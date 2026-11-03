"""Anbieter, Verschlüsselung, Einwilligung, Zuordnung und ki_aufruf (SPEC 21.6)."""

import logging

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.kern.models import AuditEintrag
from apps.lernen import ki_selectors, ki_services
from apps.lernen.ki import (
    KiAuthFehler,
    KiEinwilligungFehlt,
    KiNichtVerfuegbar,
    KiServerFehler,
    KiVerbindungsFehler,
)
from apps.lernen.models import KiAnbieter, KiAufgabe, KiZuordnung

KEY = "test-schluessel-nicht-echt"


def _alles_gespeicherte_text():
    """Alle Tabellen als Text: der Klartext-Schlüssel darf nirgends vorkommen."""
    with connection.cursor() as c:
        tabellen = connection.introspection.table_names(c)
        teile = []
        for t in tabellen:
            if t.startswith(("lernen_ki", "kern_audit")):
                c.execute(f'SELECT * FROM "{t}"')  # noqa: S608 - nur Tabellennamen aus der DB
                teile.append(repr(c.fetchall()))
    return "\n".join(teile)


# --- Standard und Anlegen ------------------------------------------------------------------------


def test_standard_ist_ki_aus(db):
    assert not KiAnbieter.objects.exists() and not KiZuordnung.objects.exists()
    for aufgabe in KiAufgabe.values:
        assert ki_selectors.ki_status(aufgabe) is ki_selectors.KiStatus.AUS
        assert not ki_selectors.ki_verfuegbar(aufgabe)
        with pytest.raises(KiNichtVerfuegbar):
            ki_services.ki_aufruf(aufgabe, nachricht="x")


def test_anlegen_ist_inaktiv_und_cloud_wird_erkannt(lokal, cloud):
    assert (lokal.aktiv, lokal.ist_cloud, lokal.hat_schluessel) == (False, False, False)
    assert (cloud.aktiv, cloud.ist_cloud, cloud.hat_schluessel) == (False, True, True)
    fern = ki_services.anbieter_speichern(
        name="Fern", typ="openai_kompatibel", basis_url="https://ki.example.com/v1", modell="m"
    )
    assert fern.ist_cloud is True


@pytest.mark.parametrize(
    "felder",
    [
        {"name": " "},
        {"modell": ""},
        {"typ": "quatsch"},
        {"typ": "openai_kompatibel", "basis_url": ""},
        {"basis_url": "ftp://x"},
        {"basis_url": "http://nutzer:pw@host/v1"},
        {"typ": "anthropic", "api_key": ""},
    ],
)
def test_validierung(db, felder):
    daten = {"name": "A", "typ": "openai_kompatibel", "basis_url": "http://h/v1", "modell": "m"}
    daten.update(felder)
    with pytest.raises(ValidationError):
        ki_services.anbieter_speichern(**daten)
    assert not KiAnbieter.objects.exists()


def test_name_muss_eindeutig_sein(lokal):
    with pytest.raises(ValidationError):
        ki_services.anbieter_speichern(
            name="Eigener Server", typ="openai_kompatibel", basis_url="http://h", modell="m"
        )
    ki_services.anbieter_speichern(
        anbieter=lokal,
        name="Eigener Server",
        typ="openai_kompatibel",
        basis_url="http://h",
        modell="neu",
    )  # sich selbst überschreiben ist erlaubt
    lokal.refresh_from_db()
    assert lokal.modell == "neu"


# --- Verschlüsselung -----------------------------------------------------------------------------


def test_key_verschluesselt_und_nirgends_im_klartext(cloud):
    cloud.refresh_from_db()
    assert KEY not in cloud.schluessel_verschluesselt
    assert cloud.schluessel_verschluesselt.startswith("gAAAA")  # Fernet-Token
    assert KEY not in _alles_gespeicherte_text()
    assert KEY not in repr(cloud) and KEY not in str(cloud)


def test_leerer_key_behaelt_den_alten_neuer_ersetzt(cloud):
    alt = cloud.schluessel_verschluesselt
    ki_services.anbieter_speichern(
        anbieter=cloud, name="Cloud", typ="anthropic", modell="m2", api_key=""
    )
    cloud.refresh_from_db()
    assert cloud.schluessel_verschluesselt == alt and cloud.modell == "m2"
    ki_services.anbieter_speichern(
        anbieter=cloud, name="Cloud", typ="anthropic", modell="m2", api_key="anderer-schluessel"
    )
    cloud.refresh_from_db()
    assert cloud.schluessel_verschluesselt != alt
    assert "anderer-schluessel" not in _alles_gespeicherte_text()


def test_audit_beim_speichern_ohne_key(cloud):
    eintrag = AuditEintrag.objects.get(aktion="lernen.ki_anbieter_angelegt")
    assert eintrag.details["schluessel_gesetzt"] is True
    assert KEY not in str(eintrag.details)


# --- Einwilligung und Aktivierung ----------------------------------------------------------------


def test_cloud_braucht_einwilligung(cloud, mama):
    with pytest.raises(KiEinwilligungFehlt):
        ki_services.anbieter_aktivieren(cloud)
    cloud.refresh_from_db()
    assert not cloud.aktiv and cloud.einwilligung_am is None
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    cloud.refresh_from_db()
    assert cloud.aktiv and cloud.einwilligung_am is not None
    assert cloud.einwilligung_von == mama
    assert AuditEintrag.objects.filter(aktion="lernen.ki_einwilligung").count() == 1


def test_einwilligung_bleibt_bei_aus_und_wieder_ein(cloud, mama):
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    ki_services.anbieter_deaktivieren(cloud, akteur=mama)
    am = KiAnbieter.objects.get(pk=cloud.pk).einwilligung_am
    ki_services.anbieter_aktivieren(cloud, akteur=mama)  # ohne Häkchen: bereits erteilt
    cloud.refresh_from_db()
    assert cloud.aktiv and cloud.einwilligung_am == am
    assert AuditEintrag.objects.filter(aktion="lernen.ki_einwilligung").count() == 1


def test_lokal_braucht_keine_einwilligung(lokal):
    ki_services.anbieter_aktivieren(lokal)
    lokal.refresh_from_db()
    assert lokal.aktiv and lokal.einwilligung_am is None


def test_adresse_aendern_setzt_einwilligung_zurueck(cloud, mama):
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    ki_services.anbieter_speichern(
        anbieter=cloud,
        name="Cloud",
        typ="openai",
        modell="m",
        basis_url="https://proxy.example.com/v1",
    )
    cloud.refresh_from_db()
    assert not cloud.aktiv and cloud.einwilligung_am is None and cloud.einwilligung_von is None


def test_nur_modell_aendern_laesst_einwilligung_und_zustand(cloud, mama):
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    ki_services.anbieter_speichern(anbieter=cloud, name="Cloud", typ="anthropic", modell="neu")
    cloud.refresh_from_db()
    assert cloud.aktiv and cloud.einwilligung_am is not None


def test_lokal_wird_zu_cloud_geaendert(lokal):
    ki_services.anbieter_aktivieren(lokal)
    ki_services.anbieter_speichern(
        anbieter=lokal,
        name="Eigener Server",
        typ="openai_kompatibel",
        basis_url="https://ki.example.com/v1",
        modell="m",
    )
    lokal.refresh_from_db()
    assert lokal.ist_cloud and not lokal.aktiv


def test_lokal_aendern_bleibt_aktiv(lokal):
    ki_services.anbieter_aktivieren(lokal)
    ki_services.anbieter_speichern(
        anbieter=lokal,
        name="Eigener Server",
        typ="openai_kompatibel",
        basis_url="http://anderer-server:11434/v1",
        modell="m",
    )
    lokal.refresh_from_db()
    assert lokal.aktiv and not lokal.ist_cloud


# --- Zuordnung -----------------------------------------------------------------------------------


def test_zuordnung_setzen_aendern_loeschen(lokal, cloud):
    ki_services.zuordnung_setzen("tutor", lokal)
    ki_services.zuordnung_setzen("tutor", cloud)
    assert KiZuordnung.objects.count() == 1
    assert ki_selectors.zuordnung_fuer("tutor") == cloud
    assert ki_selectors.zuordnungen()["tutor"] == cloud
    assert ki_selectors.zuordnungen()["bewerten"] is None
    ki_services.zuordnung_setzen("tutor", None)
    assert ki_selectors.zuordnung_fuer("tutor") is None
    with pytest.raises(ValidationError):
        ki_services.zuordnung_setzen("unbekannt", lokal)
    assert AuditEintrag.objects.filter(aktion="lernen.ki_zuordnung_gesetzt").count() == 3


def test_status_der_zuordnung(lokal, cloud, mama):
    S = ki_selectors.KiStatus
    ki_services.zuordnung_setzen("tutor", cloud)
    assert ki_selectors.ki_status("tutor") is S.NICHT_AKTIV
    cloud.aktiv = True
    cloud.save()
    assert ki_selectors.ki_status("tutor") is S.EINWILLIGUNG_FEHLT
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    assert ki_selectors.ki_status("tutor") is S.BEREIT
    assert ki_selectors.ki_verfuegbar("tutor")
    assert ki_selectors.auftraege_offen() == 0
    assert [a.name for a in ki_selectors.anbieter_liste()] == ["Cloud", "Eigener Server"]


# --- ki_aufruf -----------------------------------------------------------------------------------


def test_aufruf_nicht_aktiv_und_ohne_einwilligung(cloud, transport):
    ki_services.zuordnung_setzen("tutor", cloud)
    with pytest.raises(KiNichtVerfuegbar):
        ki_services.ki_aufruf("tutor", nachricht="x")
    cloud.aktiv = True  # an der Einwilligung vorbei (z. B. Datenfehler): trotzdem gesperrt
    cloud.save()
    with pytest.raises(KiEinwilligungFehlt):
        ki_services.ki_aufruf("tutor", nachricht="x")
    assert transport.aufrufe == []


def test_unbekannte_aufgabe(db):
    with pytest.raises(ValueError):
        ki_services.ki_aufruf("quatsch", nachricht="x")


def test_aufruf_erfolg_mit_metadaten_ohne_inhalt(lokal, transport, kind_a, caplog):
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("bewerten", lokal)
    transport.antworten.append(
        (
            200,
            {
                "choices": [{"message": {"content": "GEHEIME-ANTWORT"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4},
            },
        )
    )
    with caplog.at_level(logging.INFO, logger="nestwerk.lernen.ki"):
        antwort = ki_services.ki_aufruf(
            "bewerten", system="GEHEIMES-SYSTEM", nachricht="GEHEIME-FRAGE", kind=kind_a
        )
    assert antwort.text == "GEHEIME-ANTWORT"
    aufruf = transport.aufrufe[0]
    assert aufruf["url"] == "http://dein-ki-server:11434/v1/chat/completions"
    assert aufruf["timeout"] == 60  # Einstellung lernen.ki_timeout_sekunden
    eintrag = AuditEintrag.objects.get(aktion="lernen.ki_aufruf")
    d = eintrag.details
    assert d["aufgabe"] == "bewerten" and d["erfolg"] is True and d["cloud"] is False
    assert (d["tokens_ein"], d["tokens_aus"]) == (9, 4) and d["dauer_ms"] >= 0
    assert d["anbieter"] == lokal.pk and eintrag.kind == kind_a
    gesamt = str(d) + caplog.text + _alles_gespeicherte_text()
    assert "GEHEIM" not in gesamt


def test_aufruf_gibt_key_nur_an_den_adapter(cloud, transport, mama):
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    ki_services.zuordnung_setzen("fragen_erzeugen", cloud)
    transport.antworten.append((200, {"content": [{"type": "text", "text": "ok"}]}))
    ki_services.ki_aufruf("fragen_erzeugen", nachricht="x", timeout=7)
    assert transport.aufrufe[0]["headers"]["x-api-key"] == KEY
    assert transport.aufrufe[0]["timeout"] == 7


def test_aufruf_fehler_wird_protokolliert_und_weitergereicht(lokal, transport, caplog):
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("tutor", lokal)
    transport.antworten.append((401, {"error": "abgelehnt"}))
    with pytest.raises(KiAuthFehler):
        ki_services.ki_aufruf("tutor", nachricht="x")
    d = AuditEintrag.objects.get(aktion="lernen.ki_aufruf").details
    assert d["erfolg"] is False and d["fehler"] == "auth" and "tokens_ein" not in d


def test_unerwarteter_fehler_wird_protokolliert(lokal, transport):
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("tutor", lokal)
    transport.antworten.append(RuntimeError("Bug"))
    with pytest.raises(RuntimeError):
        ki_services.ki_aufruf("tutor", nachricht="x")
    assert AuditEintrag.objects.get(aktion="lernen.ki_aufruf").details["fehler"] == "intern"


def test_kein_stiller_fallback(lokal, cloud, transport, mama):
    """Schlägt der zugeordnete Anbieter fehl, wird kein anderer Anbieter gefragt."""
    ki_services.anbieter_aktivieren(lokal)
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    ki_services.zuordnung_setzen("tutor", lokal)
    ki_services.zuordnung_setzen("bewerten", cloud)
    transport.antworten.append(KiVerbindungsFehler())
    with pytest.raises(KiVerbindungsFehler):
        ki_services.ki_aufruf("tutor", nachricht="x")
    assert len(transport.aufrufe) == 1
    assert transport.aufrufe[0]["url"].startswith("http://dein-ki-server")
    # Nach dem Ausschalten des zugeordneten Anbieters: KI aus, nicht der andere Anbieter
    ki_services.anbieter_deaktivieren(lokal)
    with pytest.raises(KiNichtVerfuegbar):
        ki_services.ki_aufruf("tutor", nachricht="x")
    assert len(transport.aufrufe) == 1


def test_key_passt_nicht_zum_schluessel(lokal, transport, settings):
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("tutor", lokal)
    lokal.schluessel_verschluesselt = "gAAAAAkaputt"
    lokal.save()
    with pytest.raises(Exception) as exc:
        ki_services.ki_aufruf("tutor", nachricht="x")
    assert exc.value.art == "konfiguration"
    assert transport.aufrufe == []


# --- Verbindungstest -----------------------------------------------------------------------------


def test_verbindung_testen_ok(lokal, transport):
    ergebnis = ki_services.verbindung_testen(lokal)
    assert ergebnis.ok and ergebnis.art == ""
    lokal.refresh_from_db()
    assert lokal.letzter_test_ok is True and lokal.letzter_test_am is not None
    assert "OK" in transport.aufrufe[0]["payload"]["messages"][-1]["content"]
    assert AuditEintrag.objects.get(aktion="lernen.ki_aufruf").details["aufgabe"] == "test"


def test_verbindung_testen_fehler_ohne_secrets(cloud, transport):
    transport.antworten.append((500, {"error": KEY}))
    ergebnis = ki_services.verbindung_testen(cloud)
    assert not ergebnis.ok and ergebnis.art == "server"
    assert KEY not in repr(ergebnis)
    cloud.refresh_from_db()
    assert cloud.letzter_test_ok is False
    # Änderung der Zugangsdaten macht den Test ungültig
    ki_services.anbieter_speichern(anbieter=cloud, name="Cloud", typ="anthropic", modell="x")
    cloud.refresh_from_db()
    assert cloud.letzter_test_ok is None


def test_server_fehler_klasse(db):
    assert KiServerFehler().wiederholbar
