from datetime import date

import pytest
from django.test import Client

from apps.konten import services as konten_services
from apps.konten.tests.conftest import (  # noqa: F401  (Fixtures weiterreichen)
    PIN,
    angemeldet,
    mama,
    papa,
    uhr,
)

GO_LIVE = date(2026, 10, 19)


@pytest.fixture
def kind_a(db):
    return konten_services.kind_anlegen("Testkind A", PIN)


@pytest.fixture
def kind_b(db):
    return konten_services.kind_anlegen("Testkind B", PIN)


def _beispielwert(d):
    from apps.kern.einstellungen import Typ

    if d.auswahl:
        return list(d.auswahl)[:1] if d.typ is Typ.LISTE else d.auswahl[0]
    return {
        Typ.GANZZAHL: d.minimum if d.minimum is not None else 1,
        Typ.BOOL: False,
        Typ.TEXT: "",
        Typ.DATUM: "2026-01-01",
        Typ.UHRZEIT: "12:00",
        Typ.ZEITZONE: "Europe/Berlin",
        Typ.LISTE: [],
    }[d.typ]


@pytest.fixture(autouse=True)
def startwerte(db):
    """Echte Startwerte von lernen und spielregeln, Rest Beispielwerte (andere Apps leeren die
    Seeds in transaktionalen Tests)."""
    from apps.kern import einstellungen
    from apps.kern.einstellungen import startwerte_schreiben
    from apps.kern.models import Einstellung
    from apps.lernen.einstellungen import (
        STARTWERTE,
        STARTWERTE_KI,
        STARTWERTE_MATERIAL,
        STARTWERTE_MATHE,
        STARTWERTE_MATHE_HILFE,
        STARTWERTE_PRUEFUNG,
        STARTWERTE_PUNKTE,
        STARTWERTE_TUTOR,
        STARTWERTE_UEBEN,
        STARTWERTE_WOCHE,
    )
    from apps.spielregeln import raenge_start
    from apps.spielregeln.einstellungen import STARTWERTE as SPIELREGELN
    from apps.spielregeln.models import Kalibrierung, Rang

    Einstellung.objects.update_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )
    for werte in (
        STARTWERTE,
        STARTWERTE_UEBEN,
        STARTWERTE_KI,
        STARTWERTE_MATERIAL,
        STARTWERTE_PRUEFUNG,
        STARTWERTE_TUTOR,
        STARTWERTE_WOCHE,
        STARTWERTE_MATHE,
        STARTWERTE_MATHE_HILFE,
        STARTWERTE_PUNKTE,
        SPIELREGELN,
    ):
        startwerte_schreiben(Einstellung, werte)
    einstellungen.setzen("allgemein.go_live_datum", GO_LIVE, akteur=None)
    vorhanden = set(Einstellung.objects.values_list("schluessel", flat=True))
    for d in einstellungen.definitionen():
        if d.schluessel not in vorhanden:
            Einstellung.objects.create(
                schluessel=d.schluessel, modul=d.modul, wert=d.pruefen(_beispielwert(d))
            )
    raenge_start.anlegen(Rang, Kalibrierung)
    # Die Migration stellt Runden auf Minuten; die älteren Tests rechnen in Fragen, die Tests von
    # Etappe 14 schalten selbst um (``minuten_modus``).
    einstellungen.setzen("lernen.runde_ziel", "fragen", akteur=None)


@pytest.fixture(autouse=True)
def speicher_ordner(settings, tmp_path):
    """Jeder Test schreibt in einen eigenen Ordner, nie ins echte Datenverzeichnis."""
    settings.LERNEN_SPEICHER_DIR = tmp_path / "lernmappe"
    return settings.LERNEN_SPEICHER_DIR


@pytest.fixture
def kind_client(kind_a):
    return angemeldet(Client(), kind_a)


@pytest.fixture
def eltern_client(mama):  # noqa: F811
    return angemeldet(Client(), mama)


@pytest.fixture
def fach(db):
    """Ein Fach mit zwei Themen und Vokabeln (erfunden, unabhängig von den Startdaten)."""
    from apps.lernen.models import Fach, Frage, Thema

    f = Fach.objects.create(schluessel="testsprache", name="Testsprache", reihenfolge=99)
    tiere = Thema.objects.create(fach=f, klassenstufe=5, name="Tiere")
    farben = Thema.objects.create(fach=f, klassenstufe=5, name="Farben")
    for thema, paare in (
        (tiere, [("Hund", "dog"), ("Katze", "cat"), ("Pferd", "horse")]),
        (farben, [("rot", "red"), ("blau", "blue"), ("sein", "to be / be")]),
    ):
        for de, en in paare:
            Frage.objects.create(thema=thema, typ="vokabel", frage=de, antwort=en)
    return f


class FakeTransport:
    """Ersetzt ``ki.transport.post_json``: zeichnet Aufrufe auf, liefert Antworten aus einer Liste
    (``(status, body)`` oder eine Exception). Kein echtes Netz."""

    def __init__(self):
        self.antworten = []
        self.aufrufe = []

    def __call__(self, url, *, headers, payload, timeout):
        self.aufrufe.append(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
        )
        if not self.antworten:
            return 200, {"choices": [{"message": {"content": "OK"}}], "usage": {}}
        antwort = self.antworten.pop(0)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


@pytest.fixture
def transport(monkeypatch):
    from apps.lernen.ki import transport as modul

    fake = FakeTransport()
    monkeypatch.setattr(modul, "post_json", fake)
    return fake


@pytest.fixture
def lokal(db):
    from apps.lernen import ki_services

    return ki_services.anbieter_speichern(
        name="Eigener Server",
        typ="openai_kompatibel",
        basis_url="http://dein-ki-server:11434/v1",
        modell="dein-modellname",
        akteur=None,
    )


@pytest.fixture
def cloud(db):
    from apps.lernen import ki_services

    return ki_services.anbieter_speichern(
        name="Cloud",
        typ="anthropic",
        modell="dein-modellname",
        api_key="test-schluessel-nicht-echt",
        akteur=None,
    )
