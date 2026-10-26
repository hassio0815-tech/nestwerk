"""Zustandsautomat: alle erlaubten und alle verbotenen Übergänge (zentrale Tabelle)."""

from itertools import product

import pytest

from apps.aufgaben import wiederholung, zustand
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus

S = InstanzStatus
ERWARTET = {
    (S.OFFEN, S.RESERVIERT),
    (S.OFFEN, S.NICHT_UEBERNOMMEN),
    (S.RESERVIERT, S.KONFLIKT),
    (S.RESERVIERT, S.OFFEN),
    (S.RESERVIERT, S.NICHT_UEBERNOMMEN),
    (S.RESERVIERT, S.GEMELDET),
    (S.RESERVIERT, S.BESTAETIGT),
    (S.KONFLIKT, S.RESERVIERT),
    (S.KONFLIKT, S.OFFEN),
    (S.KONFLIKT, S.NICHT_UEBERNOMMEN),
    (S.GEMELDET, S.BESTAETIGT),
    (S.GEMELDET, S.ABGELEHNT),
    (S.GEMELDET, S.RUECKFRAGE),
    (S.RUECKFRAGE, S.GEMELDET),
    (S.RUECKFRAGE, S.BESTAETIGT),
    (S.RUECKFRAGE, S.ABGELEHNT),
    (S.BESTAETIGT, S.STORNIERT),
    (S.BESTAETIGT, S.NACHBESSERN),
    (S.NACHBESSERN, S.GEMELDET),
    (S.NACHBESSERN, S.STORNIERT),
}
ALLE = list(product(S.values, S.values))


def test_tabelle_entspricht_dem_diagramm():
    tabelle = {(v, n) for v, ziele in zustand.UEBERGAENGE.items() for n in ziele}
    assert tabelle == ERWARTET
    assert set(zustand.UEBERGAENGE) == set(S.values)
    assert zustand.ENDZUSTAENDE == {S.ABGELEHNT, S.NICHT_UEBERNOMMEN, S.STORNIERT}


@pytest.fixture
def instanz(mama):
    aufgabe = Aufgabe.objects.create(
        titel="Test", punkte=10, erstellt_von=mama, wiederholungsart=wiederholung.EINMALIG
    )
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe, titel_snapshot="Test", punkte_snapshot=10, freigabeart_snapshot="eltern"
    )


@pytest.mark.parametrize(("von", "nach"), ALLE)
def test_jeder_uebergang(instanz, von, nach):
    AufgabenInstanz.objects.filter(pk=instanz.pk).update(status=von)
    instanz.refresh_from_db()
    if (von, nach) in ERWARTET:
        zustand.uebergang(instanz, nach)
        instanz.refresh_from_db()
        assert instanz.status == nach
    else:
        with pytest.raises(zustand.UngueltigerUebergang):
            zustand.uebergang(instanz, nach)
        instanz.refresh_from_db()
        assert instanz.status == von


def test_veralteter_stand_scheitert_am_bedingten_update(instanz):
    kopie = AufgabenInstanz.objects.get(pk=instanz.pk)
    zustand.uebergang(instanz, S.RESERVIERT)
    with pytest.raises(zustand.UngueltigerUebergang, match="inzwischen"):
        zustand.uebergang(kopie, S.RESERVIERT)  # Objekt glaubt noch an "offen"
