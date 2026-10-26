from datetime import UTC, datetime, timedelta

import pytest

from apps.benachrichtigung import registry, router, services
from apps.ereignisse import registry as ereignis_registry
from apps.ereignisse import services as ereignis_services
from apps.kern import zeit
from apps.konten import services as konten_services

PASSWORT = "Zebra-Korkenzieher-77"
PIN = "4817"
SMTP_PASSWORT = "Geheim-Mail-Passwort-4711"

TYP_ENTSCHEIDUNG = "test.gemeldet"
TYP_INFO = "test.info"
TYP_KIND = "test.bestaetigt"
TYP_LISTE = "test.nur_liste"
TYP_INTERN = "test.intern"


class Uhr:
    """Steuerbare Uhr (lokale Zeit Europe/Berlin = UTC+2 im Oktober vor der Umstellung)."""

    def __init__(self):
        self.jetzt = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)  # Freitag 14:00 lokal

    def lokal(self, wochentag_datum, stunde, minute=0):
        """Setzt die Uhr auf lokale Zeit (CEST, UTC+2) an einem Datum."""
        self.jetzt = datetime(
            wochentag_datum.year,
            wochentag_datum.month,
            wochentag_datum.day,
            stunde,
            minute,
            tzinfo=UTC,
        ) - timedelta(hours=2)


@pytest.fixture(autouse=True)
def zeitzone(db):
    from apps.kern.models import Einstellung

    Einstellung.objects.update_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )


@pytest.fixture(autouse=True)
def dns_oeffentlich(monkeypatch):
    """Keine echte Namensauflösung: jeder Host löst auf eine öffentliche Adresse auf."""
    from apps.benachrichtigung import push

    monkeypatch.setattr(
        push.socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))]
    )


@pytest.fixture
def uhr(monkeypatch):
    u = Uhr()
    monkeypatch.setattr(zeit, "jetzt", lambda: u.jetzt)
    return u


@pytest.fixture
def katalog(db):
    """Isolierte Ereignis-Registry mit Testtypen und dem Router; Kanäle bleiben die echten."""
    with ereignis_registry.isoliert(), registry.isoliert():
        ereignis_registry.typ_deklarieren(
            TYP_ENTSCHEIDUNG,
            modul="test",
            bezeichnung="Aufgabe gemeldet",
            zielgruppe="eltern",
            standard_kanaele=["push", "email"],
            deep_link_muster="/eltern/meldung/{instanz}/",
            entscheidung=True,
        )
        ereignis_registry.typ_deklarieren(
            TYP_INFO,
            modul="test",
            bezeichnung="Aufgabe gewählt",
            zielgruppe="eltern",
            standard_kanaele=["push", "email"],
        )
        ereignis_registry.typ_deklarieren(
            TYP_KIND,
            modul="test",
            bezeichnung="Aufgabe bestätigt",
            zielgruppe="kind",
            standard_kanaele=["push", "popup"],
            deep_link_muster="/kind/",
        )
        ereignis_registry.typ_deklarieren(
            TYP_LISTE, modul="test", bezeichnung="Nur Liste", zielgruppe="eltern"
        )
        ereignis_registry.typ_deklarieren(
            TYP_INTERN, modul="test", bezeichnung="Intern", zielgruppe="intern"
        )
        ereignis_services.typen_synchronisieren()
        ereignis_registry.alle_typen_handler_registrieren(router.router, name=router.ROUTER_NAME)
        yield ereignis_registry


@pytest.fixture
def mama(db):
    benutzer = konten_services.eltern_anlegen("Mama", rolle_label="mama", email="mama@example.org")
    konten_services.eltern_passwort_setzen(PASSWORT, von=benutzer)
    return benutzer


@pytest.fixture
def papa(db, mama):
    return konten_services.eltern_anlegen("Papa", rolle_label="papa", email="papa@example.org")


@pytest.fixture
def anna(db):
    return konten_services.kind_anlegen("Anna", PIN)


@pytest.fixture
def smtp(db):
    return services.smtp_speichern(
        host="smtp.example.org",
        port=587,
        sicherheit="starttls",
        benutzername="nestwerk@example.org",
        passwort=SMTP_PASSWORT,
        absender="nestwerk@example.org",
    )


def veroeffentlichen(typ, **kwargs):
    from django.db import transaction

    with transaction.atomic():
        return ereignis_services.veroeffentlichen(typ, **kwargs)
