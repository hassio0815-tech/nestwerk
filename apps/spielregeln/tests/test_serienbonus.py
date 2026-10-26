"""AP21: Serienbonus-Rechnung (reine Funktionen, Einstellungen wirken)."""

import pytest

from apps.kern import einstellungen
from apps.spielregeln import serienbonus


@pytest.mark.parametrize(
    ("serie", "prozent"), [(0, 0), (1, 0), (2, 5), (3, 10), (4, 15), (5, 20), (6, 25), (30, 25)]
)
def test_prozent_startwerte(db, serie, prozent):
    assert serienbonus.prozent(serie) == prozent


def test_einstellungen_wirken(db):
    einstellungen.setzen("spielregeln.serienbonus_start", 3, akteur=None)
    einstellungen.setzen("spielregeln.serienbonus_schritt_prozent", 10, akteur=None)
    einstellungen.setzen("spielregeln.serienbonus_deckel_prozent", 15, akteur=None)
    assert [serienbonus.prozent(s) for s in range(1, 6)] == [0, 0, 10, 15, 15]


@pytest.mark.parametrize(
    ("basis", "satz", "bonus"),
    [(10, 5, 1), (20, 5, 1), (21, 5, 2), (100, 25, 25), (0, 25, 0), (7, 0, 0)],
)
def test_aufrundung(basis, satz, bonus):
    assert serienbonus.bonus_punkte(basis, satz) == bonus
