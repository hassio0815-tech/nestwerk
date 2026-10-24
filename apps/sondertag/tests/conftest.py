from datetime import date, time

import pytest
from django.test import Client

from apps.konten.tests.conftest import (  # noqa: F401  (Fixtures weiterreichen)
    PIN,
    angemeldet,
    anna,
    ben,
    mama,
    papa,
)

GO_LIVE = date(2026, 10, 19)


class Uhr:
    """Steuert ``zeit.jetzt``/``zeit.heute`` über ein Datum (12:00 lokal)."""

    def __init__(self, tag):
        self.tag = tag

    def stellen(self, tag):
        self.tag = tag
        return tag


@pytest.fixture
def uhr(monkeypatch):
    from apps.kern import zeit

    u = Uhr(GO_LIVE)

    def jetzt():
        return zeit.lokal_zu_utc(u.tag, time(12, 0))

    monkeypatch.setattr(zeit, "jetzt", jetzt)
    return u


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
    """Einstellungen (echte Startwerte, Rest Beispielwerte), Ränge und Sondertag-Meilensteine;
    transaktionale Tests anderer Apps leeren die Seeds."""
    from apps.kern import einstellungen
    from apps.kern.einstellungen import startwerte_schreiben
    from apps.kern.models import Einstellung
    from apps.sondertag.einstellungen import STARTWERTE
    from apps.sondertag.meilensteine_start import anlegen
    from apps.spielregeln import raenge_start
    from apps.spielregeln.einstellungen import STARTWERTE as SPIELREGELN
    from apps.spielregeln.models import Kalibrierung, MeilensteinRegel, Rang

    Einstellung.objects.update_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )
    avatar = {"avatar.max_zaehlende_mods_woche": 1, "avatar.godmode_zyklus_aktivwochen": 26}
    for werte in (STARTWERTE, avatar, SPIELREGELN):
        startwerte_schreiben(Einstellung, werte)
    einstellungen.setzen("allgemein.go_live_datum", GO_LIVE, akteur=None)
    vorhanden = set(Einstellung.objects.values_list("schluessel", flat=True))
    for d in einstellungen.definitionen():
        if d.schluessel not in vorhanden:
            Einstellung.objects.create(
                schluessel=d.schluessel, modul=d.modul, wert=d.pruefen(_beispielwert(d))
            )
    raenge_start.anlegen(Rang, Kalibrierung)
    anlegen(MeilensteinRegel)


@pytest.fixture
def kind_client(anna):  # noqa: F811
    return angemeldet(Client(), anna)


@pytest.fixture
def eltern_client(mama, papa):  # noqa: F811
    return angemeldet(Client(), mama)
