"""Abstandswiederholung in Boxen und Auswahl der nächsten Frage."""

import random
from datetime import date, timedelta

import pytest

from apps.kern import einstellungen
from apps.lernen import selectors, wiederholung
from apps.lernen.models import (
    Fach,
    Frage,
    FrageTyp,
    Intensitaet,
    Lernstand,
    Quelle,
    Richtung,
    Thema,
    Vorhaben,
)

HEUTE = date(2026, 10, 23)
JETZT = None


@pytest.fixture
def alle_themen(fach):
    return list(fach.themen.all())


def _naechste(kind, fach, themen, **extra):
    vorgaben = {
        "thema": None,
        "vorhaben": Vorhaben.WIEDERHOLEN,
        "intensitaet": Intensitaet.NORMAL,
        "heute": HEUTE,
        "ausgeschlossen": set(),
        "letztes_thema": None,
        "zufall": random.Random(7),
    }
    vorgaben.update(extra)
    return wiederholung.naechste(kind, fach, themen, **vorgaben)


def test_abstaende_aus_den_einstellungen():
    assert wiederholung.abstaende() == [1, 3, 7, 14]
    einstellungen.setzen("lernen.box_abstaende_tage", [2, 4], akteur=None)
    assert wiederholung.abstaende() == [2, 4]
    assert wiederholung.naechste_box(0, True) == 1
    assert wiederholung.naechste_box(1, True) == 1  # letzte Box bleibt


def test_einstellung_abstaende_wird_validiert():
    for schlecht in ([1], [7, 3], []):
        with pytest.raises(Exception):  # noqa: B017 - ValidationError der Definition
            einstellungen.setzen("lernen.box_abstaende_tage", schlecht, akteur=None)
    with pytest.raises(Exception):  # noqa: B017
        einstellungen.setzen("lernen.fragen_normal", 0, akteur=None)


def test_box_vor_bei_richtig_zurueck_bei_falsch():
    assert wiederholung.naechste_box(0, True) == 1
    assert wiederholung.naechste_box(2, True) == 3
    assert wiederholung.naechste_box(3, True) == 3
    assert wiederholung.naechste_box(3, False) == 0
    assert wiederholung.faellig_nach(0, HEUTE) == HEUTE + timedelta(days=1)
    assert wiederholung.faellig_nach(3, HEUTE) == HEUTE + timedelta(days=14)
    assert wiederholung.faellig_nach(9, HEUTE) == HEUTE + timedelta(days=14)


def test_stand_buchen_fortschreiben(kind_a, fach):
    einstellungen.setzen("lernen.wiederholung_algorithmus", "leitner", akteur=None)
    frage = Frage.objects.filter(thema__fach=fach).first()
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    assert (s.box, s.faellig_am, s.versuche, s.richtige) == (1, HEUTE + timedelta(days=3), 1, 1)
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    assert (s.box, s.faellig_am) == (2, HEUTE + timedelta(days=7))
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, False, HEUTE, None)
    assert (s.box, s.faellig_am, s.versuche, s.richtige) == (0, HEUTE + timedelta(days=1), 3, 2)
    # Die andere Richtung hat einen eigenen Stand
    assert Lernstand.objects.filter(kind=kind_a, frage=frage).count() == 1
    wiederholung.stand_buchen(kind_a, frage, Richtung.EN_DE, False, HEUTE, None)
    assert Lernstand.objects.filter(kind=kind_a, frage=frage).count() == 2


def test_aufgabe_in_beide_richtungen(fach):
    sein = Frage.objects.get(thema__fach=fach, frage="sein")
    hin = wiederholung.aufgabe_fuer(sein, Richtung.DE_EN)
    assert (hin.text, hin.erwartet, hin.loesung, hin.mehrere) == (
        "sein",
        "to be / be",
        "to be",
        True,
    )
    zurueck = wiederholung.aufgabe_fuer(sein, Richtung.EN_DE)
    assert (zurueck.text, zurueck.erwartet, zurueck.mehrere) == ("to be", "sein", False)
    assert wiederholung.richtungen(sein) == (Richtung.DE_EN, Richtung.EN_DE)


def test_fragen_nur_vorwaerts(fach):
    thema = fach.themen.first()
    frage = Frage.objects.create(
        thema=thema, typ=FrageTyp.FRAGE, frage="Wie viel ist 2+2?", antwort="4"
    )
    assert wiederholung.richtungen(frage) == (Richtung.DE_EN,)
    aufgabe = wiederholung.aufgabe_fuer(frage, Richtung.EN_DE)
    assert (aufgabe.richtung, aufgabe.text, aufgabe.erwartet) == (Richtung.DE_EN, frage.frage, "4")


def test_neue_fragen_wenn_nichts_faellig(kind_a, fach, alle_themen):
    frage, richtung = _naechste(kind_a, fach, alle_themen)
    assert frage.thema.fach_id == fach.pk
    assert richtung in (Richtung.DE_EN, Richtung.EN_DE)


def test_faellige_vor_neuen_beim_wiederholen(kind_a, fach, alle_themen):
    frage = Frage.objects.get(thema__fach=fach, frage="Hund")
    Lernstand.objects.create(
        kind=kind_a, frage=frage, richtung=Richtung.DE_EN, box=1, faellig_am=HEUTE
    )
    assert _naechste(kind_a, fach, alle_themen) == (frage, Richtung.DE_EN)


def test_nicht_faellige_kommen_nicht(kind_a, fach, alle_themen):
    # Alle 12 Paare sind geübt, aber erst morgen fällig: nichts mehr dran
    for f in Frage.objects.filter(thema__fach=fach):
        for r in wiederholung.richtungen(f):
            Lernstand.objects.create(
                kind=kind_a, frage=f, richtung=r, faellig_am=HEUTE + timedelta(days=1)
            )
    assert _naechste(kind_a, fach, alle_themen) is None


def test_vorhaben_neu_bevorzugt_neue(kind_a, fach, alle_themen):
    hund = Frage.objects.get(thema__fach=fach, frage="Hund")
    Lernstand.objects.create(kind=kind_a, frage=hund, richtung=Richtung.DE_EN, faellig_am=HEUTE)
    gesehen = {
        _naechste(kind_a, fach, alle_themen, vorhaben=Vorhaben.NEU, zufall=random.Random(i))
        for i in range(30)
    }
    assert (hund, Richtung.DE_EN) not in gesehen


def test_stolperstellen_zuerst(kind_a, fach, alle_themen):
    hund, katze = (
        Frage.objects.get(thema__fach=fach, frage="Hund"),
        Frage.objects.get(thema__fach=fach, frage="Katze"),
    )
    Lernstand.objects.create(
        kind=kind_a, frage=hund, richtung=Richtung.DE_EN, box=2, faellig_am=HEUTE
    )
    Lernstand.objects.create(
        kind=kind_a,
        frage=katze,
        richtung=Richtung.DE_EN,
        box=0,
        versuche=3,
        richtige=1,
        faellig_am=HEUTE,
    )
    for i in range(10):
        wahl = _naechste(
            kind_a, fach, alle_themen, vorhaben=Vorhaben.STOLPERSTELLEN, zufall=random.Random(i)
        )
        assert wahl == (katze, Richtung.DE_EN)


def test_unbekanntes_vorhaben_faellt_auf_wiederholen(kind_a, fach, alle_themen):
    hund = Frage.objects.get(thema__fach=fach, frage="Hund")
    Lernstand.objects.create(kind=kind_a, frage=hund, richtung=Richtung.DE_EN, faellig_am=HEUTE)
    assert _naechste(kind_a, fach, alle_themen, vorhaben="gibtsnicht") == (hund, Richtung.DE_EN)


def test_ausgeschlossene_paare_fehlen(kind_a, fach, alle_themen):
    paare = {
        (f.pk, r)
        for f in Frage.objects.filter(thema__fach=fach)
        for r in wiederholung.richtungen(f)
    }
    rest = next(iter(paare))
    wahl = _naechste(kind_a, fach, alle_themen, ausgeschlossen=paare - {rest})
    assert (wahl[0].pk, wahl[1]) == rest
    assert _naechste(kind_a, fach, alle_themen, ausgeschlossen=paare) is None


def test_gemischte_themen_nie_zweimal_dasselbe_hintereinander(kind_a, fach, alle_themen):
    tiere = fach.themen.get(name="Tiere")
    for i in range(20):
        wahl = _naechste(kind_a, fach, alle_themen, letztes_thema=tiere.pk, zufall=random.Random(i))
        assert wahl[0].thema_id != tiere.pk


def test_nur_ein_thema_bleibt_dabei_wenn_alles_gleich(kind_a, fach, alle_themen):
    tiere = fach.themen.get(name="Tiere")
    # Nur ein Thema gewählt und es war schon das letzte: es gibt keine Alternative
    wahl = _naechste(kind_a, fach, alle_themen, thema=tiere, letztes_thema=tiere.pk)
    assert wahl[0].thema_id == tiere.pk


def test_gewaehltes_thema_neu_aus_dem_thema_faellig_aus_dem_fach(kind_a, fach, alle_themen):
    tiere, farben = fach.themen.get(name="Tiere"), fach.themen.get(name="Farben")
    rot = Frage.objects.get(thema__fach=fach, frage="rot")
    Lernstand.objects.create(kind=kind_a, frage=rot, richtung=Richtung.DE_EN, faellig_am=HEUTE)
    # Wiederholung aus Farben kommt auch, wenn "Tiere" gewählt ist
    assert _naechste(kind_a, fach, alle_themen, thema=tiere) == (rot, Richtung.DE_EN)
    # Neue Paare kommen nur aus dem gewählten Thema
    neu = {
        _naechste(
            kind_a, fach, alle_themen, thema=farben, vorhaben=Vorhaben.NEU, zufall=random.Random(i)
        )
        for i in range(30)
    }
    assert {f.thema_id for f, _r in neu} == {farben.pk}


def test_richtungswunsch_der_intensitaet(kind_a, fach, alle_themen):
    aufwaermen = {
        _naechste(
            kind_a, fach, alle_themen, intensitaet=Intensitaet.AUFWAERMEN, zufall=random.Random(i)
        )[1]
        for i in range(20)
    }
    herausforderung = {
        _naechste(
            kind_a,
            fach,
            alle_themen,
            intensitaet=Intensitaet.HERAUSFORDERUNG,
            zufall=random.Random(i),
        )[1]
        for i in range(20)
    }
    assert aufwaermen == {Richtung.EN_DE}
    assert herausforderung == {Richtung.DE_EN}


def test_fremde_und_ungeprueft_fragen_zaehlen_nicht(kind_a, kind_b, fach, alle_themen):
    thema = fach.themen.get(name="Tiere")
    fremd = Frage.objects.create(
        thema=thema, typ="vokabel", frage="Maus", antwort="mouse", quelle=Quelle.ELTERN, kind=kind_b
    )
    Lernstand.objects.create(kind=kind_a, frage=fremd, richtung=Richtung.DE_EN, faellig_am=HEUTE)
    offen = Frage.objects.create(
        thema=thema,
        typ="vokabel",
        frage="Esel",
        antwort="donkey",
        quelle=Quelle.KI,
        freigabe="offen",
        kind=kind_a,
    )
    Lernstand.objects.create(kind=kind_a, frage=offen, richtung=Richtung.DE_EN, faellig_am=HEUTE)
    for i in range(30):
        wahl = _naechste(kind_a, fach, alle_themen, zufall=random.Random(i))
        assert wahl[0] not in (fremd, offen)


def test_eigene_freigegebene_frage_zaehlt(kind_a, fach, alle_themen):
    thema = fach.themen.get(name="Tiere")
    eigene = Frage.objects.create(
        thema=thema, typ="vokabel", frage="Maus", antwort="mouse", quelle=Quelle.ELTERN, kind=kind_a
    )
    Lernstand.objects.create(kind=kind_a, frage=eigene, richtung=Richtung.DE_EN, faellig_am=HEUTE)
    assert _naechste(kind_a, fach, alle_themen) == (eigene, Richtung.DE_EN)


def test_themen_bis_klassenstufe(fach):
    Thema.objects.create(fach=fach, klassenstufe=8, name="Zukunft")
    Thema.objects.create(fach=fach, klassenstufe=None, name="Immer")
    namen = {t.name for t in selectors.themen_bis(fach, 5)}
    assert namen == {"Tiere", "Farben", "Immer"}
    assert {t.name for t in selectors.themen_bis(fach)} == namen | {"Zukunft"}


def test_fach_ohne_fragen(kind_a, db):
    leer = Fach.objects.create(schluessel="leer", name="Leer")
    assert _naechste(kind_a, leer, []) is None
