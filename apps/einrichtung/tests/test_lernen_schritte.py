"""Etappe 8: die optionalen Schritte "Lernen" im Einrichtungs-Assistenten (Durchläufe, Überspringen,
Wiederaufnahme, Prüfungen, Schlüssel-Schutz, Idempotenz). Kein echtes Netz (Fake-Transport)."""

import logging
from pathlib import Path

import pytest
from django.contrib.sessions.models import Session
from django.test import Client

from apps.einrichtung import schritte
from apps.kern import einstellungen
from apps.kern import registry as kern_registry
from apps.kern.models import AuditEintrag, Einstellung
from apps.konten import selectors
from apps.lernen import ki_selectors
from apps.lernen.models import Fach, KiAnbieter, KiZuordnung, Leistungsstufe, Lernmappe
from apps.lernen.speicher import Speicher
from apps.lernen.tests.conftest import FakeTransport

from .conftest import abschluss, lernen_ueberspringen, url
from .test_assistent import _bis_schritt7, _startwerte_posten

GRUND, SPEICHER, KINDER_NR, KI = 8, 9, 10, 11
SCHLUESSEL = "sk-test-geheim-0123456789"  # erfunden, kein echter Schlüssel
LOKAL = {
    "modus": "openai_kompatibel",
    "name": "Meine KI",
    "basis_url": "http://dein-ki-server:11434/v1",
    "modell": "dein-modellname",
    "api_key": SCHLUESSEL,
    "aufgaben": ["auslesen", "fragen_erzeugen", "bewerten"],
}
CLOUD = {
    "modus": "anthropic",
    "name": "Cloud",
    "basis_url": "",
    "modell": "dein-modellname",
    "api_key": SCHLUESSEL,
    "aufgaben": ["auslesen"],
}


@pytest.fixture
def transport(monkeypatch):
    from apps.lernen.ki import transport as modul

    fake = FakeTransport()
    monkeypatch.setattr(modul, "post_json", fake)
    return fake


@pytest.fixture
def ordner(tmp_path, settings):
    settings.LERNEN_SPEICHER_DIR = tmp_path / "standard"
    ziel = tmp_path / "nas"
    ziel.mkdir()
    return ziel


@pytest.fixture
def bei_lernen(c):
    """Assistent bis zum ersten Lernen-Schritt."""
    _bis_schritt7(c)
    assert _startwerte_posten(c).status_code == 302
    return c


@pytest.fixture
def offen(bei_lernen):
    """Wie ``bei_lernen``, aber alle Schritte sind freigegeben (Schritte einzeln ansteuern)."""
    einstellungen.setzen("einrichtung.schritt", abschluss(), akteur=None)
    return bei_lernen


def _kinder_daten(**ueberschreiben):
    daten = {}
    for kind in selectors.aktive_kinder():
        daten.update(
            {
                f"kind-{kind.pk}-klasse": "6",
                f"kind-{kind.pk}-schulform": "Beispielschule",
                f"kind-{kind.pk}-stufe-mathe": "Grundniveau",
                f"kind-{kind.pk}-stufe-englisch": "Erweiterungsniveau",
                f"kind-{kind.pk}-freigabe": "sofort",
            }
        )
    daten.update(ueberschreiben)
    return daten


def _alles_auf_einmal(c, ordner):
    assert (
        c.post(url(GRUND), {"faecher": ["mathe"], "tagesziel": "25", "lernpunkte": "1"}).status_code
        == 302
    )
    assert c.post(url(SPEICHER), {"modus": "pfad", "pfad": str(ordner)}).status_code == 302
    assert c.post(url(KINDER_NR), _kinder_daten()).status_code == 302
    assert c.post(url(KI), {**LOKAL, "aktion": "weiter"}).status_code == 302


# --- Schrittfolge --------------------------------------------------------------------------------


def test_schrittfolge_mit_modul_schritten(c):
    assert [s.schluessel for s in schritte.erweiterungen()] == [
        "lernen_grund",
        "lernen_speicher",
        "lernen_kinder",
        "lernen_ki",
    ]
    assert abschluss() == 12
    assert schritte.erweiterung(7) is None and schritte.erweiterung(12) is None
    assert schritte.erweiterung(8).schluessel == "lernen_grund"


def test_ohne_registrierte_schritte_ist_abschluss_schritt_8(c):
    with kern_registry.isoliert():
        assert schritte.letzter() == 8
        assert schritte.erweiterung(8) is None


# --- Durchläufe ----------------------------------------------------------------------------------


def test_durchlauf_ohne_lernen_alles_ueberspringen(bei_lernen, transport):
    c = bei_lernen
    seiten = c.get(url(GRUND)).content.decode()
    assert "Später in den Einstellungen" in seiten
    lernen_ueberspringen(c)
    html = c.get(url(abschluss())).content.decode()
    assert "Übersprungene Teile behalten die Startwerte" in html
    assert c.post(url(abschluss())).status_code == 200
    assert einstellungen.wert("allgemein.einrichtung_abgeschlossen") is True
    # nichts angelegt, nichts verändert
    assert not Leistungsstufe.objects.exists() and not Lernmappe.objects.exists()
    assert not KiAnbieter.objects.exists() and not KiZuordnung.objects.exists()
    assert einstellungen.wert("lernen.speicher_pfad") == ""
    assert einstellungen.wert("lernen.tutor_aktiv") is False
    assert Fach.objects.filter(aktiv=True).count() == 2
    assert transport.aufrufe == []


def test_durchlauf_mit_lernen_legt_alles_an(bei_lernen, ordner, transport):
    c = bei_lernen
    _alles_auf_einmal(c, ordner)
    assert [f.schluessel for f in Fach.objects.filter(aktiv=True)] == ["mathe"]
    assert einstellungen.wert("lernen.tagesziel_minuten") == 25
    assert einstellungen.wert("lernen.lernpunkte_aktiv") is True
    assert einstellungen.wert("lernen.tutor_aktiv") is False  # Standard bleibt aus
    assert einstellungen.wert("lernen.speicher_pfad") == str(ordner.resolve())
    assert Speicher().basis == ordner.resolve()
    kinder = list(selectors.aktive_kinder())
    assert len(kinder) == 2
    for kind in kinder:
        mappe = Lernmappe.objects.get(kind=kind)
        assert mappe.schulform == "Beispielschule" and mappe.fragen_sofort_nutzbar is True
        stufe = Leistungsstufe.objects.get(kind=kind, fach__schluessel="mathe")
        assert (stufe.stufe, stufe.klassenstufe) == ("Grundniveau", 6)
        assert not Leistungsstufe.objects.filter(kind=kind, fach__schluessel="englisch").exists()
        assert (ordner / f"kind_{kind.pk}" / "inbox").is_dir()  # Ordner im gewählten Speicherort
    anbieter = KiAnbieter.objects.get()
    assert anbieter.aktiv and not anbieter.ist_cloud
    assert {a for a, p in ki_selectors.zuordnungen().items() if p} == set(LOKAL["aufgaben"])
    html = c.get(url(abschluss())).content.decode()
    assert "Beispielschule" in html and "Meine KI" in html and "Klasse 6" in html
    assert str(ordner.resolve()) in html
    antwort = c.post(url(abschluss()))
    assert "Fertig" in antwort.content.decode()
    assert "/eltern/lernen/ki/" in antwort.content.decode()  # Link auf der Abschlussseite
    assert einstellungen.wert("allgemein.einrichtung_abgeschlossen") is True


def test_ueberspringen_aendert_nichts_und_gibt_weiter_frei(bei_lernen):
    c = bei_lernen
    r = c.post(url(GRUND), {"aktion": "ueberspringen", "tagesziel": "99"})
    assert r.status_code == 302 and r["Location"] == url(SPEICHER)
    assert einstellungen.wert("lernen.tagesziel_minuten") != 99


def test_wiederaufnahme(bei_lernen, ordner):
    c = bei_lernen
    c.post(url(GRUND), {"faecher": ["mathe", "englisch"], "tagesziel": "30"})
    c.post(url(SPEICHER), {"modus": "pfad", "pfad": str(ordner)})
    neu = Client()  # neue Sitzung, z. B. am nächsten Tag
    r = neu.get("/einrichtung/")
    assert r.status_code == 302 and r["Location"] == url(KINDER_NR)
    # zurück: gespeicherte Werte sind vorbelegt
    html = neu.get(url(GRUND)).content.decode()
    assert 'value="30"' in html
    assert str(ordner.resolve()) in neu.get(url(SPEICHER)).content.decode()


# --- Grundwerte ----------------------------------------------------------------------------------


@pytest.mark.parametrize("ziel", ["", "0", "241", "abc"])
def test_grundwerte_tagesziel_ungueltig(bei_lernen, ziel):
    r = bei_lernen.post(url(GRUND), {"faecher": ["mathe"], "tagesziel": ziel})
    assert r.status_code == 200 and "Tagesziel muss eine Zahl" in r.content.decode()
    assert einstellungen.wert("lernen.tagesziel_minuten") == 20


def test_grundwerte_ohne_fach_und_unbekanntes_fach(bei_lernen):
    for faecher in ([], ["gibt-es-nicht"]):
        r = bei_lernen.post(url(GRUND), {"faecher": faecher, "tagesziel": "20"})
        assert r.status_code == 200 and "mindestens ein Fach" in r.content.decode()
    assert Fach.objects.filter(aktiv=True).count() == 2


def test_tutor_standard_aus_mit_hinweis_und_einschaltbar(bei_lernen):
    html = bei_lernen.get(url(GRUND)).content.decode()
    assert "Eine Garantie gibt es nicht" in html
    assert 'name="tutor" value="1" checked' not in html
    bei_lernen.post(url(GRUND), {"faecher": ["mathe"], "tagesziel": "20", "tutor": "1"})
    assert einstellungen.wert("lernen.tutor_aktiv") is True
    assert einstellungen.wert("lernen.lernpunkte_aktiv") is False  # nicht angehakt = aus


# --- Speicher ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pfad",
    ["", "relativ/ordner", "/tmp/../etc", "/", "/etc", "/proc/self", "/usr/lib", "/gibt/es/nicht"],
)
def test_speicher_pfad_abgelehnt(offen, pfad):
    r = offen.post(url(SPEICHER), {"modus": "pfad", "pfad": pfad})
    assert r.status_code == 200 and "feld__hinweis--fehler" in r.content.decode()
    assert einstellungen.wert("lernen.speicher_pfad") == ""


def test_speicher_datei_statt_ordner_und_programmordner(offen, tmp_path, settings):
    datei = tmp_path / "datei.txt"
    datei.write_text("x")
    r = offen.post(url(SPEICHER), {"modus": "pfad", "pfad": str(datei)})
    assert "gibt es nicht" in r.content.decode()
    r = offen.post(url(SPEICHER), {"modus": "pfad", "pfad": str(settings.BASE_DIR)})
    assert "nicht verwendet werden" in r.content.decode()


def test_speicher_nicht_schreibbar(offen, ordner, monkeypatch):
    def verweigert(*args, **kwargs):
        raise PermissionError("kein Zugriff")

    monkeypatch.setattr("apps.lernen.speicher.tempfile.NamedTemporaryFile", verweigert)
    r = offen.post(url(SPEICHER), {"modus": "pfad", "pfad": str(ordner)})
    html = r.content.decode()
    assert "nicht schreiben" in html and "kein Zugriff" not in html  # keine Systemdetails
    assert einstellungen.wert("lernen.speicher_pfad") == ""


def test_speicher_schreibtest_hinterlaesst_nichts_und_volume_zurueck(offen, ordner):
    assert offen.post(url(SPEICHER), {"modus": "pfad", "pfad": str(ordner)}).status_code == 302
    assert list(Path(ordner).iterdir()) == []
    r = offen.post(url(SPEICHER), {"modus": "volume", "pfad": str(ordner)})
    assert r.status_code == 302 and einstellungen.wert("lernen.speicher_pfad") == ""


def test_speicher_unbekannter_modus(offen):
    r = offen.post(url(SPEICHER), {"modus": "irgendwas"})
    assert r.status_code == 200 and "Auswahl" in r.content.decode()


def test_speicher_symlink_auf_systemordner_abgelehnt(offen, tmp_path):
    link = tmp_path / "link"
    link.symlink_to("/etc")
    r = offen.post(url(SPEICHER), {"modus": "pfad", "pfad": str(link)})
    assert "nicht verwendet werden" in r.content.decode()


# --- Kinder --------------------------------------------------------------------------------------


def test_kinder_validierung_alles_oder_nichts(offen):
    erstes = selectors.aktive_kinder().order_by("anzeigename").first()
    daten = _kinder_daten(**{f"kind-{erstes.pk}-klasse": "99"})
    r = offen.post(url(KINDER_NR), daten)
    assert r.status_code == 200 and "Klassenstufe muss" in r.content.decode()
    assert not Lernmappe.objects.exists() and not Leistungsstufe.objects.exists()
    r = offen.post(url(KINDER_NR), _kinder_daten(**{f"kind-{erstes.pk}-klasse": "x"}))
    assert "Klassenstufe muss" in r.content.decode()
    r = offen.post(url(KINDER_NR), _kinder_daten(**{f"kind-{erstes.pk}-stufe-mathe": "Superhirn"}))
    assert "Unbekannte Leistungsstufe" in r.content.decode()
    r = offen.post(url(KINDER_NR), _kinder_daten(**{f"kind-{erstes.pk}-schulform": "x" * 61}))
    assert "Schulform ist zu lang" in r.content.decode()
    assert not Lernmappe.objects.exists()


def test_kinder_leere_angaben_und_standardfreigabe(offen):
    r = offen.post(url(KINDER_NR), {})
    assert r.status_code == 302
    for kind in selectors.aktive_kinder():
        mappe = Lernmappe.objects.get(kind=kind)
        assert mappe.fragen_sofort_nutzbar is False and mappe.schulform == ""
        assert not Leistungsstufe.objects.filter(kind=kind).exists()  # keine Stufe, keine Klasse


def test_kinder_idempotent_und_stufe_entfernen(offen):
    for _ in range(2):
        assert offen.post(url(KINDER_NR), _kinder_daten()).status_code == 302
    assert Lernmappe.objects.count() == 2
    assert Leistungsstufe.objects.count() == 4  # 2 Kinder x 2 Fächer
    kind = selectors.aktive_kinder().order_by("anzeigename").first()
    leer = _kinder_daten(
        **{
            f"kind-{kind.pk}-klasse": "",
            f"kind-{kind.pk}-stufe-mathe": "",
            f"kind-{kind.pk}-stufe-englisch": "",
        }
    )
    offen.post(url(KINDER_NR), leer)
    assert not Leistungsstufe.objects.filter(kind=kind).exists()
    assert Lernmappe.objects.count() == 2
    html = offen.get(url(KINDER_NR)).content.decode()
    assert "Beispielschule" in html  # gespeicherter Stand wird wieder angezeigt


def test_kinder_ordner_fehler_wird_gemeldet(offen, monkeypatch):
    def kaputt(self, kind_id):
        raise OSError("voll")

    monkeypatch.setattr(Speicher, "ordner_anlegen", kaputt)
    r = offen.post(url(KINDER_NR), _kinder_daten())
    html = r.content.decode()
    assert r.status_code == 200 and "Speicherort prüfen" in html and "voll" not in html
    assert not Lernmappe.objects.exists()


def test_kinder_fremde_ids_werden_ignoriert(offen):
    r = offen.post(url(KINDER_NR), {"kind-11111111-1111-1111-1111-111111111111-klasse": "5"})
    assert r.status_code == 302
    assert not Leistungsstufe.objects.exists()


# --- KI ------------------------------------------------------------------------------------------


def test_ki_keine_ki_jetzt_aendert_nichts(offen, transport):
    r = offen.post(url(KI), {"modus": "keine"})
    assert r.status_code == 302 and not KiAnbieter.objects.exists() and transport.aufrufe == []


def test_ki_lokal_testen_und_speichern(offen, transport):
    r = offen.post(url(KI), {**LOKAL, "aktion": "testen"})
    html = r.content.decode()
    assert r.status_code == 200 and "Test erfolgreich" in html and "Verbindung steht" in html
    assert len(transport.aufrufe) == 1
    assert transport.aufrufe[0]["url"].startswith("http://dein-ki-server:11434")
    anbieter = KiAnbieter.objects.get()
    assert anbieter.letzter_test_ok is True and anbieter.aktiv
    assert SCHLUESSEL not in html
    assert "Ein Schlüssel ist gespeichert" in html
    # Weiter ohne Schlüssel im Formular: der gespeicherte bleibt
    ohne = {**LOKAL, "api_key": "", "aktion": "weiter"}
    assert offen.post(url(KI), ohne).status_code == 302
    assert KiAnbieter.objects.get().hat_schluessel


def test_ki_test_fehlgeschlagen_zeigt_klartext(offen, transport):
    transport.antworten.append((401, {"error": "nope"}))
    html = offen.post(url(KI), {**LOKAL, "aktion": "testen"}).content.decode()
    assert "Test fehlgeschlagen" in html and "Zugang abgelehnt" in html
    assert KiAnbieter.objects.get().letzter_test_ok is False


@pytest.mark.parametrize("adresse", ["ftp://server", "http://nutzer:pw@server/v1", "kein url", ""])
def test_ki_ungueltige_url(offen, adresse, transport):
    r = offen.post(url(KI), {**LOKAL, "basis_url": adresse})
    assert r.status_code == 200 and "feld__hinweis--fehler" in r.content.decode()
    assert not KiAnbieter.objects.exists() and transport.aufrufe == []


def test_ki_pflichtfelder(offen):
    for feld in ("name", "modell"):
        r = offen.post(url(KI), {**LOKAL, feld: ""})
        assert r.status_code == 200
    r = offen.post(url(KI), {**CLOUD, "api_key": "", "einwilligung": "1"})
    assert "API-Schlüssel nötig" in r.content.decode()
    assert offen.post(url(KI), {**LOKAL, "modus": "gibt-es-nicht"}).status_code == 200
    assert not KiAnbieter.objects.exists()


def test_ki_cloud_ohne_einwilligung_nicht_aktivierbar(offen, transport):
    r = offen.post(url(KI), {**CLOUD, "aktion": "weiter"})
    assert r.status_code == 200 and "Einwilligung" in r.content.decode()
    assert not KiAnbieter.objects.exists()  # alles oder nichts
    r = offen.post(url(KI), {**CLOUD, "aktion": "testen"})
    assert "Einwilligung" in r.content.decode() and transport.aufrufe == []
    assert not KiZuordnung.objects.exists()
    assert SCHLUESSEL not in r.content.decode()


def test_ki_cloud_mit_einwilligung(offen, transport):
    r = offen.post(url(KI), {**CLOUD, "einwilligung": "1", "aktion": "weiter"})
    assert r.status_code == 302
    anbieter = KiAnbieter.objects.get()
    assert anbieter.ist_cloud and anbieter.aktiv and anbieter.einwilligung_am is not None
    assert AuditEintrag.objects.filter(aktion="lernen.ki_einwilligung").count() == 1
    html = offen.get(url(KI)).content.decode()
    assert "Cloud-Anbieter" in html and "Kosten pro Nutzung" in html


def test_ki_nachtraeglich_keine_ki_loest_zuordnung(offen):
    offen.post(url(KI), {**LOKAL, "aktion": "weiter"})
    assert KiZuordnung.objects.count() == 3
    assert offen.post(url(KI), {"modus": "keine"}).status_code == 302
    anbieter = KiAnbieter.objects.get()
    assert not anbieter.aktiv and not KiZuordnung.objects.exists()
    assert 'value="keine" selected' in offen.get(url(KI)).content.decode()


def test_ki_idempotent_und_aufgaben_aendern(offen):
    for _ in range(2):
        assert offen.post(url(KI), {**LOKAL, "aktion": "weiter"}).status_code == 302
    assert KiAnbieter.objects.count() == 1 and KiZuordnung.objects.count() == 3
    offen.post(url(KI), {**LOKAL, "aufgaben": ["tutor"], "aktion": "weiter"})
    assert {a for a, p in ki_selectors.zuordnungen().items() if p} == {"tutor"}
    offen.post(url(KI), {**LOKAL, "name": "Umbenannt", "aufgaben": ["unbekannt"]})
    assert KiAnbieter.objects.get().name == "Umbenannt" and not KiZuordnung.objects.exists()


def test_ki_vorbelegung_mit_tutor(offen):
    offen.post(url(GRUND), {"faecher": ["mathe"], "tagesziel": "20", "tutor": "1"})
    html = offen.get(url(KI)).content.decode()
    assert 'value="tutor" checked' in html


def test_schluessel_nirgends_im_klartext(offen, ordner, transport, caplog):
    caplog.set_level(logging.DEBUG)
    seiten = []
    c = offen
    seiten.append(c.post(url(KI), {**LOKAL, "aktion": "testen"}).content.decode())
    seiten.append(c.post(url(KI), {**LOKAL, "basis_url": "kein url"}).content.decode())
    seiten.append(c.post(url(KI), {**CLOUD, "aktion": "testen"}).content.decode())
    seiten.append(c.get(url(KI)).content.decode())
    c.post(url(KI), {**LOKAL, "aktion": "weiter"})
    seiten.append(c.get(url(abschluss())).content.decode())
    for html in seiten:
        assert SCHLUESSEL not in html
    anbieter = KiAnbieter.objects.get()
    assert SCHLUESSEL not in anbieter.schluessel_verschluesselt and anbieter.hat_schluessel
    for e in AuditEintrag.objects.all():
        assert SCHLUESSEL not in str(e.details) and SCHLUESSEL not in str(e.__dict__)
    for s in Session.objects.all():
        assert SCHLUESSEL not in str(s.get_decoded())
    assert not any(SCHLUESSEL in str(w.wert) for w in Einstellung.objects.all())
    assert SCHLUESSEL not in caplog.text
    for aufruf in transport.aufrufe:  # der Schlüssel geht nur als Anfrage-Kopf an den Anbieter
        assert SCHLUESSEL not in str(aufruf["payload"])


# --- Zugriff, Sprache ----------------------------------------------------------------------------


def test_nur_heimnetz_auch_fuer_lernen_schritte(offen):
    for nr in (GRUND, SPEICHER, KINDER_NR, KI):
        assert offen.get(url(nr), REMOTE_ADDR="8.8.8.8").status_code == 403
        assert offen.post(url(nr), {}, REMOTE_ADDR="8.8.8.8").status_code == 403


def test_schritte_nicht_ueberspringbar_per_adresse(c):
    r = c.get(url(GRUND))
    assert r.status_code == 302 and r["Location"] == url(1)


def test_nach_abschluss_gesperrt_und_eltern_seiten_nur_fuer_eltern(bei_lernen, ordner, transport):
    c = bei_lernen
    _alles_auf_einmal(c, ordner)
    assert c.post(url(abschluss())).status_code == 200
    for nr in (GRUND, SPEICHER, KINDER_NR, KI):
        assert c.get(url(nr)).status_code == 404
        assert c.post(url(nr), {"modus": "keine"}).status_code == 404
    kind = selectors.aktive_kinder().get(anzeigename="Max")
    r = c.post(f"/anmelden/kind/{kind.pk}/", {"pin": "1357"})
    assert r.status_code == 302
    antwort = c.get("/eltern/lernen/ki/")
    assert antwort.status_code != 200 and "Meine KI" not in antwort.content.decode()


def test_schritte_auf_englisch(offen, settings):
    offen.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    for nr, text in (
        (GRUND, "Learning: basics"),
        (SPEICHER, "Learning: storage"),
        (KINDER_NR, "Learning: children"),
        (KI, "Learning: AI"),
    ):
        html = offen.get(url(nr)).content.decode()
        assert text in html, nr
        assert "Später in den Einstellungen" not in html
        assert "Later in the settings" in html
    en = offen.get(url(KI)).content.decode()
    assert "Test connection" in en and "A guarantee" not in en
    assert "Keine KI jetzt" not in en and "No AI for now" in en
