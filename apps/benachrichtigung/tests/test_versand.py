"""Versand: E-Mail (locmem), Pop-up, Push-Platzhalter, Retries, Worker-Nachlauf."""

import logging

import pytest
from django.core import mail as django_mail
from django.db import connection

from apps.benachrichtigung import mail, registry, router, texte, versand
from apps.benachrichtigung.models import Popup, SmtpKonto, ZustellStatus, Zustellung
from apps.ereignisse import worker
from apps.kern.models import Einstellung

from .conftest import SMTP_PASSWORT, TYP_ENTSCHEIDUNG, TYP_INFO, TYP_KIND, veroeffentlichen

pytestmark = pytest.mark.django_db


def senden_alle(uhr=None):
    return versand.zustellungen_senden()


def zustellung(benutzer, ereignis, kanal):
    return Zustellung.objects.get(
        benachrichtigung__empfaenger=benutzer, benachrichtigung__ereignis=ereignis, kanal_id=kanal
    )


def test_email_wird_deutsch_mit_deep_link_gesendet(katalog, mama, papa, smtp):
    with texte.isoliert():
        texte.text_registrieren(
            TYP_ENTSCHEIDUNG,
            titel="{kind} hat „{aufgabe}“ gemeldet",
            text="Bitte bestätigen oder ablehnen.",
        )
        from apps.konten import services as konten

        anna = konten.kind_anlegen("Anna", "4817")
        e = veroeffentlichen(TYP_ENTSCHEIDUNG, kind=anna, daten={"aufgabe": "Müll", "instanz": 12})
        router.router(e)
    senden_alle()
    assert len(django_mail.outbox) == 2
    nachricht = next(m for m in django_mail.outbox if m.to == ["mama@example.org"])
    assert nachricht.subject == "Nestwerk: Anna hat „Müll“ gemeldet"
    assert nachricht.from_email == "nestwerk@example.org"
    assert "https://nestwerk.test/eltern/meldung/12/" in nachricht.body
    assert "Hallo Mama" in nachricht.body
    html, art = nachricht.alternatives[0]
    assert art == "text/html" and "https://nestwerk.test/eltern/meldung/12/" in html
    assert zustellung(mama, e, "email").status == ZustellStatus.GESENDET
    assert zustellung(mama, e, "email").gesendet_am is not None


def test_zweiter_versandlauf_sendet_nichts_doppelt(katalog, mama, smtp):
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    senden_alle()
    senden_alle()
    assert len(django_mail.outbox) == 1


def test_unterdrueckte_zustellungen_werden_nie_gesendet(katalog, mama, smtp):
    from apps.benachrichtigung import services

    services.praeferenz_setzen(mama, TYP_INFO, "email", False)
    router.router(veroeffentlichen(TYP_INFO))
    senden_alle()
    assert django_mail.outbox == []


def test_ohne_smtp_konto_nicht_konfiguriert(katalog, mama):
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    senden_alle()
    z = zustellung(mama, e, "email")
    assert z.status == ZustellStatus.NICHT_KONFIGURIERT
    assert "nicht eingerichtet" in z.fehler


def test_ohne_adresse_wird_aufgegeben(katalog, smtp):
    from apps.konten import services as konten

    konten.eltern_anlegen("Opa", rolle_label="andere")  # ohne E-Mail
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    senden_alle()
    opa_z = Zustellung.objects.get(
        benachrichtigung__empfaenger__anzeigename="Opa", kanal_id="email"
    )
    assert opa_z.status == ZustellStatus.AUFGEGEBEN and "Adresse" in opa_z.fehler


def test_push_ohne_geraet_ist_nicht_konfiguriert(katalog, mama):
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    senden_alle()
    z = zustellung(mama, e, "push")
    assert z.status == ZustellStatus.NICHT_KONFIGURIERT
    assert "Kein Gerät" in z.fehler


def test_smtp_fehler_wiederholt_mit_backoff_und_gibt_auf(katalog, mama, smtp, uhr, monkeypatch):
    Einstellung.objects.filter(schluessel="benachrichtigung.zustellung_max_versuche").update(wert=2)

    def kaputt(daten, *args, **kwargs):
        raise ConnectionRefusedError(f"Login mit {daten.passwort} abgelehnt")

    monkeypatch.setattr(mail, "senden", kaputt)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    senden_alle()
    z = zustellung(mama, e, "email")
    assert z.status == ZustellStatus.FEHLER and z.versuche == 1
    assert z.naechster_versuch > uhr.jetzt
    senden_alle()  # noch nicht fällig
    assert zustellung(mama, e, "email").versuche == 1
    uhr.jetzt = z.naechster_versuch
    senden_alle()
    z.refresh_from_db()
    assert z.status == ZustellStatus.AUFGEGEBEN and z.versuche == 2
    assert SMTP_PASSWORT not in z.fehler and "***" in z.fehler


def test_passwort_steht_nie_in_logs_oder_fehlertext(katalog, mama, smtp, monkeypatch, caplog):
    from django.core.mail.backends.locmem import EmailBackend

    def senden_kaputt(self, messages):
        raise OSError(f"Anmeldung mit {SMTP_PASSWORT} fehlgeschlagen")

    monkeypatch.setattr(EmailBackend, "send_messages", senden_kaputt)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    with caplog.at_level(logging.DEBUG):
        senden_alle()
    z = zustellung(mama, e, "email")
    assert z.status == ZustellStatus.FEHLER
    assert SMTP_PASSWORT not in z.fehler
    assert SMTP_PASSWORT not in caplog.text


def test_popup_kanal_legt_popup_an(katalog, mama, anna):
    e = veroeffentlichen(TYP_KIND, kind=anna)
    router.router(e)
    senden_alle()
    popup = Popup.objects.get()
    assert popup.empfaenger_id == anna.pk and popup.art == TYP_KIND and popup.gesehen_am is None
    assert zustellung(anna, e, "popup").status == ZustellStatus.GESENDET
    senden_alle()
    assert Popup.objects.count() == 1


def test_worker_runde_verteilt_routet_und_sendet(katalog, mama, papa, smtp):
    from apps.ereignisse import registry as ereignisse

    ereignisse.nachlauf_registrieren("benachrichtigung.versand", versand.zustellungen_senden)
    e = veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"instanz": 3})
    ergebnis = worker.runde()
    assert ergebnis["ok"] == 1
    assert ergebnis["nachlauf"] >= 2
    assert len(django_mail.outbox) == 2
    assert zustellung(mama, e, "email").status == ZustellStatus.GESENDET


def test_eigener_kanal_laesst_sich_registrieren(katalog, mama):
    gesendet = []

    class HaKanal(registry.ZustellKanal):
        slug = "homeassistant"
        bezeichnung = "Home Assistant"
        rollen = ("eltern",)

        def senden(self, zustellung):
            gesendet.append(zustellung.benachrichtigung.titel)

    registry.kanal_registrieren(HaKanal())
    with pytest.raises(Exception, match="doppelt"):
        registry.kanal_registrieren(HaKanal())
    from apps.benachrichtigung import services

    services.praeferenz_setzen(mama, TYP_INFO, "homeassistant", True)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    senden_alle()
    assert gesendet == ["Aufgabe gewählt"]
    assert zustellung(mama, e, "homeassistant").status == ZustellStatus.GESENDET


def test_passwort_nie_im_klartext_in_db_und_audit(smtp):
    from apps.kern.models import AuditEintrag

    konto = SmtpKonto.objects.get()
    assert konto.passwort_verschluesselt != SMTP_PASSWORT
    assert SMTP_PASSWORT not in konto.passwort_verschluesselt
    with connection.cursor() as cur:
        for tabelle in ("benachrichtigung_smtpkonto", "kern_auditeintrag"):
            cur.execute(f"SELECT * FROM {tabelle}")  # noqa: S608
            assert SMTP_PASSWORT not in repr(cur.fetchall()), tabelle
    assert AuditEintrag.objects.filter(aktion="benachrichtigung.smtp_gespeichert").exists()
    assert SMTP_PASSWORT not in repr(konto) and SMTP_PASSWORT not in str(konto)


def test_wiederholung_in_der_ruhezeit_bleibt_stumm(katalog, mama, smtp, uhr, monkeypatch):
    """B-19: Die Ruhezeit wird vor jedem Versand erneut geprüft (nicht nur beim Routing)."""
    from datetime import UTC, datetime, time

    from apps.benachrichtigung import services

    uhr.jetzt = datetime(2026, 10, 23, 19, 50, tzinfo=UTC)  # 21:50 Berlin
    services.ruhezeit_setzen(mama, von=time(22, 0), bis=time(6, 0), gilt_fuer_email=True)
    aufrufe = []

    def einmal_kaputt(*args, **kwargs):
        aufrufe.append(1)
        raise ConnectionRefusedError("kurz weg")

    monkeypatch.setattr(mail, "senden", einmal_kaputt)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    assert zustellung(mama, e, "email").status == ZustellStatus.OFFEN  # vor der Ruhezeit
    senden_alle()
    z = zustellung(mama, e, "email")
    assert z.status == ZustellStatus.FEHLER
    uhr.jetzt = datetime(2026, 10, 23, 21, 0, tzinfo=UTC)  # 23:00 Berlin: Ruhezeit
    senden_alle()
    z.refresh_from_db()
    assert z.status == ZustellStatus.UNTERDRUECKT_RUHEZEIT
    assert len(aufrufe) == 1  # kein zweiter Sendeversuch
    senden_alle()
    assert len(aufrufe) == 1
