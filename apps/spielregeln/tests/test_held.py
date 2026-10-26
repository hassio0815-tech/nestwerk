"""Held der Woche (AP30): relativer Zuwachs, Pause, Gleichstand, Historie, Idempotenz."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from apps.ereignisse.models import Ereignis
from apps.kern.zeit import IsoWoche
from apps.spielregeln import held, selectors
from apps.spielregeln.events import HELD, HELD_KIND
from apps.spielregeln.models import Wochenauswertung

START = date(2026, 10, 19)  # Montag W43


def _woche(i):
    return IsoWoche.von(START + timedelta(days=7 * i))


def zeile(kind, i, xp, *, aktiv=True, pausentage=0, neutral=False, final=True):
    w = _woche(i)
    return Wochenauswertung.objects.create(
        kind=kind,
        iso_jahr=w.jahr,
        iso_woche=w.woche,
        montag=w.montag,
        aktiv=aktiv,
        neutral=neutral,
        pausentage=pausentage,
        xp_woche=xp,
        wochenserie_danach=1,
        aktive_wochen_gesamt=i + 1,
        finalisiert_am=datetime(2026, 12, 1, tzinfo=UTC) if final else None,
    )


def lauf(i_aktuell):
    """Job, als wäre jetzt Woche ``i_aktuell`` (Mittwoch)."""
    jetzt = datetime.combine(_woche(i_aktuell).montag + timedelta(days=2), datetime.min.time(), UTC)
    return held.sicherstellen(jetzt)


def helden_namen(i):
    return sorted(z.kind.anzeigename for z in selectors.helden(_woche(i)))


def test_zuwachs_ist_relativ_zum_eigenen_schnitt(anna, ben):
    for i in range(4):  # Anna schafft sonst 200, Ben 80
        zeile(anna, i, 200)
        zeile(ben, i, 80)
    zeile(anna, 4, 260)  # +30 %
    zeile(ben, 4, 140)  # +75 %  (absolut weniger, relativ mehr)
    lauf(5)
    assert helden_namen(4) == ["Ben"]
    z = {z.kind.anzeigename: z.zuwachs_relativ for z in selectors.zuwaechse(_woche(4))}
    assert z == {"Anna": Decimal("0.300"), "Ben": Decimal("0.750")}


def test_pausiertes_kind_ist_ausgenommen(anna, ben):
    for i in range(3):
        zeile(anna, i, 100)
        zeile(ben, i, 100)
    zeile(anna, 3, 300, pausentage=2)  # pausiert: trotz Rekord kein Held
    zeile(ben, 3, 120)
    lauf(4)
    assert helden_namen(3) == ["Ben"]
    zeilen = {z.kind.anzeigename for z in selectors.zuwaechse(_woche(3))}
    assert zeilen == {"Ben"}


def test_gleichstand_mehrere_helden(anna, ben):
    for i in range(3):
        zeile(anna, i, 100)
        zeile(ben, i, 200)
    zeile(anna, 3, 150)
    zeile(ben, 3, 300)  # beide +50 %
    lauf(4)
    assert helden_namen(3) == ["Anna", "Ben"]


def test_zu_wenig_historie_einfache_regel(anna, ben):
    # Erste Woche: Mindestbasis 50 statt Schnitt -> verglichen wird nach Punkten
    zeile(anna, 0, 100)
    zeile(ben, 0, 150)
    lauf(1)
    assert helden_namen(0) == ["Ben"]
    assert held.zuwachs(100, [], min_wochen=2, basis=50) == Decimal("1.000")
    # eine Woche Historie reicht noch nicht (min 2): weiter Mindestbasis
    assert held.zuwachs(100, [400], min_wochen=2, basis=50) == Decimal("1.000")
    assert held.zuwachs(100, [400, 400], min_wochen=2, basis=50) == Decimal("-0.750")


def test_niemand_ueber_dem_schnitt_kein_held(anna, ben):
    for i in range(3):
        zeile(anna, i, 200)
        zeile(ben, i, 200)
    zeile(anna, 3, 100)
    zeile(ben, 3, 0, aktiv=False)
    lauf(4)
    assert helden_namen(3) == []


def test_unfertige_woche_wird_nicht_bewertet(anna, ben):
    zeile(anna, 0, 100)
    zeile(ben, 0, 150, final=False)
    lauf(1)
    assert helden_namen(0) == []
    assert not selectors.zuwaechse(_woche(0))


def test_laufende_woche_wird_nicht_bewertet(anna):
    zeile(anna, 0, 100)
    lauf(0)
    assert helden_namen(0) == []


@pytest.mark.django_db
def test_idempotent_und_ereignisse_genau_einmal(anna, ben):
    zeile(anna, 0, 100)
    zeile(ben, 0, 150)
    lauf(1)
    lauf(1)
    lauf(1)
    assert helden_namen(0) == ["Ben"]
    assert Ereignis.objects.filter(typ__slug=HELD).count() == 1
    assert Ereignis.objects.filter(typ__slug=HELD_KIND, kind=ben).count() == 1
    # Spätere XP-Korrektur ändert den gespeicherten Fakt nicht mehr
    Wochenauswertung.objects.filter(kind=anna).update(xp_woche=999)
    lauf(1)
    assert helden_namen(0) == ["Ben"]


def test_alte_wochen_ohne_ereignisse(anna):
    zeile(anna, 0, 100)
    lauf(5)  # Woche 0 ist länger her: Fakt ja, Pop-up nein
    assert helden_namen(0) == ["Anna"]
    assert not Ereignis.objects.filter(typ__slug=HELD_KIND).exists()


def test_held_titel_zaehlt(anna):
    zeile(anna, 0, 100)
    lauf(1)
    assert selectors.held_titel(anna) == 1


def test_einstellungen_wirken(anna, ben):
    from apps.kern import einstellungen

    einstellungen.setzen("spielregeln.held_basis_wochen", 1, akteur=None)
    zeile(anna, 0, 400)
    zeile(anna, 1, 100)
    zeile(anna, 2, 150)  # N=1 und min_wochen=2: nur eine Historienwoche -> Mindestbasis 50
    lauf(3)
    z = selectors.zuwaechse(_woche(2))[0]
    assert z.zuwachs_relativ == Decimal("2.000")
