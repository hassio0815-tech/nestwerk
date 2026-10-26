"""AP32 Rang-Prognose: reine Rechnung (Engpass, Historie), faktor_wochen (P-07), Kind-Kachel."""

from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from apps.kern import einstellungen
from apps.kern.models import AuditEintrag
from apps.spielregeln import prognose, selectors, services
from apps.spielregeln.models import Aktivitaet, Kalibrierung, Wochenauswertung

from .conftest import GO_LIVE, lok
from .test_raenge import _stufen, _wochen, _xp

STICHTAG = date(2026, 12, 1)


@pytest.fixture(autouse=True)
def prognose_einstellungen(db):
    for schluessel, wert in {
        "spielregeln.prognose_wochen": 6,
        "spielregeln.prognose_min_wochen": 3,
        "spielregeln.prognose_ziel_sondertage": 2,
        "spielregeln.prognose_kind_zeigen": True,
    }.items():
        einstellungen.setzen(schluessel, wert, akteur=None)


def _basis(xp=175, quote=1, wochen=6):
    return prognose.Basis(wochen, Fraction(xp), Fraction(quote), wochen >= 3)


STUFEN = [prognose.StufeBedarf(2, "Uncommon", 2000, 20), prognose.StufeBedarf(3, "Rare", 5000, 42)]


def test_engpass_wochen_bei_normalem_fleiss():
    z = prognose.rang_ziele(_basis(), xp=1000, aktive_wochen=10, stufen=STUFEN, stichtag=STICHTAG)
    assert z[0].engpass == "wochen"  # 1000 XP fehlen = 6 Wochen, 10 Aktivwochen fehlen
    assert (z[0].wochen_xp, z[0].wochen_aktiv, z[0].wochen) == (6, 10, 10)
    assert z[0].datum == STICHTAG + timedelta(weeks=10)
    assert not prognose.xp_bindet(z)


def test_engpass_xp_bei_wenig_punkten_und_beides():
    z = prognose.rang_ziele(
        _basis(xp=50), xp=1000, aktive_wochen=10, stufen=STUFEN[:1], stichtag=STICHTAG
    )
    assert z[0].engpass == "xp" and z[0].wochen == 20 and prognose.xp_bindet(z)
    z = prognose.rang_ziele(
        _basis(xp=100), xp=1000, aktive_wochen=10, stufen=STUFEN[:1], stichtag=STICHTAG
    )
    assert z[0].engpass == "beides" and z[0].wochen == 10


def test_aktivquote_verlaengert_die_wochen():
    z = prognose.rang_ziele(
        _basis(quote=Fraction(1, 2)),
        xp=2000,
        aktive_wochen=10,
        stufen=STUFEN[:1],
        stichtag=STICHTAG,
    )
    assert z[0].wochen == 20 and z[0].engpass == "wochen"


def test_zu_wenig_historie_gibt_hinweis_statt_zahl():
    b = prognose.Basis(2, Fraction(100), Fraction(1), False)
    assert prognose.rang_ziele(b, xp=0, aktive_wochen=0, stufen=STUFEN, stichtag=STICHTAG) == []
    assert "Zu wenig Verlauf" in b.hinweis


def test_kein_tempo_keine_zahl():
    b = prognose.Basis(6, Fraction(0), Fraction(0), True)
    z = prognose.rang_ziele(b, xp=0, aktive_wochen=0, stufen=STUFEN[:1], stichtag=STICHTAG)
    assert z[0].wochen is None and z[0].datum is None


def test_basis_aus_wochenauswertungen_reproduzierbar(anna):
    for i in range(8):
        montag = GO_LIVE + timedelta(weeks=i)
        Wochenauswertung.objects.create(
            kind=anna, iso_jahr=montag.isocalendar()[0], iso_woche=montag.isocalendar()[1],
            montag=montag, aktiv=i % 2 == 0, neutral=i == 7, pausentage=0, xp_woche=100 * (i + 1),
            wochenserie_danach=0, aktive_wochen_gesamt=0,
        )  # fmt: skip
    stichtag = GO_LIVE + timedelta(weeks=8, days=2)
    a, b = prognose.basis(anna, stichtag), prognose.basis(anna, stichtag)
    assert a == b
    # neutrale Woche 7 zählt nicht; die letzten 6 sind Wochen 1..6 (Index)
    assert a.wochen == 6 and a.xp_schnitt == Fraction(100 * (2 + 3 + 4 + 5 + 6 + 7), 6)
    assert a.aktivquote == Fraction(3, 6)
    # eine spätere Woche (nach dem Stichtag) ändert die Basis nicht
    assert prognose.basis(anna, GO_LIVE + timedelta(weeks=3, days=2)).wochen == 3


def test_faktor_wochen_wirkt_auf_rangaufstieg(anna, mama, uhr):
    _xp(anna, 2500)
    _wochen(anna, uhr, 10)
    assert _stufen(anna) == []  # 10 < 20 Aktivwochen
    assert selectors.rang_fortschritt(anna).wochen_fehlen == 10
    services.wochen_faktor_setzen(anna, "0,5", von=mama, notiz="Test")
    assert _stufen(anna) == [2]  # sofort geprüft
    assert selectors.rang_fortschritt(anna).naechster.stufe == 3
    assert selectors.wochen_faktor(anna) == Decimal("0.50")
    assert selectors.kind_wochen_faktor(anna) == Decimal("0.50")
    eintrag = AuditEintrag.objects.filter(aktion="kalibrierung.wochen_geaendert").get()
    assert eintrag.details["neu"] == "0.50" and eintrag.details["alt"] == "1.00"


def test_faktor_wochen_global_mal_kind_und_aufrunden(anna, mama):
    services.wochen_faktor_setzen(None, "0,9", von=mama)
    services.wochen_faktor_setzen(anna, "0,9", von=mama)
    rang = selectors.raenge()[2]  # Rare: 42 Wochen
    assert selectors.wirksame_wochen(rang, selectors.wochen_faktor(anna)) == 35  # ceil(34,02)
    services.wochen_faktor_setzen(anna, None, von=mama)
    assert selectors.kind_wochen_faktor(anna) is None


def test_schwellen_faktor_entfernen_behaelt_wochenfaktor(anna, mama):
    services.wochen_faktor_setzen(anna, "0,8", von=mama)
    services.kalibrierung_setzen(anna, "0,7", von=mama)
    services.kalibrierung_setzen(anna, None, von=mama)
    assert selectors.kind_wochen_faktor(anna) == Decimal("0.80")
    assert selectors.kind_faktor(anna) == Decimal("1.00")
    assert Kalibrierung.objects.filter(kind=anna).count() == 1


def test_faktor_nur_von_eltern(anna, ben):
    with pytest.raises(services.RangFehler):
        services.wochen_faktor_setzen(anna, "0,9", von=ben)
    with pytest.raises(services.RangFehler):
        services.wochen_faktor_setzen(anna, "9", von=None)


def test_kind_kachel_zeigt_nur_wochen(kind_client, anna, uhr):
    for i in range(6):
        montag = GO_LIVE + timedelta(weeks=i)
        Aktivitaet.objects.create(kind=anna, datum=montag, modul="t", referenz=f"p{i}")
        _xp(anna, 150)
    uhr.stellen(lok(2026, 10, 21, 12) + timedelta(weeks=6))
    services.wochen_sicherstellen(anna)
    html = kind_client.get("/kind/dungeon/").content.decode()
    assert "Nächster Rang voraussichtlich in ca." in html
    for verboten in ("Engpass", "Faktor", "Kalibrierung", "Ampel", "Aktivquote"):
        assert verboten not in html
    einstellungen.setzen("spielregeln.prognose_kind_zeigen", False, akteur=None)
    assert "Nächster Rang voraussichtlich" not in kind_client.get("/kind/dungeon/").content.decode()


def test_kind_kachel_ohne_historie_keine_prognose(kind_client, anna, uhr):
    assert "Nächster Rang voraussichtlich" not in kind_client.get("/kind/dungeon/").content.decode()
