from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.kern import zeit
from apps.kern.einstellungen import EinstellungFehlt
from apps.kern.models import Einstellung
from apps.kern.zeit import IsoWoche

BERLIN = ZoneInfo("Europe/Berlin")


def utc(*args):
    return datetime(*args, tzinfo=UTC)


# --- heute / Mitternacht Berlin vs. UTC ------------------------------------------------------


def test_heute_mitternacht_berlin_nicht_utc():
    # Sommer: 22:30 UTC = 00:30 MESZ am Folgetag
    assert zeit.heute(utc(2026, 7, 5, 22, 30), BERLIN) == date(2026, 7, 6)
    assert zeit.heute(utc(2026, 7, 5, 21, 59), BERLIN) == date(2026, 7, 5)
    # Winter: 23:00 UTC = 00:00 MEZ am Folgetag
    assert zeit.heute(utc(2026, 1, 5, 23, 0), BERLIN) == date(2026, 1, 6)
    assert zeit.heute(utc(2026, 1, 5, 22, 59, 59), BERLIN) == date(2026, 1, 5)


def test_woche_wechselt_um_mitternacht_berlin():
    # So 05.07.2026 23:30 MESZ = 21:30 UTC -> noch W27; Mo 00:30 MESZ -> W28
    assert IsoWoche.von(utc(2026, 7, 5, 21, 30), BERLIN) == IsoWoche(2026, 27)
    assert IsoWoche.von(utc(2026, 7, 5, 22, 30), BERLIN) == IsoWoche(2026, 28)


def test_naive_zeitpunkt_wird_abgelehnt():
    with pytest.raises(ValueError):
        zeit.lokal(datetime(2026, 1, 1, 12, 0), BERLIN)


# --- Sommer-/Winterzeit ----------------------------------------------------------------------


def test_tag_der_sommerzeit_umstellung_hat_23_stunden():
    beginn, ende = zeit.tag_intervall(date(2026, 3, 29), BERLIN)
    assert beginn == utc(2026, 3, 28, 23, 0)
    assert ende == utc(2026, 3, 29, 22, 0)
    assert ende - beginn == timedelta(hours=23)


def test_tag_der_winterzeit_umstellung_hat_25_stunden():
    beginn, ende = zeit.tag_intervall(date(2026, 10, 25), BERLIN)
    assert beginn == utc(2026, 10, 24, 22, 0)
    assert ende == utc(2026, 10, 25, 23, 0)
    assert ende - beginn == timedelta(hours=25)


def test_wochen_mit_zeitumstellung_haben_167_bzw_169_stunden():
    beginn, ende = IsoWoche(2026, 13).intervall(BERLIN)  # 23.–29.03.2026
    assert ende - beginn == timedelta(hours=167)
    beginn, ende = IsoWoche(2026, 43).intervall(BERLIN)  # 19.–25.10.2026
    assert ende - beginn == timedelta(hours=169)
    beginn, ende = IsoWoche(2026, 44).intervall(BERLIN)
    assert ende - beginn == timedelta(hours=168)


def test_heute_rund_um_die_umstellung():
    # 25.10.2026: 00:30 UTC = 02:30 MESZ, 01:30 UTC = 02:30 MEZ -> beides der 25.
    assert zeit.heute(utc(2026, 10, 25, 0, 30), BERLIN) == date(2026, 10, 25)
    assert zeit.heute(utc(2026, 10, 25, 1, 30), BERLIN) == date(2026, 10, 25)
    assert zeit.heute(utc(2026, 10, 25, 22, 59), BERLIN) == date(2026, 10, 25)
    assert zeit.heute(utc(2026, 10, 25, 23, 0), BERLIN) == date(2026, 10, 26)


def test_uhrzeit_in_der_luecke_wird_nach_vorn_verschoben():
    # 29.03.2026 02:30 gibt es nicht -> 03:30 MESZ = 01:30 UTC
    moment = zeit.lokal_zu_utc(date(2026, 3, 29), time(2, 30), BERLIN)
    assert moment == utc(2026, 3, 29, 1, 30)
    assert zeit.lokal(moment, BERLIN).time() == time(3, 30)


def test_doppelte_uhrzeit_nimmt_erstes_auftreten():
    # 25.10.2026 02:30 gibt es zweimal -> erstes Auftreten (MESZ) = 00:30 UTC
    assert zeit.lokal_zu_utc(date(2026, 10, 25), time(2, 30), BERLIN) == utc(2026, 10, 25, 0, 30)


# --- ISO-Woche 53 und Jahreswechsel ----------------------------------------------------------


@pytest.mark.parametrize(
    ("jahr", "anzahl"),
    [(2015, 53), (2020, 53), (2024, 52), (2025, 52), (2026, 53), (2027, 52), (2032, 53)],
)
def test_anzahl_iso_wochen(jahr, anzahl):
    assert zeit.anzahl_iso_wochen(jahr) == anzahl


def test_woche_53_ueber_den_jahreswechsel():
    w53 = IsoWoche(2026, 53)
    assert w53.montag == date(2026, 12, 28)
    assert w53.sonntag == date(2027, 1, 3)
    assert IsoWoche.von(date(2027, 1, 1)) == w53
    assert IsoWoche.von(date(2027, 1, 3)) == w53
    assert IsoWoche.von(date(2027, 1, 4)) == IsoWoche(2027, 1)
    assert w53.naechste() == IsoWoche(2027, 1)
    assert IsoWoche(2027, 1).vorherige() == w53
    assert IsoWoche(2026, 52).naechste() == w53
    assert len(w53.tage()) == 7 and w53.tage()[3] == date(2026, 12, 31)


def test_jahreswechsel_ohne_woche_53():
    assert IsoWoche.von(date(2024, 12, 30)) == IsoWoche(2025, 1)
    assert IsoWoche(2025, 52).naechste() == IsoWoche(2026, 1)
    assert IsoWoche(2026, 1).montag == date(2025, 12, 29)


def test_woche_53_existiert_nicht_in_jedem_jahr():
    with pytest.raises(ValueError):
        IsoWoche(2025, 53)
    with pytest.raises(ValueError):
        IsoWoche(2026, 0)


def test_iso_woche_sortierung_und_text():
    assert IsoWoche(2026, 53) < IsoWoche(2027, 1) < IsoWoche(2027, 2)
    assert str(IsoWoche(2027, 1)) == "2027-W01"


def test_woche_53_intervall_in_utc():
    beginn, ende = IsoWoche(2026, 53).intervall(BERLIN)
    assert beginn == utc(2026, 12, 27, 23, 0)
    assert ende == utc(2027, 1, 3, 23, 0)


# --- App-Jahr --------------------------------------------------------------------------------

GO_LIVE = date(2026, 11, 1)


def test_app_jahr_grenzen():
    j1 = zeit.app_jahr(date(2026, 11, 1), GO_LIVE)
    assert (j1.nummer, j1.beginn, j1.ende) == (1, date(2026, 11, 1), date(2027, 11, 1))
    assert zeit.app_jahr(date(2027, 10, 31), GO_LIVE).nummer == 1
    assert zeit.app_jahr(date(2027, 11, 1), GO_LIVE).nummer == 2
    assert zeit.app_jahr(date(2030, 6, 1), GO_LIVE).nummer == 4
    assert j1.enthaelt(date(2027, 10, 31)) and not j1.enthaelt(date(2027, 11, 1))


def test_app_jahr_vor_go_live():
    with pytest.raises(zeit.VorGoLive):
        zeit.app_jahr(date(2026, 10, 31), GO_LIVE)


def test_app_jahr_grenze_um_mitternacht_berlin():
    # 31.10.2027 23:30 UTC = 01.11.2027 00:30 MEZ -> App-Jahr 2
    assert zeit.app_jahr(utc(2027, 10, 31, 23, 30), GO_LIVE, BERLIN).nummer == 2
    assert zeit.app_jahr(utc(2027, 10, 31, 22, 59), GO_LIVE, BERLIN).nummer == 1


def test_app_jahr_bei_go_live_am_29_februar():
    go_live = date(2028, 2, 29)
    j2 = zeit.app_jahr_nummer(2, go_live)
    assert (j2.beginn, j2.ende) == (date(2029, 2, 28), date(2030, 2, 28))
    assert zeit.app_jahr(date(2029, 2, 27), go_live).nummer == 1
    assert zeit.app_jahr(date(2029, 2, 28), go_live).nummer == 2
    assert zeit.app_jahr_nummer(5, go_live).beginn == date(2032, 2, 29)
    assert zeit.app_jahr(date(2032, 2, 28), go_live).nummer == 4


def test_app_jahre_lueckenlos():
    for n in range(1, 30):
        assert zeit.app_jahr_nummer(n, GO_LIVE).ende == zeit.app_jahr_nummer(n + 1, GO_LIVE).beginn


# --- Einstellungen als Quelle ----------------------------------------------------------------


def test_zeitzone_und_go_live_aus_einstellungen(kern_werte):
    assert zeit.zeitzone() == BERLIN
    assert zeit.heute(utc(2026, 7, 5, 22, 30)) == date(2026, 7, 6)
    assert zeit.app_jahr(date(2027, 11, 1)).nummer == 2


def test_andere_zeitzone_aus_einstellung(kern_werte):
    Einstellung.objects.filter(schluessel="allgemein.zeitzone").update(wert="America/New_York")
    assert zeit.heute(utc(2026, 7, 6, 2, 0)) == date(2026, 7, 5)


@pytest.mark.django_db
def test_ohne_zeitzonen_wert_klarer_fehler():
    with pytest.raises(EinstellungFehlt, match="allgemein.zeitzone"):
        zeit.heute()
