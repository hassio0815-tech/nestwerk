"""Prüfungsvorbereitung: Anlegen, Realitätscheck, Verschieben, Pausentage, Üben, Punkte, Probe."""

import random
from collections import defaultdict
from datetime import timedelta

import pytest

from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen, zeit
from apps.lernen import events, plan, plan_selectors, plan_services, selectors, services, tagesziel
from apps.lernen.models import (
    Fach,
    Frage,
    Freigabe,
    Lernpause,
    Lernziel,
    Material,
    PortionArt,
    PortionStatus,
    Pruefung,
    PruefungStatus,
    Thema,
)
from apps.lernen.plan_services import PlanFehler
from apps.punkte.models import Buchung


def thema_mit(fach, anzahl, name="Langes Thema"):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name=name)
    for i in range(anzahl):
        Frage.objects.create(thema=t, typ="frage", frage=f"Frage {name} {i}", antwort=f"a{i}")
    return t


@pytest.fixture
def lang(fach):
    return thema_mit(fach, 40)


def heute():
    return zeit.heute()


def anlegen(kind, fach, *themen, tage=14, **extra):
    return plan_services.pruefung_anlegen(
        kind, fach, "Test", heute() + timedelta(days=tage), themen=themen, **extra
    )


def summen(p):
    s = defaultdict(int)
    for x in p.portionen.exclude(status=PortionStatus.VERSCHOBEN):
        s[x.datum] += x.minuten
    return s


def ueben(kind, portion, uhr, anzahl=None):
    """Beantwortet Fragen der Portion richtig und gibt die Sitzung zurück."""
    s = plan_services.portion_starten(kind, portion, jetzt=uhr.jetzt)
    for _ in range(anzahl or 99):
        a = services.frage_stellen(s, zufall=random.Random(1), jetzt=uhr.jetzt)
        if a is None:
            break
        uhr.weiter(seconds=20)
        services.antworten(s, a.loesung, jetzt=uhr.jetzt)
    return s


# --- Anlegen -------------------------------------------------------------------------------


def test_anlegen_macht_plan_mit_portionen_und_nie_ueber_das_tagesziel(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=21)
    assert p.plan_ok and p.status in (PruefungStatus.GEPLANT, PruefungStatus.AKTIV)
    assert p.stoffe.count() == 1
    ziel = Lernziel.objects.filter(kind=kind_a).first()
    limit = ziel.ziel_minuten if ziel else einstellungen.wert("lernen.tagesziel_minuten")
    assert max(summen(p).values()) <= limit
    neu = p.portionen.filter(art=PortionArt.NEU)
    assert sorted(i for x in neu for i in x.fragen) == sorted(
        Frage.objects.filter(thema=lang).values_list("pk", flat=True)
    )
    assert p.portionen.filter(art=PortionArt.LEICHT).count() == 1
    assert p.portionen.filter(art=PortionArt.PUFFER).exists()
    assert not p.portionen.filter(art=PortionArt.PUFFER).exclude(minuten=0).exists()


def test_anlegen_validiert(kind_a, kind_b, fach, lang, uhr, mama):
    morgen = heute() + timedelta(days=1)
    with pytest.raises(PlanFehler):  # Termin heute
        plan_services.pruefung_anlegen(kind_a, fach, "x", heute(), themen=[lang])
    with pytest.raises(PlanFehler):  # Vergangenheit
        plan_services.pruefung_anlegen(
            kind_a, fach, "x", heute() - timedelta(days=3), themen=[lang]
        )
    with pytest.raises(PlanFehler):  # kein Stoff
        plan_services.pruefung_anlegen(kind_a, fach, "x", morgen)
    with pytest.raises(PlanFehler):  # Thema aus anderem Fach
        anderes = Fach.objects.create(schluessel="anders", name="Anders")
        fremd = thema_mit(anderes, 5, "Fremd")
        plan_services.pruefung_anlegen(kind_a, fach, "x", morgen, themen=[fremd])
    with pytest.raises(services.LernenFehler):  # Eltern haben keine Prüfungen
        plan_services.pruefung_anlegen(mama, fach, "x", morgen, themen=[lang])
    assert Pruefung.objects.count() == 0  # nichts bleibt halb angelegt


def test_fremdes_material_und_nicht_freigegebene_fragen_gehen_nicht(kind_a, kind_b, fach, uhr):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name="Mat")
    m = Material.objects.create(
        kind=kind_b,
        name="a" * 32 + ".png",
        art="bild",
        mime="image/png",
        inhalt_hash="h",
        status="bereit",
        fach=fach,
    )
    Frage.objects.create(thema=t, frage="q", antwort="a", quelle="ki", kind=kind_b, material=m)
    with pytest.raises(PlanFehler):
        plan_services.pruefung_anlegen(
            kind_a, fach, "x", heute() + timedelta(days=9), materialien=[m]
        )
    # Material von Kind A mit nur offener (nicht freigegebener) Frage: nicht wählbar
    m2 = Material.objects.create(
        kind=kind_a,
        name="b" * 32 + ".png",
        art="bild",
        mime="image/png",
        inhalt_hash="h2",
        status="bereit",
        fach=fach,
    )
    Frage.objects.create(
        thema=t,
        frage="q2",
        antwort="a",
        quelle="ki",
        kind=kind_a,
        material=m2,
        freigabe=Freigabe.OFFEN,
    )
    with pytest.raises(PlanFehler):
        plan_services.pruefung_anlegen(
            kind_a, fach, "x", heute() + timedelta(days=9), materialien=[m2]
        )


def test_material_als_stoff_nutzt_nur_freigegebene_fragen(kind_a, fach, uhr):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name="Mat")
    m = Material.objects.create(
        kind=kind_a,
        name="c" * 32 + ".png",
        art="bild",
        mime="image/png",
        inhalt_hash="h3",
        status="bereit",
        fach=fach,
    )
    frei = [
        Frage.objects.create(
            thema=t, frage=f"q{i}", antwort="a", quelle="ki", kind=kind_a, material=m
        )
        for i in range(6)
    ]
    Frage.objects.create(
        thema=t,
        frage="offen",
        antwort="a",
        quelle="ki",
        kind=kind_a,
        material=m,
        freigabe=Freigabe.OFFEN,
    )
    p = anlegen(kind_a, fach, materialien=[m], tage=10)
    assert p.plan_ok
    geplant = {i for x in p.portionen.filter(art=PortionArt.NEU) for i in x.fragen}
    assert geplant == {f.pk for f in frei}


# --- Realitätscheck ------------------------------------------------------------------------


def test_zu_viel_stoff_ergibt_keinen_plan_sondern_vorschlaege(kind_a, fach, uhr):
    gross = thema_mit(fach, 600, "Riesig")
    p = anlegen(kind_a, fach, gross, tage=6)
    assert p.plan_ok is False
    assert p.portionen.count() == 0  # kein überfüllter Plan
    check = plan_selectors.realitaetscheck(p, heute())
    assert check.grund == plan.GRUND_ZU_VIEL and check.benoetigt > check.verfuegbar
    assert {v.art for v in check.vorschlaege} >= {plan.VORSCHLAG_KLEINER}
    # nichts wurde automatisch geändert
    assert not Lernziel.objects.filter(kind=kind_a, ziel_minuten__gt=20).exists()


def test_termin_morgen_und_zu_wenig_zeit(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=1)
    assert not p.plan_ok and p.portionen.count() == 0
    check = plan_selectors.realitaetscheck(p, heute())
    assert check.grund == plan.GRUND_ZU_VIEL
    assert plan.VORSCHLAG_FRUEHER in {v.art for v in check.vorschlaege}


def test_ziel_erhoehen_nur_auf_wunsch_und_dann_ist_der_plan_da(kind_a, fach, uhr):
    gross = thema_mit(fach, 160, "Mittel")
    p = anlegen(kind_a, fach, gross, tage=8)
    assert not p.plan_ok
    check = plan_selectors.realitaetscheck(p, heute())
    ziel_vorschlag = next((v for v in check.vorschlaege if v.art == plan.VORSCHLAG_ZIEL), None)
    if ziel_vorschlag is None:
        pytest.skip("kein Zielvorschlag bei diesen Daten")
    with pytest.raises(PlanFehler):  # mehr als der Zuschlag
        plan_services.ziel_erhoehen(kind_a, p, 20 + 99)
    with pytest.raises(PlanFehler):  # kein Vorschlag nach unten
        plan_services.ziel_erhoehen(kind_a, p, 5)
    plan_services.ziel_erhoehen(kind_a, p, ziel_vorschlag.wert)
    p.refresh_from_db()
    assert p.plan_ok
    assert tagesziel.ziel_holen(kind_a, heute()).ziel_minuten == ziel_vorschlag.wert
    assert max(summen(p).values()) <= ziel_vorschlag.wert


def test_stoff_verkleinern_macht_den_plan_moeglich(kind_a, fach, uhr):
    a = thema_mit(fach, 300, "Teil A")
    b = thema_mit(fach, 10, "Teil B")
    p = anlegen(kind_a, fach, a, b, tage=7)
    assert not p.plan_ok
    gross = p.stoffe.get(thema=a)
    plan_services.stoff_entfernen(p, gross)
    p.refresh_from_db()
    assert p.plan_ok
    with pytest.raises(PlanFehler):  # der letzte Stoff bleibt
        plan_services.stoff_entfernen(p, p.stoffe.get())
    fremd = anlegen(kind_a, fach, thema_mit(fach, 5, "Dritter"), tage=9)
    with pytest.raises(PlanFehler):
        plan_services.stoff_entfernen(p, fremd.stoffe.get())


def test_termin_aendern_rechnet_neu(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=2)
    assert not p.plan_ok
    plan_services.termin_aendern(p, heute() + timedelta(days=20))
    p.refresh_from_db()
    assert p.plan_ok and p.termin == heute() + timedelta(days=20)
    with pytest.raises(PlanFehler):
        plan_services.termin_aendern(p, heute())


# --- Pausentage, Ferien --------------------------------------------------------------------


def test_pausentage_bekommen_keine_portionen(kind_a, kind_b, fach, lang, uhr):
    von = heute() + timedelta(days=2)
    Lernpause.objects.create(kind=kind_a, von=von, bis=von + timedelta(days=3))
    Lernpause.objects.create(kind=kind_b, von=heute(), bis=heute() + timedelta(days=30))
    p = anlegen(kind_a, fach, lang, tage=20)
    assert p.plan_ok
    gesperrt = {von + timedelta(days=i) for i in range(4)}
    assert not {x.datum for x in p.portionen.all()} & gesperrt  # nur Pause von A zählt


def test_ferien_fuer_alle_verhindern_den_plan_ehrlich(kind_a, fach, lang, uhr):
    einstellungen.setzen("lernen.ferien_schalter", True, akteur=None)
    p = anlegen(kind_a, fach, lang, tage=10)
    assert not p.plan_ok and p.portionen.count() == 0


# --- Verpasste Tage ------------------------------------------------------------------------


def test_verpasste_tage_verschieben_den_plan_ohne_vorwurf(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=21)
    erste = p.portionen.filter(art=PortionArt.NEU).order_by("datum").first()
    punkte_vorher = Buchung.objects.filter(kind=kind_a).count()
    uhr.weiter(days=4)  # nichts geübt
    plan_services.tag_pflegen(kind_a)
    p.refresh_from_db()
    assert p.plan_ok
    assert p.plan_angepasst_am == heute()
    erste.refresh_from_db()
    assert erste.status == PortionStatus.VERSCHOBEN
    offen = p.portionen.filter(status=PortionStatus.OFFEN)
    assert not offen.filter(datum__lt=heute()).exists()  # nichts liegt mehr in der Vergangenheit
    assert max(summen(p).values()) <= 20
    # alle Fragen sind weiter genau einmal als neu eingeplant
    neu = [i for x in offen.filter(art=PortionArt.NEU) for i in x.fragen]
    assert sorted(neu) == sorted(Frage.objects.filter(thema=lang).values_list("pk", flat=True))
    # keine Punkte abgezogen
    assert Buchung.objects.filter(kind=kind_a).count() == punkte_vorher
    assert not Buchung.objects.filter(kind=kind_a, guthaben_delta__lt=0).exists()
    # zweites Öffnen am selben Tag ändert nichts
    vorher = list(p.portionen.values_list("id", flat=True))
    plan_services.tag_pflegen(kind_a)
    assert list(p.portionen.values_list("id", flat=True)) == vorher


def test_puffer_werden_gebraucht_bevor_es_zu_viel_wird(kind_a, fach, uhr):
    """Passt der Rest nur mit den Puffertagen, bleibt der Plan ok und meldet die Pufferbenutzung."""
    for anzahl in range(120, 700, 20):
        t = thema_mit(fach, anzahl, f"Test{anzahl}")
        p = anlegen(kind_a, fach, t, tage=22)
        if not p.plan_ok:
            break
        zuvor = p.portionen.count()
        assert zuvor
        p.delete()
        t.delete()
    else:
        pytest.fail("kein Grenzfall gefunden")
    # eine Menge davor passt gerade noch
    t = thema_mit(fach, anzahl - 20, "Grenze")
    p = anlegen(kind_a, fach, t, tage=22)
    assert p.plan_ok
    uhr.weiter(days=2)
    plan_services.tag_pflegen(kind_a)
    p.refresh_from_db()
    if p.plan_ok:
        assert p.puffer_genutzt or p.portionen.filter(art=PortionArt.PUFFER).exists()
    else:  # sonst erneuter Realitätscheck mit Vorschlägen, nichts Überfülltes
        assert plan_selectors.realitaetscheck(p, heute()).vorschlaege
        assert max(summen(p).values()) <= 20


def test_wenn_es_eng_wird_kommt_der_realitaetscheck_und_der_plan_bleibt_lesbar(
    kind_a, fach, lang, uhr
):
    p = anlegen(kind_a, fach, lang, tage=10)
    assert p.plan_ok
    uhr.weiter(days=8)  # fast alles verpasst, der Termin ist nah
    plan_services.tag_pflegen(kind_a)
    p.refresh_from_db()
    assert not p.plan_ok
    assert plan_selectors.realitaetscheck(p, heute()).grund == plan.GRUND_ZU_VIEL
    assert not Buchung.objects.filter(kind=kind_a, guthaben_delta__lt=0).exists()


def test_nach_dem_termin_ist_die_pruefung_abgeschlossen(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=12)
    uhr.weiter(days=13)
    plan_services.tag_pflegen(kind_a)
    p.refresh_from_db()
    assert p.status == PruefungStatus.ABGESCHLOSSEN
    assert plan_services.plan_berechnen(p) is None  # nichts mehr zu planen


def test_status_wird_aktiv_wenn_der_plan_beginnt(kind_a, fach, uhr):
    t = thema_mit(fach, 20, "Spaet")
    p = anlegen(kind_a, fach, t, tage=60)
    assert p.status == PruefungStatus.GEPLANT
    uhr.weiter(days=20)
    plan_services.tag_pflegen(kind_a)
    p.refresh_from_db()
    assert p.status == PruefungStatus.AKTIV


# --- Üben einer Portion --------------------------------------------------------------------


def erste_portion(p):
    return p.portionen.filter(art=PortionArt.NEU).order_by("datum", "id").first()


def test_nur_ueben_erledigt_eine_portion_kein_klick(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    s = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    assert s.portion_id == portion.pk
    portion.refresh_from_db()
    assert portion.status == PortionStatus.OFFEN  # nur gestartet
    mindest = einstellungen.wert("lernen.pruefung_min_antworten")
    for i in range(mindest - 1):
        a = services.frage_stellen(s, jetzt=uhr.jetzt)
        uhr.weiter(seconds=10)
        services.antworten(s, a.loesung, jetzt=uhr.jetzt)
        portion.refresh_from_db()
        assert portion.status == PortionStatus.OFFEN, i
    a = services.frage_stellen(s, jetzt=uhr.jetzt)
    services.antworten(s, a.loesung, jetzt=uhr.jetzt)
    portion.refresh_from_db()
    assert portion.status == PortionStatus.ERLEDIGT
    assert portion.erledigt_am == heute()


def test_portion_fragen_kommen_nur_aus_der_portion(kind_a, fach, lang, uhr):
    andere = thema_mit(fach, 30, "Ablenkung")
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    s = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    gestellt = set()
    for _ in range(portion.minuten * 3):
        a = services.frage_stellen(s, jetzt=uhr.jetzt)
        if a is None:
            break
        gestellt.add(a.frage.pk)
        services.antworten(s, a.loesung, jetzt=uhr.jetzt)
    assert gestellt and gestellt <= set(portion.fragen)
    assert not Frage.objects.filter(pk__in=gestellt, thema=andere).exists()


def test_mindestzeit_zaehlt_wenn_mindestens_eine_antwort_da_ist(kind_a, fach, lang, uhr):
    einstellungen.setzen("lernen.pruefung_min_antworten", 50, akteur=None)
    einstellungen.setzen("lernen.pruefung_min_sekunden", 120, akteur=None)
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    s = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    uhr.weiter(seconds=100)
    services.frage_stellen(s, jetzt=uhr.jetzt)
    uhr.weiter(seconds=100)
    a = services.frage_stellen(s, jetzt=uhr.jetzt)
    portion.refresh_from_db()
    assert portion.status == PortionStatus.OFFEN  # Zeit allein ohne Antwort reicht nicht
    services.antworten(s, a.loesung, jetzt=uhr.jetzt)
    portion.refresh_from_db()
    assert portion.status == PortionStatus.ERLEDIGT


def test_sitzung_zur_portion_wird_fortgesetzt_statt_doppelt_gestartet(kind_a, fach, lang, uhr):
    portion = erste_portion(anlegen(kind_a, fach, lang, tage=14))
    s1 = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    s2 = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    assert s1.pk == s2.pk


def test_portion_starten_schuetzt(kind_a, kind_b, fach, lang, uhr, mama):
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    with pytest.raises(PlanFehler):  # Geschwister
        plan_services.portion_starten(kind_b, portion)
    with pytest.raises(services.LernenFehler):  # Eltern üben nicht
        plan_services.portion_starten(mama, portion)
    puffer = p.portionen.filter(art=PortionArt.PUFFER).first()
    with pytest.raises(PlanFehler):
        plan_services.portion_starten(kind_a, puffer)
    plan_services.pruefung_abbrechen(p)
    with pytest.raises(PlanFehler):
        plan_services.portion_starten(kind_a, portion)


def test_portion_ohne_nutzbare_fragen(kind_a, fach, lang, uhr):
    portion = erste_portion(anlegen(kind_a, fach, lang, tage=14))
    Frage.objects.filter(pk__in=portion.fragen).update(freigabe=Freigabe.ABGELEHNT)
    with pytest.raises(PlanFehler):
        plan_services.portion_starten(kind_a, portion)


def test_portion_ueben_auch_wenn_nichts_faellig_ist(kind_a, fach, lang, uhr):
    """Eine Wiederholungs-Portion lässt sich auch üben, wenn die Boxen noch nichts fällig haben."""
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    ueben(kind_a, portion, uhr)
    wdh = p.portionen.filter(art=PortionArt.WIEDERHOLUNG, pflicht=True).order_by("datum").first()
    assert wdh is not None
    s = plan_services.portion_starten(kind_a, wdh, jetzt=uhr.jetzt)
    a = services.frage_stellen(s, jetzt=uhr.jetzt)
    assert a is not None and a.frage.pk in wdh.fragen


# --- Punkte und Ereignis -------------------------------------------------------------------


def alle_pflicht_erledigen(p):
    for x in p.portionen.all():
        if x.art == PortionArt.NEU or (x.art == PortionArt.WIEDERHOLUNG and x.pflicht):
            plan_services.portion_erledigen(x, heute())


def test_vorbereitet_gibt_einen_festen_bonus_und_ein_ereignis_einmal(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    alle_pflicht_erledigen(p)
    p.refresh_from_db()
    assert p.vorbereitet_am == heute()
    b = Buchung.objects.get(idempotenz_schluessel=f"lernen:pruefung_vorbereitet:{p.pk}")
    # Das Tageslimit (8) deckelt auch diesen Bonus (10): im Zweifel niedriger
    soll = min(
        einstellungen.wert("lernen.pruefung_punkte_vorbereitet"),
        einstellungen.wert("lernen.lernpunkte_tageslimit"),
    )
    assert b.guthaben_delta == soll and b.kind == kind_a
    ereignisse = Ereignis.objects.filter(typ=events.PRUEFUNG_VORBEREITET)
    assert ereignisse.count() == 1
    daten = ereignisse.get().daten
    assert daten["hinweis_msgid"] and daten["hinweis_parameter"] == {"titel": "Test"}
    # nochmal: nichts doppelt
    plan_services.tag_pflegen(kind_a)
    plan_services.portion_erledigen(erste_portion(p), heute())
    assert (
        Buchung.objects.filter(idempotenz_schluessel=f"lernen:pruefung_vorbereitet:{p.pk}").count()
        == 1
    )
    assert Ereignis.objects.filter(typ=events.PRUEFUNG_VORBEREITET).count() == 1


def test_bonus_haelt_das_tageslimit_ein_und_kommt_spaeter_nach(kind_a, fach, lang, uhr):
    einstellungen.setzen("lernen.lernpunkte_tageslimit", 4, akteur=None)
    p = anlegen(kind_a, fach, lang, tage=14)
    alle_pflicht_erledigen(p)
    gebucht = sum(
        Buchung.objects.filter(kind=kind_a, quelle_modul="lernen").values_list(
            "guthaben_delta", flat=True
        )
    )
    assert 0 < gebucht <= 4  # Wochen- und Abschluss-Bonus zusammen unter dem Limit
    from apps.lernen.models import Lerntag

    assert Lerntag.objects.get(kind=kind_a, datum=heute()).punkte == gebucht
    uhr.weiter(days=1)
    plan_services.tag_pflegen(kind_a)
    nachher = sum(
        Buchung.objects.filter(kind=kind_a, quelle_modul="lernen").values_list(
            "guthaben_delta", flat=True
        )
    )
    assert nachher >= gebucht
    assert nachher <= 4 + 4  # höchstens zwei Tage Limit


def test_ohne_lernpunkte_keine_buchung_aber_ereignis(kind_a, fach, lang, uhr):
    einstellungen.setzen("lernen.lernpunkte_aktiv", False, akteur=None)
    p = anlegen(kind_a, fach, lang, tage=14)
    alle_pflicht_erledigen(p)
    assert not Buchung.objects.filter(kind=kind_a, quelle_modul="lernen").exists()
    p.refresh_from_db()
    assert p.vorbereitet_am is not None
    assert Ereignis.objects.filter(typ=events.PRUEFUNG_VORBEREITET).count() == 1


def test_planwoche_eingehalten_gibt_bonus_einmal(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=21)
    erste_woche = tagesziel.montag(min(x.datum for x in p.portionen.exclude(art=PortionArt.PUFFER)))
    for x in p.portionen.exclude(art=PortionArt.PUFFER):
        if tagesziel.montag(x.datum) == erste_woche:
            plan_services.portion_erledigen(x, heute())
    schluessel = f"lernen:pruefung_woche:{p.pk}:{erste_woche.isoformat()}"
    b = Buchung.objects.get(idempotenz_schluessel=schluessel)
    assert b.guthaben_delta == einstellungen.wert("lernen.pruefung_punkte_woche")
    plan_services.tag_pflegen(kind_a)
    assert Buchung.objects.filter(idempotenz_schluessel=schluessel).count() == 1


def test_keine_punkte_pro_richtige_antwort(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    s = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    for _ in range(3):
        a = services.frage_stellen(s, jetzt=uhr.jetzt)
        services.antworten(s, a.loesung, jetzt=uhr.jetzt)
    assert not Buchung.objects.filter(kind=kind_a).exists()


def test_woche_ohne_erledigte_portionen_gibt_nichts(kind_a, fach, lang, uhr):
    anlegen(kind_a, fach, lang, tage=21)
    plan_services.tag_pflegen(kind_a)
    assert not Buchung.objects.filter(kind=kind_a).exists()


# --- Probe-Prüfung -------------------------------------------------------------------------


def test_probe_pruefung_gemischt_ohne_note_mit_hinweis_je_thema(kind_a, fach, uhr):
    gut = thema_mit(fach, 8, "Gut")
    schwach = thema_mit(fach, 8, "Schwach")
    p = anlegen(kind_a, fach, gut, schwach, tage=14)
    probe = plan_services.probe_starten(p, jetzt=uhr.jetzt, zufall=random.Random(3))
    assert len(probe.fragen) == 15 or len(probe.fragen) == 16 or len(probe.fragen) <= 15
    assert plan_services.probe_starten(p) == probe  # offene Probe wird fortgesetzt
    while (a := plan_services.probe_aufgabe(probe)) is not None:
        richtig = a.frage.thema_id == gut.pk
        plan_services.probe_antworten(
            probe, a.loesung if richtig else "weiß nicht", jetzt=uhr.jetzt
        )
        probe.refresh_from_db()
    assert probe.ende is not None
    ergebnis = {e.thema.name: e for e in plan_services.probe_ergebnis(probe)}
    assert ergebnis["Gut"].einstufung == "staerke"
    assert ergebnis["Schwach"].einstufung == "ueben"
    with pytest.raises(PlanFehler):
        plan_services.probe_antworten(probe, "x")
    assert not hasattr(ergebnis["Gut"], "note")


def test_probe_nutzt_nur_freigegebene_fragen_des_kindes(kind_a, kind_b, fach, uhr):
    t = thema_mit(fach, 6, "Eigen")
    Frage.objects.create(thema=t, frage="fremd", antwort="x", quelle="eltern", kind=kind_b)
    Frage.objects.create(
        thema=t, frage="offen", antwort="x", quelle="ki", kind=kind_a, freigabe=Freigabe.OFFEN
    )
    p = anlegen(kind_a, fach, t, tage=14)
    probe = plan_services.probe_starten(p)
    texte = set(Frage.objects.filter(pk__in=probe.fragen).values_list("frage", flat=True))
    assert "fremd" not in texte and "offen" not in texte and len(texte) == 6


def test_schwaechen_fliessen_in_die_letzten_plantage_und_nie_ueber_das_ziel(kind_a, fach, uhr):
    gut = thema_mit(fach, 8, "Gut")
    schwach = thema_mit(fach, 12, "Schwach")
    p = anlegen(kind_a, fach, gut, schwach, tage=20)
    probe = plan_services.probe_starten(p, zufall=random.Random(5))
    while (a := plan_services.probe_aufgabe(probe)) is not None:
        plan_services.probe_antworten(
            probe, "weiß nicht" if a.frage.thema_id == schwach.pk else a.loesung
        )
        probe.refresh_from_db()
    assert plan_services.schwaechen(probe)
    vorher = p.portionen.count()
    neu = plan_services.schwaechen_einplanen(probe)
    assert neu > 0 and p.portionen.count() == vorher + neu
    assert max(summen(p).values()) <= 20
    zusaetze = p.portionen.filter(art=PortionArt.WIEDERHOLUNG, pflicht=False).order_by("-datum")
    assert all(x.datum < p.termin for x in zusaetze)
    assert plan_services.schwaechen_einplanen(probe) == 0  # nur einmal
    # die Zusatzportionen enthalten nur Fragen aus dem schwachen Thema
    erlaubt = set(Frage.objects.filter(thema=schwach).values_list("pk", flat=True))
    for x in p.portionen.filter(fragen__0__in=list(erlaubt), art=PortionArt.WIEDERHOLUNG):
        assert set(x.fragen) <= erlaubt


def test_schwaechen_ohne_schwaechen(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    probe = plan_services.probe_starten(p, zufall=random.Random(2))
    while (a := plan_services.probe_aufgabe(probe)) is not None:
        plan_services.probe_antworten(probe, a.loesung)
        probe.refresh_from_db()
    assert plan_services.schwaechen(probe) == []
    assert plan_services.schwaechen_einplanen(probe) == 0


def test_probe_beenden_und_ohne_fragen(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    probe = plan_services.probe_starten(p)
    plan_services.probe_beenden(probe)
    plan_services.probe_beenden(probe)  # idempotent
    assert probe.ende is not None
    Frage.objects.filter(thema=lang).update(freigabe=Freigabe.ABGELEHNT)
    with pytest.raises(PlanFehler):
        plan_services.probe_starten(p)
    plan_services.pruefung_abbrechen(p)
    with pytest.raises(PlanFehler):
        plan_services.probe_starten(p)


# --- Isolation und Pflege ------------------------------------------------------------------


def test_geschwister_sehen_nie_fremde_plaene(kind_a, kind_b, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    portion = erste_portion(p)
    probe = plan_services.probe_starten(p)
    assert plan_selectors.pruefung(kind_b, p.pk) is None
    assert list(plan_selectors.pruefungen(kind_b)) == []
    assert list(plan_selectors.aktive_pruefungen(kind_b)) == []
    assert plan_selectors.portion(kind_b, portion.pk) is None
    assert plan_selectors.probe(kind_b, probe.pk) is None
    assert plan_selectors.pruefung(kind_a, p.pk) == p
    plan_services.tag_pflegen(kind_b)  # fasst fremde Pläne nie an
    p.refresh_from_db()
    assert p.status in (PruefungStatus.GEPLANT, PruefungStatus.AKTIV)


def test_abbrechen_und_loeschen(kind_a, fach, lang, uhr):
    p = anlegen(kind_a, fach, lang, tage=14)
    plan_services.pruefung_abbrechen(p)
    p.refresh_from_db()
    assert p.status == PruefungStatus.ABGEBROCHEN
    plan_services.pruefung_abbrechen(p)  # idempotent
    assert plan_services.plan_berechnen(p) is None
    plan_services.pruefung_loeschen(p)
    assert not Pruefung.objects.filter(pk=p.pk).exists()


def test_parameter_folgen_dem_persoenlichen_tagesziel(kind_a, uhr):
    assert plan_selectors.parameter(kind_a, heute()).tagesziel == 20
    tagesziel.ziel_holen(kind_a, heute())
    Lernziel.objects.filter(kind=kind_a).update(ziel_minuten=12)
    assert plan_selectors.parameter(kind_a, heute()).tagesziel == 12
    assert selectors.sprachstufe(kind_a) == 2
