"""Lernsitzung: Ablauf, Prüfung, Zeit, Tagesziel, Punkte, Frust-Erkennung, Rückschau."""

import random
from datetime import timedelta

import pytest

from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen, zeit
from apps.lernen import selectors, services, tagesziel
from apps.lernen.models import (
    Ergebnis,
    Erwartung,
    Fach,
    Frage,
    Intensitaet,
    Lernstand,
    Lerntag,
    Richtung,
    Strategie,
    Thema,
    Versuch,
    Vorhaben,
)
from apps.punkte import selectors as punkte
from apps.punkte.models import Buchung
from apps.spielregeln.models import Aktivitaet


def laufen(s, uhr, sekunden):
    """Lässt aktive Zeit vergehen (in Schritten unter der Denkpausen-Grenze)."""
    while sekunden > 0:
        schritt = min(100, sekunden)
        uhr.weiter(seconds=schritt)
        services.frage_stellen(s)
        sekunden -= schritt


def starten(kind, fach, **extra):
    return services.sitzung_starten(kind, fach, **extra)


def frage(s, seed=1):
    return services.frage_stellen(s, zufall=random.Random(seed))


def richtig(s, uhr=None, sekunden=0):
    a = s.aktuell_frage and services.frage_stellen(s)
    a = a or frage(s)
    if uhr:
        uhr.weiter(seconds=sekunden)
    return services.antworten(s, a.loesung)


def falsch(s, uhr=None, sekunden=0):
    frage(s)
    if uhr:
        uhr.weiter(seconds=sekunden)
    return services.antworten(s, "völlig daneben")


# --- Start ------------------------------------------------------------------------------------


def test_sitzung_starten_setzt_alles(kind_a, fach, uhr):
    s = starten(
        kind_a,
        fach,
        intensitaet=Intensitaet.HERAUSFORDERUNG,
        vorhaben=Vorhaben.NEU,
        strategie=Strategie.LAUT,
        erwartung=Erwartung.VIELES,
    )
    assert (s.ziel_fragen, s.intensitaet, s.vorhaben, s.strategie, s.erwartung) == (
        15,
        "herausforderung",
        "neu",
        "laut",
        "vieles",
    )
    assert s.beginn == uhr.jetzt
    assert starten(kind_a, fach, intensitaet=Intensitaet.AUFWAERMEN).ziel_fragen == 5
    assert Lerntag.objects.get(kind=kind_a).sekunden == 0


def test_neue_sitzung_beendet_die_offene(kind_a, fach):
    erste = starten(kind_a, fach)
    zweite = starten(kind_a, fach)
    erste.refresh_from_db()
    assert erste.ende is not None
    assert selectors.offene_sitzung(kind_a) == zweite


def test_start_pruefungen(kind_a, mama, fach):
    with pytest.raises(services.LernenFehler):
        starten(mama, fach)
    fach.aktiv = False
    fach.save()
    with pytest.raises(services.LernenFehler):
        starten(kind_a, fach)
    fach.aktiv = True
    fach.save()
    anderes = Fach.objects.create(schluessel="anderes", name="Anderes")
    fremd = Thema.objects.create(fach=anderes, name="X")
    with pytest.raises(services.LernenFehler):
        starten(kind_a, fach, thema=fremd)
    for name in ("intensitaet", "vorhaben", "strategie", "erwartung"):
        with pytest.raises(services.LernenFehler):
            starten(kind_a, fach, **{name: "nix"})


# --- Fragen und Antworten ---------------------------------------------------------------------


def test_neuladen_zeigt_dieselbe_frage(kind_a, fach):
    s = starten(kind_a, fach)
    erste = frage(s)
    assert services.frage_stellen(s).frage == erste.frage
    assert services.frage_stellen(s).richtung == erste.richtung


def test_richtige_antwort_bucht_den_lernstand(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    a = frage(s)
    r = services.antworten(s, a.loesung.upper() + " ")
    assert (r.ergebnis, r.loesung, r.nochmal) == (Ergebnis.RICHTIG, "", False)
    s.refresh_from_db()
    assert (s.versuche, s.richtig, s.aktuell_frage_id) == (1, 1, None)
    stand = Lernstand.objects.get(kind=kind_a)
    assert (stand.box, stand.richtige) == (1, 1)
    assert stand.faellig_am == zeit.heute() + timedelta(days=3)
    v = Versuch.objects.get()
    assert (v.ergebnis, v.hilfestufe, v.eingabe) == ("richtig", 0, a.loesung.upper() + " ")


def test_falsche_antwort_zeigt_loesung_und_setzt_box_zurueck(kind_a, fach):
    s = starten(kind_a, fach)
    a = frage(s)
    Lernstand.objects.create(
        kind=kind_a, frage=a.frage, richtung=a.richtung, box=3, faellig_am=zeit.heute()
    )
    r = services.antworten(s, "xyz")
    assert (r.ergebnis, r.loesung) == (Ergebnis.NOCH_NICHT, a.loesung)
    assert "falsch" not in r.text.lower()  # "noch nicht" statt "falsch"
    assert Lernstand.objects.get(kind=kind_a, frage=a.frage, richtung=a.richtung).box == 0
    s.refresh_from_db()
    assert (s.versuche, s.richtig) == (1, 0)


def _dreher(wort):
    return wort[1] + wort[0] + wort[2:]


def _nur_pferd(fach):
    Frage.objects.filter(thema__fach=fach).exclude(frage="Pferd").delete()


def test_fast_richtig_gibt_eine_zweite_chance(kind_a, fach):
    _nur_pferd(fach)
    s = starten(kind_a, fach)
    a = frage(s)
    tippfehler = _dreher(a.loesung)
    r = services.antworten(s, tippfehler)
    assert (r.ergebnis, r.nochmal) == (Ergebnis.FAST, True)
    s.refresh_from_db()
    assert (s.versuche, s.aktuell_frage_id) == (0, a.frage.pk)  # Frage bleibt offen
    assert not Lernstand.objects.exists()
    r = services.antworten(s, tippfehler)  # zweiter Versuch mit Fehler: noch nicht
    assert (r.ergebnis, r.nochmal) == (Ergebnis.NOCH_NICHT, False)
    assert list(Versuch.objects.values_list("ergebnis", flat=True)) == ["fast", "noch_nicht"]


def test_fast_dann_richtig(kind_a, fach):
    _nur_pferd(fach)
    s = starten(kind_a, fach)
    a = frage(s)
    assert services.antworten(s, _dreher(a.loesung)).nochmal
    assert services.antworten(s, a.loesung).ergebnis == Ergebnis.RICHTIG


def test_antworten_ohne_offene_frage_oder_nach_ende(kind_a, fach):
    s = starten(kind_a, fach)
    with pytest.raises(services.LernenFehler):
        services.antworten(s, "x")
    frage(s)
    services.sitzung_beenden(s)
    with pytest.raises(services.LernenFehler):
        services.antworten(s, "x")
    assert services.frage_stellen(s) is None


def test_hilfe_kostet_nichts_und_wird_gemerkt(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    a = frage(s)
    hinweis = services.hilfe(s)
    assert hinweis.replace(" ", "")[0] == a.loesung[0]
    assert hinweis.count("_") == len(a.loesung.replace(" ", "")) - 1
    assert services.hinweis_text("to be") == "t _   _ _"
    s.refresh_from_db()
    assert (s.hilfestufe_max, s.aktuell_hilfe) == (1, 1)
    services.antworten(s, a.loesung)
    assert Versuch.objects.get().hilfestufe == 1
    assert punkte.guthaben(kind_a) == 0
    with pytest.raises(services.LernenFehler):
        services.hilfe(s)


def test_loesung_zeigen_zaehlt_als_noch_nicht_ohne_strafe(kind_a, fach):
    s = starten(kind_a, fach)
    a = frage(s)
    r = services.loesung_zeigen(s)
    assert (r.ergebnis, r.loesung) == (Ergebnis.NOCH_NICHT, a.loesung)
    v = Versuch.objects.get()
    assert (v.hilfestufe, v.eingabe) == (2, "")
    s.refresh_from_db()
    assert s.hilfestufe_max == 2
    assert punkte.guthaben(kind_a) == 0


def test_ende_wenn_ziel_fragen_erreicht(kind_a, fach):
    s = starten(kind_a, fach, intensitaet=Intensitaet.AUFWAERMEN)
    for _i in range(5):
        richtig(s)
    assert frage(s) is None


def test_ende_wenn_nichts_mehr_dran_ist(kind_a, fach):
    Frage.objects.filter(thema__fach=fach).exclude(frage="rot").delete()
    s = starten(kind_a, fach)
    richtig(s)
    richtig(s)  # zweite Richtung
    assert frage(s) is None


def test_frage_ausserhalb_der_klassenstufe_kommt_nicht(kind_a, fach):
    services.leistungsstufe_setzen(kind_a, fach, "G", 4)
    Frage.objects.filter(thema__fach=fach).update(
        thema=Thema.objects.create(fach=fach, klassenstufe=9, name="Zu hoch")
    )
    s = starten(kind_a, fach)
    assert frage(s) is None


def test_mehrere_themen_werden_gemischt(kind_a, fach):
    s = starten(kind_a, fach)
    themen = []
    for i in range(6):
        a = frage(s, seed=i)
        themen.append(a.frage.thema_id)
        services.antworten(s, a.loesung)
    assert all(a != b for a, b in zip(themen, themen[1:], strict=False))


# --- Zeit, Tagesziel, Punkte ------------------------------------------------------------------


def test_zeit_ohne_lange_denkpausen(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    frage(s)
    uhr.weiter(seconds=40)
    frage(s)
    uhr.weiter(hours=2)  # Kind ist weggegangen: höchstens die Denkpause zählt
    frage(s)
    s.refresh_from_db()
    assert s.dauer_sekunden == 40 + 120
    assert Lerntag.objects.get(kind=kind_a).sekunden == 160


def test_mindesttag_erfasst_aktivitaet_einmal(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    laufen(s, uhr, 280)
    assert not Aktivitaet.objects.exists()
    laufen(s, uhr, 40)
    laufen(s, uhr, 40)
    a = Aktivitaet.objects.get()
    assert (a.modul, a.kind_id) == ("lernen", kind_a.pk)
    assert Lerntag.objects.get(kind=kind_a).mindesttag


def test_tagesziel_gibt_festen_betrag_einmal(kind_a, fach, uhr):
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    s = starten(kind_a, fach)
    laufen(s, uhr, 400)
    assert punkte.guthaben(kind_a) == 5
    b = Buchung.objects.get()
    assert (b.quelle_modul, b.art, b.bezugsdatum) == ("lernen", "modul", zeit.heute())
    laufen(s, uhr, 400)  # nochmal viel Zeit: kein zweites Mal
    assert Buchung.objects.count() == 1
    tag = Lerntag.objects.get(kind=kind_a)
    assert (tag.erreicht, tag.punkte) == (True, 5)
    # Anderer Sitzungsstart am selben Tag: weiterhin nur eine Buchung
    s2 = starten(kind_a, fach)
    laufen(s2, uhr, 200)
    assert Buchung.objects.count() == 1


def test_tagesziel_ereignis_mit_msgid_und_schluessel(kind_a, fach, uhr):
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    s = starten(kind_a, fach)
    laufen(s, uhr, 400)
    laufen(s, uhr, 400)
    e = Ereignis.objects.get(typ_id="lernen.ziel_erreicht")
    assert e.kind_id == kind_a.pk
    assert e.schluessel == f"lernen.ziel_erreicht:{kind_a.pk}:{zeit.heute().isoformat()}"
    assert e.daten["punkte"] == 5 and e.daten["minuten"] == 6
    assert e.daten["hinweis_msgid"] == "Tagesziel geschafft. Das Dranbleiben zählt."


def test_punkte_keine_pro_richtige_antwort(kind_a, fach, uhr):
    s = starten(kind_a, fach, intensitaet=Intensitaet.HERAUSFORDERUNG)
    for i in range(10):
        a = frage(s, seed=i)
        uhr.weiter(seconds=5)
        services.antworten(s, a.loesung)
    s.refresh_from_db()
    assert s.richtig == 10
    assert punkte.guthaben(kind_a) == 0  # Tagesziel (20 Minuten) nicht erreicht


def test_lernpunkte_aus_schaltet_nur_die_punkte_ab(kind_a, fach, uhr):
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    einstellungen.setzen("lernen.lernpunkte_aktiv", False, akteur=None)
    s = starten(kind_a, fach)
    laufen(s, uhr, 400)
    assert punkte.guthaben(kind_a) == 0
    assert Lerntag.objects.get(kind=kind_a).erreicht
    assert Ereignis.objects.filter(typ_id="lernen.ziel_erreicht").count() == 1
    assert Ereignis.objects.get(typ_id="lernen.ziel_erreicht").daten["punkte"] == 0


def test_tageslimit_deckelt(kind_a, fach, uhr):
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    einstellungen.setzen("lernen.lernpunkte_tageslimit", 3, akteur=None)
    s = starten(kind_a, fach)
    laufen(s, uhr, 400)
    assert punkte.guthaben(kind_a) == 3
    einstellungen.setzen("lernen.lernpunkte_tageslimit", 0, akteur=None)


def test_tageslimit_null_gibt_keine_punkte(kind_a, fach, uhr):
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    einstellungen.setzen("lernen.lernpunkte_tageslimit", 0, akteur=None)
    s = starten(kind_a, fach)
    laufen(s, uhr, 400)
    assert punkte.guthaben(kind_a) == 0
    assert Lerntag.objects.get(kind=kind_a).erreicht


def test_tagesbild_und_metrik(kind_a, fach, uhr):
    from apps.kern import registry

    s = starten(kind_a, fach)
    assert registry.fortschritt("metrik.tage_geuebt", kind_a) == 0
    laufen(s, uhr, 330)
    b = selectors.tagesbild(kind_a, zeit.heute())
    assert (b.minuten, b.mindesttag, b.erreicht, b.pause) == (5, True, False, False)
    assert registry.fortschritt("metrik.tage_geuebt", kind_a) == 1
    assert selectors.tage_der_woche(kind_a, zeit.heute()) == 1


# --- Frust ------------------------------------------------------------------------------------


def test_drei_fehler_in_folge_senken_die_stufe_und_schlagen_pause_vor(kind_a, fach, uhr):
    s = starten(kind_a, fach, intensitaet=Intensitaet.HERAUSFORDERUNG)
    r1, r2, r3 = (falsch(s, uhr, 20) for _i in range(3))
    assert not r1.pause_vorschlag and not r2.pause_vorschlag
    assert (r3.pause_vorschlag, r3.stufe_gesenkt) == (True, True)
    s.refresh_from_db()
    assert (s.intensitaet, s.frust_erkannt) == ("normal", True)
    # Nur einmal je Sitzung
    assert not falsch(s, uhr, 20).pause_vorschlag


def test_frust_im_aufwaermen_schlaegt_nur_pause_vor(kind_a, fach, uhr):
    s = starten(kind_a, fach, intensitaet=Intensitaet.AUFWAERMEN)
    for _i in range(2):
        falsch(s, uhr, 20)
    r = falsch(s, uhr, 20)
    assert (r.pause_vorschlag, r.stufe_gesenkt) == (True, False)
    s.refresh_from_db()
    assert s.intensitaet == "aufwaermen"


def test_richtige_dazwischen_unterbrechen_die_folge(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    for muster in (falsch, falsch, richtig, falsch, falsch):
        assert not muster(s, uhr, 20).pause_vorschlag


def test_sehr_schnelles_durchklicken(kind_a, fach, uhr):
    einstellungen.setzen("lernen.frust_fehler_folge", 20, akteur=None)
    s = starten(kind_a, fach)
    ergebnisse = [falsch(s) for _i in range(4)]  # ohne Zeitverlust: 0 ms je Antwort
    assert ergebnisse[-1].pause_vorschlag
    s.refresh_from_db()
    assert s.frust_erkannt


def test_schnelles_richtig_tippen_ist_kein_frust(kind_a, fach, uhr):
    einstellungen.setzen("lernen.frust_fehler_folge", 20, akteur=None)
    s = starten(kind_a, fach)
    assert not any(richtig(s).pause_vorschlag for _i in range(6))


# --- Rückschau --------------------------------------------------------------------------------


def test_rueckschau_speichern(kind_a, fach):
    s = starten(kind_a, fach, erwartung=Erwartung.WENIGES)
    richtig(s)
    services.rueckschau_speichern(s, " Schwer   war  das ", "Laut sprechen", "passend")
    s.refresh_from_db()
    assert s.ende is not None  # Rückschau beendet die Sitzung, falls nötig
    assert (s.rueckschau_schwer, s.rueckschau_geholfen) == ("Schwer war das", "Laut sprechen")
    assert (s.selbsteinschaetzung, s.rueckschau_fertig) == ("passend", True)
    assert selectors.zustand(s) == "fertig"
    # Einmal gespeichert gilt sie
    services.rueckschau_speichern(s, "anders", "anders", "zu_schwer")
    s.refresh_from_db()
    assert s.rueckschau_schwer == "Schwer war das"


def test_rueckschau_darf_leer_sein_und_kuerzt(kind_a, fach):
    s = starten(kind_a, fach)
    services.sitzung_beenden(s)
    services.rueckschau_speichern(s, "x" * 500)
    s.refresh_from_db()
    assert len(s.rueckschau_schwer) == 300
    assert (s.rueckschau_geholfen, s.selbsteinschaetzung) == ("", "")


def test_rueckschau_ungueltige_einschaetzung(kind_a, fach):
    s = starten(kind_a, fach)
    with pytest.raises(services.LernenFehler):
        services.rueckschau_speichern(s, "", "", "kaputt")


def test_sitzung_beenden_ist_idempotent(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    uhr.weiter(seconds=30)
    services.sitzung_beenden(s)
    ende = s.ende
    uhr.weiter(seconds=30)
    services.sitzung_beenden(s)
    assert s.ende == ende
    assert s.dauer_sekunden == 30


def test_zustand_und_vergleich(kind_a, fach):
    s = starten(kind_a, fach, erwartung=Erwartung.WENIGES)
    assert selectors.zustand(s) == "frage"
    assert selectors.quote(s) is None
    assert selectors.vergleich(s) == ""
    s.versuche, s.richtig = 10, 9
    assert selectors.quote(s) == 0.9
    assert selectors.vergleich(s) == "mehr"
    s.erwartung = Erwartung.VIELES
    assert selectors.vergleich(s) == "passt"
    s.richtig = 1
    assert selectors.vergleich(s) == "weniger"
    s.richtig, s.erwartung = 6, Erwartung.EINIGES
    assert selectors.vergleich(s) == "passt"
    s.erwartung = ""
    assert selectors.vergleich(s) == ""


def test_sprachstufe(kind_a, fach):
    assert selectors.sprachstufe(kind_a) == 2  # unbekannt
    assert selectors.sprachstufe(kind_a, fach) == 2
    services.leistungsstufe_setzen(kind_a, fach, "G", 3)
    assert selectors.sprachstufe(kind_a, fach) == 1
    assert selectors.sprachstufe(kind_a) == 1
    services.leistungsstufe_setzen(kind_a, fach, "G", 9)
    assert selectors.sprachstufe(kind_a, fach) == 3


def test_tag_vorbereiten_ist_idempotent(kind_a):
    assert tagesziel.KEINE == services.tag_vorbereiten(kind_a)
    assert tagesziel.KEINE == services.tag_vorbereiten(kind_a)
    assert Lerntag.objects.filter(kind=kind_a).count() == 1


def test_nur_kinder_ueben(mama, fach):
    with pytest.raises(services.LernenFehler):
        services.vorschlag_entscheiden(mama, annehmen=True)


def test_richtung_der_ersten_frage_haengt_von_der_intensitaet_ab(kind_a, fach):
    s = starten(kind_a, fach, intensitaet=Intensitaet.AUFWAERMEN)
    assert frage(s).richtung == Richtung.EN_DE
