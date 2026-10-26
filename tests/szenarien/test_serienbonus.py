"""AP21 Serienbonus über die Bestätigung (aufgaben -> spielregeln -> punkte): Tabelle SPEC 18.2,
Montag-00:01-Fall (K1), Pause neutral, Deckel, Rundung, Storno, Idempotenz, Sonderpunkte."""

from datetime import date, timedelta

import pytest

from apps.aufgaben import selectors as aufgaben_selectors
from apps.aufgaben import services as aufgaben
from apps.benachrichtigung import texte
from apps.ereignisse.models import Ereignis
from apps.punkte import selectors as punkte
from apps.punkte.models import Art, Buchung
from apps.spielregeln import services
from apps.spielregeln.models import Aktivitaet, Pause
from apps.spielregeln.tests.conftest import GO_LIVE, lok

from .test_spielregeln_aufgaben import _instanz


def _aktive_wochen(kind, anzahl):
    """Aktivität am Dienstag der ersten ``anzahl`` Wochen ab Go-live."""
    for i in range(anzahl):
        Aktivitaet.objects.create(
            kind=kind, datum=GO_LIVE + timedelta(weeks=i, days=1), modul="t", referenz=str(i)
        )


def _bestaetigen(kind, mama, uhr, gemeldet, bestaetigt=None, punkte_=10, **extra):
    instanz = _instanz(mama)
    instanz.punkte_snapshot = punkte_
    instanz.save(update_fields=["punkte_snapshot"])
    uhr.stellen(gemeldet)
    aufgaben.interesse_zeigen(instanz, kind, jetzt=gemeldet)
    aufgaben.erledigt_melden(instanz, kind, jetzt=gemeldet)
    bestaetigt = uhr.stellen(bestaetigt or gemeldet + timedelta(hours=1))
    aufgaben.bestaetigen(instanz, von=mama, jetzt=bestaetigt, **extra)
    return instanz


def _bonus(instanz):
    return Buchung.objects.filter(idempotenz_schluessel=f"aufgabe:{instanz.pk}:serienbonus").first()


@pytest.mark.parametrize(
    ("vorwochen", "prozent"), [(0, 0), (1, 5), (2, 10), (3, 15), (4, 20), (5, 25), (6, 25), (9, 25)]
)
def test_tabelle_18_2_exakt(anna, mama, uhr, vorwochen, prozent):
    _aktive_wochen(anna, vorwochen)
    mittwoch = lok(2026, 10, 21, 17) + timedelta(weeks=vorwochen)
    instanz = _bestaetigen(anna, mama, uhr, mittwoch, punkte_=100)
    bonus = _bonus(instanz)
    if prozent == 0:
        assert bonus is None
        return
    assert bonus.art == Art.SERIENBONUS
    assert (bonus.guthaben_delta, bonus.xp_delta) == (prozent, prozent)
    assert bonus.begruendung == f"Serienbonus +{prozent} % (Serie {vorwochen + 1})"
    assert bonus.bezugsdatum == mittwoch.date()


@pytest.mark.parametrize(("basis", "vorwochen", "erwartet"), [(10, 1, 1), (21, 3, 4), (3, 5, 1)])
def test_aufrundung(anna, mama, uhr, basis, vorwochen, erwartet):
    _aktive_wochen(anna, vorwochen)
    mittwoch = lok(2026, 10, 21, 17) + timedelta(weeks=vorwochen)
    assert _bonus(_bestaetigen(anna, mama, uhr, mittwoch, punkte_=basis)).guthaben_delta == erwartet


def test_montag_0001_zaehlt_woche_des_meldedatums(anna, mama, uhr):
    _aktive_wochen(anna, 1)  # W43 aktiv
    # Meldung So 01.11. (W44), Bestätigung Mo 02.11. 00:01 -> Serie nach W43 + 1 = 2 -> 5 %
    instanz = _bestaetigen(anna, mama, uhr, lok(2026, 11, 1, 19), lok(2026, 11, 2, 0, 1), 100)
    assert _bonus(instanz).guthaben_delta == 5
    assert _bonus(instanz).bezugsdatum == date(2026, 11, 1)


def test_bestaetigung_nach_wochenabschluss_zaehlt_woche_der_bestaetigung(anna, mama, uhr):
    _aktive_wochen(anna, 1)  # W43 aktiv, W44 ohne Aufgabe -> Serie gerissen
    # Meldung So 01.11., Bestätigung erst Di 03.11. (Puffer vorbei) -> zählt für W45 (K1)
    instanz = _bestaetigen(anna, mama, uhr, lok(2026, 11, 1, 19), lok(2026, 11, 3, 9), 100)
    assert _bonus(instanz) is None


def test_pausenwoche_ist_neutral(anna, mama, uhr):
    _aktive_wochen(anna, 1)  # W43
    Pause.objects.create(kind=anna, von=date(2026, 10, 26), bis=date(2026, 11, 1), quelle="eltern")
    instanz = _bestaetigen(anna, mama, uhr, lok(2026, 11, 4, 17), punkte_=100)  # W45
    assert _bonus(instanz).guthaben_delta == 5


def test_gleiche_woche_gleicher_satz(anna, mama, uhr):
    _aktive_wochen(anna, 2)
    a = _bestaetigen(anna, mama, uhr, lok(2026, 11, 2, 17), punkte_=100)
    b = _bestaetigen(anna, mama, uhr, lok(2026, 11, 3, 17), punkte_=100)
    assert _bonus(a).guthaben_delta == _bonus(b).guthaben_delta == 10


def test_sonderpunkte_ohne_serienbonus(anna, mama, uhr):
    _aktive_wochen(anna, 5)
    mittwoch = lok(2026, 11, 25, 17)
    instanz = _bestaetigen(
        anna, mama, uhr, mittwoch, punkte_=10, sonderpunkte=2, begruendung="super"
    )
    assert _bonus(instanz).guthaben_delta == 3  # 25 % von 10, nicht von 12

    assert Buchung.objects.filter(art=Art.SERIENBONUS).count() == 1
    assert punkte.xp(anna) == 10 + 2 + 3


def test_storno_nimmt_bonus_mit(anna, mama, uhr):
    _aktive_wochen(anna, 1)
    instanz = _bestaetigen(anna, mama, uhr, lok(2026, 10, 28, 17), punkte_=100)
    assert punkte.xp(anna) == 105
    uhr.stellen(lok(2026, 10, 29, 9))
    aufgaben.korrigieren(instanz, von=mama, begruendung="doch nicht")
    assert punkte.salden(anna) == punkte.Saldo(guthaben=0, xp=0)
    storno = Buchung.objects.get(storno_von=_bonus(instanz))
    assert storno.xp_delta == -5
    korrigiert = Ereignis.objects.get(typ_id="aufgabe.korrigiert")
    assert korrigiert.daten["punkte"] == 105


def test_idempotent(anna, mama, uhr):
    _aktive_wochen(anna, 1)
    instanz = _bestaetigen(anna, mama, uhr, lok(2026, 10, 28, 17), punkte_=100)
    erneut = services.serienbonus_buchen(
        anna,
        basispunkte=100,
        meldedatum=date(2026, 10, 28),
        schluessel=f"aufgabe:{instanz.pk}:serienbonus",
        quelle_modul="aufgaben",
    )
    assert erneut == _bonus(instanz)
    assert Buchung.objects.filter(art=Art.SERIENBONUS).count() == 1
    assert Ereignis.objects.filter(typ_id="serienbonus.gebucht").count() == 1


def test_kind_sieht_serienbonus_im_popup_und_verlauf(anna, mama, uhr):
    _aktive_wochen(anna, 1)
    instanz = _bestaetigen(anna, mama, uhr, lok(2026, 10, 28, 17), punkte_=100)
    ereignis = Ereignis.objects.get(typ_id="serienbonus.gebucht")
    assert ereignis.kind == anna and ereignis.daten["prozent"] == 5
    titel, text = texte.rendern(ereignis, "Serienbonus")
    assert titel == "Serienbonus +5 %"
    assert text == "+5 Punkte für 2 Wochen in Folge."
    eigene = {i.pk: i for i in aufgaben_selectors.kind_eigene(anna)}
    assert eigene[instanz.pk].serienbonus.begruendung.startswith("Serienbonus +5 %")
