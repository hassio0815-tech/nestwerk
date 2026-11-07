"""Etappe 12 (W-5, W-6, Planer): Neu-Limit, Interleaving, Fehlertyp in der Auswahl, echte
Fälligkeit im Prüfungsplaner."""

import random
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.kern import einstellungen, zeit
from apps.lernen import fsrs_adapter as fa
from apps.lernen import mathe_aufgaben, plan_selectors, plan_services, services, wiederholung
from apps.lernen.mathe import registry
from apps.lernen.models import (
    Fach,
    Frage,
    Lernstand,
    PortionArt,
    PortionStatus,
    Thema,
    Versuch,
    Vorhaben,
)

from .test_wiederholung import HEUTE, _naechste

# --- Neu-Limit (Vokabeln pro Tag) -----------------------------------------------------------------


@pytest.fixture
def alle_themen(fach):
    return list(fach.themen.all())


def _tag_ueben(kind, fach, themen, heute, vorhaben=Vorhaben.NEU):
    """Ein Tag voller richtiger Antworten; gibt die gewählten Paare zurück."""
    ausgeschlossen, paare = set(), []
    for _ in range(40):
        wahl = _naechste(
            kind, fach, themen, heute=heute, vorhaben=vorhaben, ausgeschlossen=ausgeschlossen
        )
        if wahl is None:
            break
        frage, richtung = wahl
        ausgeschlossen.add((frage.pk, richtung))
        wiederholung.stand_buchen(kind, frage, richtung, True, heute, None)
        paare.append(wahl)
    return paare


def test_neu_limit_nach_klassenstufe(kind_a, fach):
    assert wiederholung.neu_limit(kind_a, fach) == 3  # unbekannt: das Niedrigste
    for klasse, erwartet in ((3, 3), (5, 3), (6, 5), (7, 5), (8, 7), (10, 7)):
        services.leistungsstufe_setzen(kind_a, fach, "", klasse)
        assert wiederholung.neu_limit(kind_a, fach) == erwartet


def test_neu_limit_je_kind_ueberschreibt(kind_a, kind_b, fach):
    services.leistungsstufe_setzen(kind_a, fach, "", 8)
    services.leistungsstufe_setzen(kind_b, fach, "", 8)
    wiederholung.neu_limit_setzen(kind_a, fach, 2)
    assert wiederholung.neu_limit(kind_a, fach) == 2
    assert wiederholung.neu_limit(kind_b, fach) == 7
    wiederholung.neu_limit_setzen(kind_a, fach, None)
    assert wiederholung.neu_limit(kind_a, fach) == 7


def test_neu_limit_haelt(kind_a, fach, alle_themen):
    wiederholung.neu_limit_setzen(kind_a, fach, 2)
    paare = _tag_ueben(kind_a, fach, alle_themen, HEUTE)
    assert len({f.pk for f, _r in paare}) == 2  # zwei neue Vokabeln, beide Richtungen
    assert len(paare) == 4
    # am nächsten Tag kommen höchstens zwei weitere neue dazu
    morgen = HEUTE + timedelta(days=1)
    vorher = set(Lernstand.objects.values_list("frage_id", flat=True))
    _tag_ueben(kind_a, fach, alle_themen, morgen)
    neue = set(Lernstand.objects.values_list("frage_id", flat=True)) - vorher
    assert len(neue) == 2


def test_neu_limit_gilt_je_kind_und_nicht_fuer_faellige(kind_a, kind_b, fach, alle_themen):
    wiederholung.neu_limit_setzen(kind_a, fach, 1)
    _tag_ueben(kind_a, fach, alle_themen, HEUTE)
    assert Lernstand.objects.filter(kind=kind_a).values("frage_id").distinct().count() == 1
    # Geschwister ist nicht betroffen
    services.leistungsstufe_setzen(kind_b, fach, "", 8)
    paare = _tag_ueben(kind_b, fach, alle_themen, HEUTE)
    assert len({f.pk for f, _r in paare}) == 6
    # Fälliges kommt trotz erreichtem Limit
    frage = Frage.objects.filter(thema__fach=fach).first()
    Lernstand.objects.filter(kind=kind_a).update(faellig_am=HEUTE + timedelta(days=1))
    Lernstand.objects.create(
        kind=kind_a, frage=frage, richtung="en_de", faellig_am=HEUTE, erster_tag=HEUTE
    )
    wahl = _naechste(kind_a, fach, alle_themen, vorhaben=Vorhaben.WIEDERHOLEN)
    assert wahl == (frage, "en_de")


def test_neu_limit_gilt_nicht_fuer_pruefungsportionen(kind_a, fach, alle_themen):
    wiederholung.neu_limit_setzen(kind_a, fach, 1)
    ids = set(Frage.objects.filter(thema__fach=fach).values_list("pk", flat=True))
    ausgeschlossen, anzahl = set(), 0
    for _ in range(20):
        wahl = _naechste(kind_a, fach, alle_themen, ausgeschlossen=ausgeschlossen, nur_fragen=ids)
        if wahl is None:
            break
        ausgeschlossen.add((wahl[0].pk, wahl[1]))
        anzahl += 1
    assert anzahl == 12


# --- Interleaving (Mathe) ------------------------------


@pytest.fixture
def mathe(db):
    return Fach.objects.get(schluessel="mathe")


def _anteil_aeltere(kind, mathe, klasse, n, seed):
    services.leistungsstufe_setzen(kind, mathe, "Grundniveau", klasse)
    s = services.sitzung_starten(kind, mathe, ziel_fragen=100)
    band = registry.band(klasse)
    rng = random.Random(seed)
    aeltere = 0
    for _ in range(n):
        a = services.frage_stellen(s, zufall=rng)
        if registry.holen(a.frage.generator).klassenstufe < band:
            aeltere += 1
        services.antworten(s, a.loesung)
    return aeltere / n


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_mindestens_30_prozent_aus_aelteren_rechenarten(kind_a, mathe, seed):
    assert einstellungen.wert("lernen.interleaving_prozent") == 30
    assert _anteil_aeltere(kind_a, mathe, 8, 20, seed) >= 0.30


def test_interleaving_quote_ist_einstellbar(kind_a, mathe):
    einstellungen.setzen("lernen.interleaving_prozent", 50, akteur=None)
    assert _anteil_aeltere(kind_a, mathe, 8, 20, 9) >= 0.50


def test_interleaving_ohne_aeltere_rechenarten_geht(kind_a, mathe):
    # kleinste Stufe: es gibt nichts Älteres, die Sitzung läuft trotzdem
    assert _anteil_aeltere(kind_a, mathe, 3, 6, 1) == 0.0


# --- Fehlertyp in der Auswahl (W-6) ---------------------------------------------------------------


def _fehler(kind, mathe, generator, anzahl, fehlertyp="uebertrag_vergessen", alt=False):
    s = services.sitzung_starten(kind, mathe, ziel_fragen=100)
    thema = Thema.objects.filter(fach=mathe).exclude(schluessel="").first()
    for i in range(anzahl):
        f = Frage.objects.create(
            thema=thema,
            typ="frage",
            frage=f"{generator} {i}",
            antwort="1",
            generiert=True,
            generator=generator,
        )
        Versuch.objects.create(
            sitzung=s, frage=f, richtung="de_en", ergebnis="noch_nicht", fehlertyp=fehlertyp
        )
    if alt:
        Versuch.objects.filter(sitzung=s).update(erstellt=timezone.now() - timedelta(days=30))


def test_fehlerarten_der_letzten_14_tage_markieren_die_rechenart(kind_a, mathe):
    jetzt = timezone.now()
    _fehler(kind_a, mathe, "klammern", 3)
    _fehler(kind_a, mathe, "prozent_wert", 2)  # zu wenige
    _fehler(kind_a, mathe, "bruch_kuerzen", 5, alt=True)  # zu lange her
    _fehler(kind_a, mathe, "dezimal_runden", 5, fehlertyp="unlesbar")  # kein Rechenfehler
    assert mathe_aufgaben.fehler_rechenarten(kind_a, mathe, zeit.heute(jetzt)) == {"klammern"}


def test_fehlerart_erhoeht_das_gewicht(kind_a, mathe):
    gens = [registry.holen(k) for k in ("klammern", "prozent_wert")]
    basis = dict(
        band=6,
        gemischt=False,
        verlauf={},
        letzter_gen="",
        letztes_thema="",
        params=mathe_aufgaben._parameter(),
    )
    ohne = mathe_aufgaben._gewichte(gens, fehler=frozenset(), **basis)
    mit = mathe_aufgaben._gewichte(gens, fehler=frozenset({"klammern"}), **basis)
    assert mit[0] > ohne[0] and mit[1] == ohne[1]


def test_fehlerart_zieht_in_der_sitzung_haeufiger(kind_a, mathe):
    services.leistungsstufe_setzen(kind_a, mathe, "Grundniveau", 6)
    einstellungen.setzen(
        "lernen.mathe_rechenarten_aus",
        [k for k in registry.schluessel_alle() if k not in ("klammern", "prozent_wert")],
        akteur=None,
    )
    _fehler(kind_a, mathe, "klammern", 3)
    s = services.sitzung_starten(kind_a, mathe, ziel_fragen=100)
    rng = random.Random(5)
    gezogen = []
    for _ in range(40):
        a = services.frage_stellen(s, zufall=rng)
        gezogen.append(a.frage.generator)
        services.antworten(s, a.loesung)
    assert gezogen.count("klammern") > gezogen.count("prozent_wert")


# --- Prüfungsplaner nutzt die echte Fälligkeit ------------------------------


def _plan_mit_offener_wiederholung(kind, fach, uhr):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name="Planthema")
    for i in range(6):
        Frage.objects.create(thema=t, typ="frage", frage=f"Q{i}", antwort=f"a{i}")
    p = plan_services.pruefung_anlegen(
        kind, fach, "Test", zeit.heute() + timedelta(days=30), themen=[t]
    )
    neu = p.portionen.filter(art=PortionArt.NEU).order_by("datum").first()
    neu.status = PortionStatus.ERLEDIGT
    neu.save()
    wdh = (
        p.portionen.filter(art=PortionArt.WIEDERHOLUNG, pflicht=True, stoff=neu.stoff)
        .order_by("datum")
        .first()
    )
    return p, neu, wdh


def test_planer_parameter_folgen_dem_algorithmus(kind_a):
    heute = zeit.heute()
    fsrs_p = plan_selectors.parameter(kind_a, heute).abstaende
    assert fsrs_p == tuple(
        fa.nominale_abstaende(len(einstellungen.wert("lernen.box_abstaende_tage")))
    )
    einstellungen.setzen("lernen.wiederholung_algorithmus", "leitner", akteur=None)
    assert plan_selectors.parameter(kind_a, heute).abstaende == (1, 3, 7, 14)


def test_offene_wiederholung_folgt_der_echten_faelligkeit(kind_a, fach, uhr):
    p, neu, wdh = _plan_mit_offener_wiederholung(kind_a, fach, uhr)
    heute = zeit.heute()
    real = heute + timedelta(days=9)
    for fid in wdh.fragen:
        Lernstand.objects.create(
            kind=kind_a, frage_id=fid, richtung="de_en", faellig_am=real, erster_tag=heute
        )
    offen = plan_selectors.eingabe(p, heute)["wdh_offen"]
    mine = [w for w in offen if w.fragen == tuple(wdh.fragen)]
    assert mine and mine[0].frueh_ab == real


def test_ohne_stand_bleibt_der_geplante_termin(kind_a, fach, uhr):
    p, neu, wdh = _plan_mit_offener_wiederholung(kind_a, fach, uhr)
    heute = zeit.heute()
    offen = plan_selectors.eingabe(p, heute)["wdh_offen"]
    mine = [w for w in offen if w.fragen == tuple(wdh.fragen)]
    assert mine and mine[0].frueh_ab == max(wdh.datum, heute)


def test_echte_faelligkeit_nie_nach_dem_letzten_lerntag(kind_a, fach, uhr):
    p, neu, wdh = _plan_mit_offener_wiederholung(kind_a, fach, uhr)
    heute = zeit.heute()
    for fid in wdh.fragen:
        Lernstand.objects.create(
            kind=kind_a, frage_id=fid, richtung="de_en", faellig_am=p.termin + timedelta(days=40)
        )
    mine = [
        w for w in plan_selectors.eingabe(p, heute)["wdh_offen"] if w.fragen == tuple(wdh.fragen)
    ]
    assert mine[0].frueh_ab <= p.termin - timedelta(days=1)
