"""SMTP-Konto, Fernet-Schlüssel und Testmail."""

import os
import stat

import pytest
from django.core import mail as django_mail
from django.core.exceptions import ValidationError

from apps.benachrichtigung import crypto, mail, services
from apps.benachrichtigung.models import SmtpKonto
from apps.kern.models import AuditEintrag

from .conftest import SMTP_PASSWORT

pytestmark = pytest.mark.django_db

ANGABEN = {
    "host": "smtp.example.org",
    "port": 587,
    "sicherheit": "starttls",
    "benutzername": "nestwerk@example.org",
    "absender": "nestwerk@example.org",
}


def test_fernet_roundtrip_und_falscher_schluessel(settings):
    token = crypto.verschluesseln("geheim")
    assert "geheim" not in token and crypto.entschluesseln(token) == "geheim"
    settings.FERNET_KEY = "ZmFsc2NoZXItc2NobHVlc3NlbC1uaWNodC1nZWx0ZW5kLTEyMzQ="
    with pytest.raises((crypto.SchluesselFehler, ValueError)):
        crypto.entschluesseln(token)


def test_schluesseldatei_wird_im_volume_angelegt(settings, tmp_path):
    settings.FERNET_KEY = None
    settings.SECRETS_DIR = tmp_path / "secrets"
    token = crypto.verschluesseln("abc")
    datei = tmp_path / "secrets" / "fernet.key"
    assert datei.exists()
    assert stat.S_IMODE(os.stat(datei).st_mode) == 0o600
    assert crypto.entschluesseln(token) == "abc"  # gleicher Schlüssel beim zweiten Zugriff


def test_smtp_speichern_behaelt_passwort_ohne_neueingabe(smtp):
    vorher = SmtpKonto.objects.get().passwort_verschluesselt
    services.smtp_speichern(**{**ANGABEN, "port": 465, "sicherheit": "ssl"})
    konto = SmtpKonto.objects.get()
    assert konto.passwort_verschluesselt == vorher and konto.port == 465
    assert mail.daten_aus_konto(konto).passwort


def test_smtp_ohne_passwort_beim_ersten_mal_wird_abgelehnt(db):
    with pytest.raises(ValidationError):
        services.smtp_speichern(**ANGABEN)
    with pytest.raises(ValidationError):
        services.smtp_speichern(**{**ANGABEN, "port": 0}, passwort="x")
    with pytest.raises(ValidationError):
        services.smtp_speichern(**{**ANGABEN, "absender": "kaputt"}, passwort="x")


def test_audit_enthaelt_kein_passwort(smtp):
    eintrag = AuditEintrag.objects.get(aktion="benachrichtigung.smtp_gespeichert")
    assert SMTP_PASSWORT not in repr(eintrag.details)
    assert eintrag.details["zugang_neu"] is True


def test_testmail_mit_gespeichertem_konto(smtp):
    ergebnis = services.testmail_senden("eltern@example.org")
    assert ergebnis.ok and "eltern@example.org" in ergebnis.meldung
    assert len(django_mail.outbox) == 1
    nachricht = django_mail.outbox[0]
    assert nachricht.to == ["eltern@example.org"] and nachricht.from_email == "nestwerk@example.org"
    assert "Testnachricht" in nachricht.subject
    assert SmtpKonto.objects.get().zuletzt_getestet_am is not None


def test_testmail_mit_ungespeicherten_daten_setzt_kein_testdatum(db):
    daten = mail.SmtpDaten(passwort="pw", **ANGABEN)
    assert "pw" not in repr(daten)
    ergebnis = services.testmail_senden("a@example.org", daten=daten)
    assert ergebnis.ok and len(django_mail.outbox) == 1
    assert not SmtpKonto.objects.exists()


def test_testmail_fehler_ist_deutsch_und_ohne_passwort(db, monkeypatch):
    def kaputt(daten, *args, **kwargs):
        raise ConnectionRefusedError(f"Verbindung abgelehnt (Passwort {daten.passwort})")

    monkeypatch.setattr(mail, "senden", kaputt)
    ergebnis = services.testmail_senden(
        "a@example.org", daten=mail.SmtpDaten(passwort="Streng-Geheim", **ANGABEN)
    )
    assert not ergebnis.ok
    assert ergebnis.meldung.startswith("Der Versand hat nicht geklappt")
    assert "Streng-Geheim" not in ergebnis.meldung
    eintrag = AuditEintrag.objects.get(aktion="benachrichtigung.testmail_fehlgeschlagen")
    assert "Streng-Geheim" not in repr(eintrag.details)


def test_testmail_ohne_konto_und_mit_falscher_adresse(db):
    assert not services.testmail_senden("a@example.org").ok
    assert services.testmail_senden("kaputt").meldung == "Die E-Mail-Adresse ist ungültig."


def test_aenderung_der_zugangsdaten_setzt_testdatum_zurueck(smtp):
    services.testmail_senden("a@example.org")
    services.smtp_speichern(**ANGABEN, passwort="neu")
    assert SmtpKonto.objects.get().zuletzt_getestet_am is None
