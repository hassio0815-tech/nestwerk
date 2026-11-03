"""Tagesziel, Anpassung, Schonung und Wochenserie (SPEC 21.2)."""

from datetime import date, timedelta

import pytest

from apps.kern import einstellungen
from apps.lernen import services, tagesziel
from apps.lernen.models import Lernpause, Lerntag, Lernziel, PausenGrund

HEUTE = date(2026, 10, 23)  # Freitag, Woche ab Montag 19.10.


def tag(kind, datum, *, erreicht=False, mindest=None, minuten=20):
    mindest = erreicht if mindest is None else mindest
    return Lerntag.objects.create(
        kind=kind,
        datum=datum,
        sekunden=minuten * 60,
        ziel_minuten=20,
        mindesttag=mindest,
        erreicht=erreicht,
    )


def ziel(kind, *, seit, minuten=20, **extra):
    return Lernziel.objects.create(kind=kind, ziel_minuten=minuten, seit=seit, **extra)


# --- Ziel und Lerntag -----------------------------------------------------------------------


def test_ziel_startet_bei_der_familieneinstellung(kind_a):
    z = tagesziel.ziel_holen(kind_a, HEUTE)
    assert (z.ziel_minuten, z.seit) == (20, HEUTE)
    assert tagesziel.ziel_holen(kind_a, HEUTE).pk == z.pk


def test_lerntag_folgt_dem_ziel_bis_es_erreicht_ist(kind_a):
    z = tagesziel.ziel_holen(kind_a, HEUTE)
    t = tagesziel.lerntag_holen(kind_a, HEUTE)
    assert t.ziel_minuten == 20
    z.ziel_minuten = 10
    z.save()
    assert tagesziel.lerntag_holen(kind_a, HEUTE).ziel_minuten == 10
    t.refresh_from_db()
    t.erreicht = True
    t.save()
    z.ziel_minuten = 5
    z.save()
    assert tagesziel.lerntag_holen(kind_a, HEUTE).ziel_minuten == 10  # erreicht: eingefroren


# --- Anpassen ---------------------------------------------------------------------------------


def test_ohne_vergangene_tage_bleibt_alles(kind_a):
    ziel(kind_a, seit=HEUTE)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE
    ziel_ = Lernziel.objects.get(kind=kind_a)
    ziel_.seit = HEUTE - timedelta(days=1)
    ziel_.save()
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE


def test_nach_zwei_verfehlten_tagen_wird_das_ziel_gesenkt(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=4))
    tag(kind_a, HEUTE - timedelta(days=4), erreicht=True)
    a = tagesziel.ziel_anpassen(kind_a, HEUTE)
    assert (a.art, a.minuten) == ("gesenkt", 15)
    z = Lernziel.objects.get(kind=kind_a)
    assert (z.ziel_minuten, z.geaendert_am) == (15, HEUTE)
    # Gleicher Tag noch einmal: kein zweites Senken (das Fenster beginnt neu)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE


def test_ein_erreichter_tag_verhindert_das_senken(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=4))
    tag(kind_a, HEUTE - timedelta(days=1), erreicht=True)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE
    assert Lernziel.objects.get(kind=kind_a).ziel_minuten == 20


def test_ein_verfehlter_tag_reicht_nicht(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=2))
    # Nur gestern zählt (der Starttag selbst nicht)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE


def test_ziel_sinkt_nie_unter_den_mindesttag(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=5), minuten=7)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE).minuten == 5  # Mindesttag 5
    ziel_ = Lernziel.objects.get(kind=kind_a)
    ziel_.geaendert_am = HEUTE - timedelta(days=4)
    ziel_.save()
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE  # schon am Boden


def test_schonungstage_zaehlen_nicht_als_verfehlt(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=4))
    Lernpause.objects.create(
        kind=kind_a, von=HEUTE - timedelta(days=3), bis=HEUTE - timedelta(days=1), grund="krank"
    )
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE
    assert Lernziel.objects.get(kind=kind_a).ziel_minuten == 20


def test_senken_laesst_einen_offenen_vorschlag_verschwinden(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=4), vorschlag_minuten=25)
    tagesziel.ziel_anpassen(kind_a, HEUTE)
    assert Lernziel.objects.get(kind=kind_a).vorschlag_minuten is None


def test_vorschlag_nach_vielen_erreichten_tagen(kind_a):
    ziel(
        kind_a, seit=HEUTE - timedelta(days=14), minuten=10, geaendert_am=HEUTE - timedelta(days=14)
    )
    for i in range(1, 10):
        tag(kind_a, HEUTE - timedelta(days=i), erreicht=True)
    a = tagesziel.ziel_anpassen(kind_a, HEUTE)
    assert (a.art, a.minuten) == ("vorschlag", 15)
    z = Lernziel.objects.get(kind=kind_a)
    assert (z.ziel_minuten, z.vorschlag_minuten) == (10, 15)  # nur Vorschlag, nicht gesetzt
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE  # kein zweiter Vorschlag


def test_vorschlag_nie_ueber_dem_familienziel(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=14), minuten=18)
    for i in range(1, 10):
        tag(kind_a, HEUTE - timedelta(days=i), erreicht=True)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE).minuten == 20


def test_kein_vorschlag_wenn_das_ziel_schon_voll_ist_oder_zu_wenig_geuebt(kind_a):
    ziel(kind_a, seit=HEUTE - timedelta(days=14), minuten=20)
    for i in range(1, 10):
        tag(kind_a, HEUTE - timedelta(days=i), erreicht=True)
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE
    z = Lernziel.objects.get(kind=kind_a)
    z.ziel_minuten = 10
    z.save()
    Lerntag.objects.filter(kind=kind_a).exclude(datum__gte=HEUTE - timedelta(days=4)).delete()
    assert tagesziel.ziel_anpassen(kind_a, HEUTE) == tagesziel.KEINE


def test_vorschlag_annehmen_oder_lassen(kind_a):
    ziel(kind_a, seit=HEUTE, minuten=10, vorschlag_minuten=15)
    z = tagesziel.vorschlag_entscheiden(kind_a, HEUTE, annehmen=True)
    assert (z.ziel_minuten, z.vorschlag_minuten, z.geaendert_am) == (15, None, HEUTE)
    z.vorschlag_minuten = 20
    z.save()
    z = tagesziel.vorschlag_entscheiden(kind_a, HEUTE, annehmen=False)
    assert (z.ziel_minuten, z.vorschlag_minuten) == (15, None)
    assert tagesziel.vorschlag_entscheiden(kind_a, HEUTE, annehmen=True).ziel_minuten == 15


def test_service_vorschlag_entscheiden(kind_a):
    ziel(kind_a, seit=HEUTE, minuten=10, vorschlag_minuten=15)
    services.vorschlag_entscheiden(kind_a, annehmen=True, heute=HEUTE)
    assert Lernziel.objects.get(kind=kind_a).ziel_minuten == 15


# --- Schonung --------------------------------------------------------------------------------


def test_pausentage_fuer_kind_und_alle(kind_a, kind_b):
    Lernpause.objects.create(kind=kind_a, von=HEUTE, bis=HEUTE + timedelta(days=1))
    Lernpause.objects.create(kind=kind_b, von=HEUTE, bis=HEUTE + timedelta(days=5))
    Lernpause.objects.create(
        kind=None, von=HEUTE - timedelta(days=9), bis=HEUTE - timedelta(days=8)
    )
    Lernpause.objects.create(kind=None, von=HEUTE + timedelta(days=3))  # offen
    tage = tagesziel.pausentage(kind_a, HEUTE - timedelta(days=9), HEUTE + timedelta(days=4))
    assert HEUTE in tage and HEUTE + timedelta(days=1) in tage
    assert HEUTE + timedelta(days=2) not in tage  # Pause von kind_b gilt nicht
    assert HEUTE - timedelta(days=9) in tage  # für alle
    assert HEUTE + timedelta(days=4) in tage  # offene Pause
    assert tagesziel.ist_pausentag(kind_a, HEUTE)
    assert not tagesziel.ist_pausentag(kind_a, HEUTE - timedelta(days=1))


def test_pause_eintragen_und_loeschen(kind_a):
    p = services.pause_eintragen(kind_a, HEUTE, HEUTE + timedelta(days=2), PausenGrund.KRANK)
    assert tagesziel.ist_pausentag(kind_a, HEUTE + timedelta(days=2))
    services.pause_loeschen(p)
    assert not tagesziel.ist_pausentag(kind_a, HEUTE)
    with pytest.raises(services.LernenFehler):
        services.pause_eintragen(kind_a, HEUTE, HEUTE - timedelta(days=1))
    with pytest.raises(services.LernenFehler):
        services.pause_eintragen(kind_a, HEUTE, HEUTE, grund="egal")


def test_ferien_schalter_legt_offene_pause_an_und_beendet_sie(kind_a):
    tagesziel.ferien_abgleichen(HEUTE)
    assert Lernpause.objects.count() == 0
    einstellungen.setzen("lernen.ferien_schalter", True, akteur=None)
    tagesziel.ferien_abgleichen(HEUTE)
    tagesziel.ferien_abgleichen(HEUTE + timedelta(days=1))  # idempotent
    p = Lernpause.objects.get()
    assert (p.kind, p.von, p.bis, p.grund) == (None, HEUTE, None, PausenGrund.FERIEN)
    einstellungen.setzen("lernen.ferien_schalter", False, akteur=None)
    tagesziel.ferien_abgleichen(HEUTE + timedelta(days=3))
    p.refresh_from_db()
    assert p.bis == HEUTE + timedelta(days=2)
    tagesziel.ferien_abgleichen(HEUTE + timedelta(days=4))  # nichts Offenes mehr
    assert Lernpause.objects.count() == 1


def test_ferien_am_selben_tag_wieder_aus_entfernt_die_pause(kind_a):
    einstellungen.setzen("lernen.ferien_schalter", True, akteur=None)
    tagesziel.ferien_abgleichen(HEUTE)
    einstellungen.setzen("lernen.ferien_schalter", False, akteur=None)
    tagesziel.ferien_abgleichen(HEUTE)
    assert Lernpause.objects.count() == 0


# --- Wochenserie -----------------------------------------------------------------------------


def woche(kind, montag, tage):
    for i in tage:
        tag(kind, montag + timedelta(days=i), erreicht=True)


M0 = date(2026, 10, 19)  # Montag der Woche von HEUTE


def test_ohne_ziel_keine_serie(kind_a):
    assert tagesziel.serie(kind_a, HEUTE) == tagesziel.Serie(0, 0, 3, False)


def test_serie_zaehlt_wochen_in_folge(kind_a):
    ziel(kind_a, seit=M0 - timedelta(weeks=3))
    woche(kind_a, M0 - timedelta(weeks=3), [0, 2, 4])
    woche(kind_a, M0 - timedelta(weeks=2), [1, 2, 3])
    woche(kind_a, M0 - timedelta(weeks=1), [0, 1, 2, 3])
    s = tagesziel.serie(kind_a, HEUTE)
    assert (s.wochen, s.tage_diese_woche, s.bedarf, s.geschont) == (3, 0, 3, False)
    woche(kind_a, M0, [0, 1, 2])  # laufende Woche reicht jetzt
    s = tagesziel.serie(kind_a, HEUTE)
    assert (s.wochen, s.tage_diese_woche) == (4, 3)


def test_laufende_woche_bricht_die_serie_nicht(kind_a):
    ziel(kind_a, seit=M0 - timedelta(weeks=1))
    woche(kind_a, M0 - timedelta(weeks=1), [0, 1, 2])
    woche(kind_a, M0, [0])
    assert tagesziel.serie(kind_a, HEUTE).wochen == 1


def test_gerissene_serie_beginnt_von_vorn_und_nimmt_nie_punkte(kind_a):
    ziel(kind_a, seit=M0 - timedelta(weeks=4))
    woche(kind_a, M0 - timedelta(weeks=4), [0, 1, 2])
    woche(kind_a, M0 - timedelta(weeks=3), [0, 1, 2])
    # Woche -2 verfehlt (nur ein Tag), Woche -1 geschafft
    woche(kind_a, M0 - timedelta(weeks=2), [0])
    woche(kind_a, M0 - timedelta(weeks=1), [0, 1, 2])
    assert tagesziel.serie(kind_a, HEUTE).wochen == 1
    from apps.punkte import selectors as punkte

    assert punkte.guthaben(kind_a) == 0  # die Serie rechnet nie mit Punkten


def test_pausentage_senken_den_bedarf_und_schonen(kind_a):
    ziel(kind_a, seit=M0 - timedelta(weeks=3))
    woche(kind_a, M0 - timedelta(weeks=3), [0, 1, 2])
    # Woche -2: zwei Pausentage, ein geübter Tag -> reicht (Bedarf 3-2=1)
    Lernpause.objects.create(
        kind=kind_a, von=M0 - timedelta(weeks=2), bis=M0 - timedelta(weeks=2, days=-1)
    )
    woche(kind_a, M0 - timedelta(weeks=2), [3])
    # Woche -1: ganz in Ferien -> geschont, zählt nicht mit, bricht nicht
    Lernpause.objects.create(
        kind=None, von=M0 - timedelta(weeks=1), bis=M0 - timedelta(days=1), grund="ferien"
    )
    assert tagesziel.serie(kind_a, HEUTE).wochen == 2


def test_laufende_woche_geschont_und_ferien_schalter(kind_a):
    ziel(kind_a, seit=M0 - timedelta(weeks=1))
    woche(kind_a, M0 - timedelta(weeks=1), [0, 1, 2])
    einstellungen.setzen("lernen.ferien_schalter", True, akteur=None)
    s = tagesziel.serie(kind_a, HEUTE)
    assert (s.wochen, s.bedarf, s.geschont) == (1, 0, True)


def test_wochen_vor_dem_ersten_lerntag_zaehlen_nicht(kind_a):
    ziel(kind_a, seit=M0)  # erste Woche ist die laufende
    assert tagesziel.serie(kind_a, HEUTE).wochen == 0
