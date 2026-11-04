"""Mathe-Generator im Üben (SPEC 21.13): Sitzung, Lernstand, Wiederholung, Auswahl, Einstellungen,
Aufräumen, Prüfungsplan und Probe-Prüfung. Alles lokal, ohne KI."""

import random
from datetime import timedelta

import pytest
from django.urls import reverse

from apps.kern import einstellungen, zeit
from apps.lernen import mathe_aufgaben, plan_selectors, plan_services, selectors, services
from apps.lernen.mathe import registry, schwierigkeit
from apps.lernen.models import (
    Ergebnis,
    Fach,
    Frage,
    Lernsitzung,
    Lernstand,
    Pruefung,
    PruefungStatus,
    Thema,
    Versuch,
)
from apps.lernen.startdaten import MATHE_GENERATOR_THEMEN, mathe_themen_anlegen


@pytest.fixture
def mathe(db):
    return Fach.objects.get(schluessel="mathe")


def stufe(kind, mathe, klasse, niveau="Grundniveau"):
    services.leistungsstufe_setzen(kind, mathe, niveau, klasse)


def thema(mathe, schluessel):
    return Thema.objects.get(fach=mathe, schluessel=schluessel)


def start(kind, mathe, **extra):
    extra.setdefault("ziel_fragen", 100)
    return services.sitzung_starten(kind, mathe, **extra)


def richtig(s, rng):
    a = services.frage_stellen(s, zufall=rng)
    return a, services.antworten(s, a.loesung)


def falsch(s, rng):
    a = services.frage_stellen(s, zufall=rng)
    return a, services.antworten(s, "99999,5")


def alle_generatoren_aus_ausser(*keys):
    einstellungen.setzen(
        "lernen.mathe_rechenarten_aus",
        [k for k in registry.schluessel_alle() if k not in keys],
        akteur=None,
    )


# --- Startdaten und Themen ------------------------------------------------------------------------


def test_themen_sind_den_generatoren_zugeordnet(mathe):
    schluessel = set(
        Thema.objects.filter(fach=mathe).exclude(schluessel="").values_list("schluessel", flat=True)
    )
    assert schluessel == set(MATHE_GENERATOR_THEMEN) == set(registry.themen_schluessel())
    for s, (klasse, _name, _platz) in MATHE_GENERATOR_THEMEN.items():
        assert thema(mathe, s).klassenstufe == klasse


def test_themenmigration_ist_additiv_und_idempotent(mathe):
    vorher = list(Thema.objects.values_list("pk", "name", "klassenstufe", "schluessel"))
    bruch = Thema.objects.get(fach=mathe, klassenstufe=6, name="Brüche")
    Frage.objects.create(
        thema=bruch, typ="frage", frage="Eltern-Frage?", antwort="ja", quelle="eltern"
    )
    mathe_themen_anlegen(Fach, Thema)
    mathe_themen_anlegen(Fach, Thema)
    assert list(Thema.objects.values_list("pk", "name", "klassenstufe", "schluessel")) == vorher
    assert bruch.fragen.count() == 1  # vorhandene Daten bleiben


def test_themenmigration_verbindet_vorhandenes_und_legt_fehlendes_an(mathe):
    Thema.objects.filter(fach=mathe, schluessel="mathe_8_dreisatz").delete()
    Thema.objects.filter(fach=mathe, schluessel="mathe_6_brueche").update(schluessel="")
    mathe_themen_anlegen(Fach, Thema)
    assert Thema.objects.filter(fach=mathe, schluessel="mathe_8_dreisatz").count() == 1
    assert (
        Thema.objects.filter(
            fach=mathe, klassenstufe=6, name="Brüche", schluessel="mathe_6_brueche"
        ).count()
        == 1
    )


def test_einstellungen_haben_startwerte(db):
    assert einstellungen.wert("lernen.mathe_rechenarten_aus") == []
    assert einstellungen.wert("lernen.mathe_aufgaben_je_runde") == 0
    assert einstellungen.wert("lernen.mathe_zahlenraum_max") == 0
    assert (
        einstellungen.wert("lernen.mathe_ziel_von_prozent"),
        einstellungen.wert("lernen.mathe_ziel_bis_prozent"),
    ) == (70, 85)


# --- Der Ablauf -----------------------------------------------------------------------------------


def test_aufgabe_wird_als_frage_zeile_mit_seed_und_parametern_angelegt(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    s = start(kind_a, mathe)
    a = services.frage_stellen(s, zufall=random.Random(1))
    f = a.frage
    assert (f.generiert, f.quelle, f.kind_id, f.typ, f.freigabe) == (
        True,
        "system",
        None,
        "frage",
        "freigegeben",
    )
    assert f.generator in registry.schluessel_alle() and 1 <= f.gen_schwierigkeit <= 5
    assert f.gen_daten["seed"] >= 0 and f.gen_daten["typ"] and f.gen_daten["parameter"]
    assert f.gen_daten["loesung"]["anzeige"] == f.antwort == a.loesung
    assert f.frage == a.text and a.generiert and not a.mehrere
    # reproduzierbar: Seed + Generator + Schwierigkeit ergeben dieselbe Aufgabe
    neu = registry.erzeugen(f.generator, f.gen_schwierigkeit, f.gen_daten["seed"])
    assert neu.text == f.frage and neu.to_dict() == f.gen_daten


def test_richtig_falsch_hilfe_loesung_wie_bei_vokabeln(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    s = start(kind_a, mathe)
    rng = random.Random(2)
    a, antwort = richtig(s, rng)
    assert antwort.ergebnis == Ergebnis.RICHTIG and antwort.loesung == ""
    v = Versuch.objects.get(sitzung=s, frage=a.frage)
    assert v.ergebnis == Ergebnis.RICHTIG and v.fehlertyp == ""
    stand = Lernstand.objects.get(kind=kind_a, frage=a.frage)
    assert (stand.box, stand.versuche, stand.richtige) == (1, 1, 1)
    b, antwort = falsch(s, rng)
    assert antwort.ergebnis == Ergebnis.NOCH_NICHT and antwort.loesung == b.loesung
    assert Lernstand.objects.get(kind=kind_a, frage=b.frage).box == 0
    c = services.frage_stellen(s, zufall=rng)
    assert services.hilfe(s)  # Hinweis auf die Lösung, kostet nichts
    assert services.frage_stellen(s).frage == c.frage  # Neuladen: dieselbe Aufgabe
    rueck = services.loesung_zeigen(s)
    assert (
        rueck.loesung == c.loesung and Versuch.objects.get(sitzung=s, frage=c.frage).hilfestufe == 2
    )
    s.refresh_from_db()
    assert (s.versuche, s.richtig) == (3, 1)


def test_fast_ungekuerzt_gibt_zweite_chance_mit_hinweis_und_fehlertyp(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    alle_generatoren_aus_ausser("bruch_kuerzen")
    s = start(kind_a, mathe)
    a = services.frage_stellen(s, zufall=random.Random(3))
    z, n = a.frage.gen_daten["parameter"]["zaehler"], a.frage.gen_daten["parameter"]["nenner"]
    rueck = services.antworten(s, f"{z}/{n}")  # genau die Aufgabe: nicht gekürzt
    assert rueck.ergebnis == Ergebnis.FAST and rueck.nochmal and "kürzen" in rueck.text
    assert Versuch.objects.get(sitzung=s).fehlertyp == "nicht_gekuerzt"
    assert services.frage_stellen(s).frage == a.frage  # dieselbe Aufgabe noch einmal
    rueck = services.antworten(s, a.loesung)
    assert rueck.ergebnis == Ergebnis.RICHTIG
    assert Lernstand.objects.get(kind=kind_a, frage=a.frage).richtige == 1


def test_bruch_wird_als_bruch_angezeigt_nicht_am_schraegstrich_geteilt(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    alle_generatoren_aus_ausser("bruch_kuerzen")
    s = start(kind_a, mathe)
    a = services.frage_stellen(s, zufall=random.Random(4))
    assert "/" in a.loesung and not a.mehrere


def test_ende_nach_ziel_fragen_und_aufgaben_je_runde(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    einstellungen.setzen("lernen.mathe_aufgaben_je_runde", 3, akteur=None)
    s = services.sitzung_starten(kind_a, mathe)
    assert s.ziel_fragen == 3
    rng = random.Random(5)
    for _i in range(3):
        richtig(s, rng)
    assert services.frage_stellen(s, zufall=rng) is None
    einstellungen.setzen("lernen.mathe_aufgaben_je_runde", 0, akteur=None)
    assert services.sitzung_starten(kind_a, mathe).ziel_fragen == einstellungen.wert(
        "lernen.fragen_normal"
    )


def test_aufgaben_je_runde_gilt_nicht_fuer_andere_faecher(kind_a, fach):
    einstellungen.setzen("lernen.mathe_aufgaben_je_runde", 3, akteur=None)
    assert services.sitzung_starten(kind_a, fach).ziel_fragen != 3


# --- Auswahl --------------------------------------------------------------------------------------


@pytest.mark.parametrize("klasse,band", [(3, 3), (4, 3), (5, 6), (6, 6), (7, 6), (8, 8), (10, 8)])
def test_klassenstufe_bestimmt_die_inhalte(kind_a, mathe, klasse, band):
    stufe(kind_a, mathe, klasse)
    s = start(kind_a, mathe)
    rng = random.Random(6)
    klassen = []
    for _i in range(40):
        a, _ = richtig(s, rng)
        klassen.append(a.frage.gen_daten["klassenstufe"])
    assert max(klassen) == band
    assert klassen.count(band) >= 25  # Hauptsache aktuelle Stufe, Rest zum Auffrischen
    if band == 3:
        assert set(klassen) == {3}


def test_ohne_klassenstufe_zaehlt_wie_klasse_6_und_alle_themen(kind_a, mathe):
    s = start(kind_a, mathe)
    rng = random.Random(7)
    klassen = {richtig(s, rng)[0].frage.gen_daten["klassenstufe"] for _i in range(60)}
    assert 6 in klassen and len(klassen) >= 2


def test_gewaehltes_thema_bleibt_beim_thema(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    t = thema(mathe, "mathe_6_prozent")
    s = start(kind_a, mathe, thema=t)
    rng = random.Random(8)
    for _i in range(20):
        a, _ = richtig(s, rng)
        assert a.frage.thema == t and a.frage.gen_daten["thema"] == "mathe_6_prozent"


@pytest.mark.parametrize(
    "niveau,intensitaet,erwartet",
    [
        ("Grundniveau", "aufwaermen", 1),
        ("Grundniveau", "normal", 2),
        ("Grundniveau", "herausforderung", 3),
        ("Erweiterungsniveau", "aufwaermen", 2),
        ("Erweiterungsniveau", "normal", 3),
        ("Erweiterungsniveau", "herausforderung", 4),
    ],
)
def test_niveau_und_intensitaet_bestimmen_die_startschwierigkeit(
    kind_a, mathe, niveau, intensitaet, erwartet
):
    stufe(kind_a, mathe, 6, niveau)
    s = start(kind_a, mathe, intensitaet=intensitaet)
    a = services.frage_stellen(s, zufall=random.Random(9))
    assert a.frage.gen_schwierigkeit == erwartet


def test_schwierigkeit_folgt_den_antworten_im_zielbereich(kind_a, mathe):
    stufe(kind_a, mathe, 6, "Erweiterungsniveau")
    alle_generatoren_aus_ausser("prozent_wert")
    s = start(kind_a, mathe)
    rng = random.Random(10)
    stufen = [richtig(s, rng)[0].frage.gen_schwierigkeit for _i in range(14)]
    assert (
        stufen[0] == 3 and stufen[-1] == 4 and stufen == sorted(stufen)
    )  # richtig: schwerer, Normal-Grenze 4
    # nun viele Fehler: wieder leichter
    for _i in range(8):
        falsch(s, rng)
    s.refresh_from_db()
    a = services.frage_stellen(s, zufall=rng)
    assert a.frage.gen_schwierigkeit < 4 or s.frust_erkannt


def test_frust_senkt_die_schwierigkeit(kind_a, mathe):
    stufe(kind_a, mathe, 6, "Erweiterungsniveau")
    alle_generatoren_aus_ausser("prozent_wert")
    s = start(kind_a, mathe, intensitaet="herausforderung")
    rng = random.Random(11)
    erste = services.frage_stellen(s, zufall=rng).frage.gen_schwierigkeit
    assert erste == 4
    services.antworten(s, "xx")
    for _i in range(2):
        falsch(s, rng)
    s.refresh_from_db()
    assert s.frust_erkannt and s.intensitaet == "normal"
    danach = services.frage_stellen(s, zufall=rng).frage.gen_schwierigkeit
    assert danach < erste


def test_themen_werden_gemischt_nicht_in_bloecken(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    s = start(kind_a, mathe)
    rng = random.Random(12)
    gens, themen = [], []
    for _i in range(40):
        a, _ = richtig(s, rng)
        gens.append(a.frage.generator)
        themen.append(a.frage.gen_daten["thema"])
    assert len(set(themen)) >= 4 and len(set(gens)) >= 6
    lauf = max(len(list(g)) for _k, g in __import__("itertools").groupby(themen))
    assert lauf <= 3
    assert sum(a == b for a, b in zip(gens, gens[1:], strict=False)) <= 3  # selten zweimal dasselbe


def test_schwaechen_kommen_oefter(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    alle_generatoren_aus_ausser("bruch_kuerzen", "prozent_wert", "klammern", "dezimal_runden")
    s = start(kind_a, mathe)
    rng = random.Random(13)
    for _i in range(20):  # Prozent liegt dem Kind, Brüche nicht
        a = services.frage_stellen(s, zufall=rng)
        if a.frage.generator == "bruch_kuerzen":
            services.antworten(s, "0")
        else:
            services.antworten(s, a.loesung)
    folgende = []
    for _i in range(40):
        a = services.frage_stellen(s, zufall=rng)
        folgende.append(a.frage.generator)
        services.antworten(s, "0" if a.frage.generator == "bruch_kuerzen" else a.loesung)
    assert folgende.count("bruch_kuerzen") >= folgende.count("klammern")


# --- Wiederholung ---------------------------------------------------------------------------------


def test_faellige_schwaeche_kommt_als_gleichartige_neue_aufgabe(kind_a, mathe, uhr):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("add_sub_100")
    s = start(kind_a, mathe)
    rng = random.Random(14)
    alt, _ = falsch(s, rng)
    stand = Lernstand.objects.get(kind=kind_a, frage=alt.frage)
    assert stand.box == 0
    services.sitzung_beenden(s)
    uhr.weiter(days=2)
    s2 = start(kind_a, mathe, vorhaben="wiederholen", ziel_fragen=5)
    neu = services.frage_stellen(s2, zufall=rng)
    assert neu.frage.pk != alt.frage.pk and neu.frage.generator == alt.frage.generator
    assert neu.frage.gen_daten["typ"] == alt.frage.gen_daten["typ"]
    assert neu.frage.gen_schwierigkeit == alt.frage.gen_schwierigkeit
    assert neu.frage.gen_daten["parameter"] != alt.frage.gen_daten["parameter"]
    assert neu.text != alt.text
    stand.refresh_from_db()
    assert stand.frage_id == neu.frage.pk and stand.box == 0  # Stand wandert mit, Box bleibt
    assert not alt.frage.staende.exists()
    services.antworten(s2, neu.loesung)
    stand.refresh_from_db()
    assert (stand.box, stand.versuche, stand.richtige) == (1, 2, 1)


def test_nicht_faellige_aufgaben_kommen_nicht_wieder(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    s = start(kind_a, mathe, vorhaben="wiederholen")
    rng = random.Random(15)
    alt, _ = richtig(s, rng)
    neu = services.frage_stellen(s, zufall=rng)
    assert neu.frage.pk != alt.frage.pk
    assert Lernstand.objects.get(kind=kind_a, frage=alt.frage).faellig_am > zeit.heute()


def test_stolperstellen_kommen_zuerst(kind_a, mathe, uhr):
    stufe(kind_a, mathe, 3)
    s = start(kind_a, mathe)
    rng = random.Random(16)
    richtig(s, rng)
    schwach, _ = falsch(s, rng)
    richtig(s, rng)
    services.sitzung_beenden(s)
    uhr.weiter(days=20)
    s2 = start(kind_a, mathe, vorhaben="stolperstellen")
    a = services.frage_stellen(s2, zufall=rng)
    assert a.frage.generator == schwach.frage.generator


def test_vorhaben_neu_bringt_neues_auch_wenn_etwas_faellig_ist(kind_a, mathe, uhr):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("einmaleins")
    s = start(kind_a, mathe)
    rng = random.Random(17)
    alt, _ = falsch(s, rng)
    services.sitzung_beenden(s)
    uhr.weiter(days=3)
    s2 = start(kind_a, mathe, vorhaben="neu")
    neu = services.frage_stellen(s2, zufall=rng)
    assert neu.frage.pk != alt.frage.pk
    assert Lernstand.objects.get(kind=kind_a, frage=alt.frage)  # unberührt, nicht gewandert
    assert not Lernstand.objects.filter(kind=kind_a, frage=neu.frage).exists()


def test_keine_doppelte_aufgabe_in_einer_sitzung(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("einmaleins")
    s = start(kind_a, mathe, intensitaet="aufwaermen", ziel_fragen=50)
    rng = random.Random(18)
    texte = [richtig(s, rng)[0].text for _i in range(25)]
    assert len(set(texte)) == len(texte)


# --- Isolation ------------------------------------------------------------------------------------


def test_kinder_sind_isoliert(kind_a, kind_b, mathe, uhr):
    stufe(kind_a, mathe, 3)
    stufe(kind_b, mathe, 3)
    sa = start(kind_a, mathe)
    rng = random.Random(19)
    a, _ = falsch(sa, rng)
    services.sitzung_beenden(sa)
    assert not Lernstand.objects.filter(kind=kind_b).exists()
    assert not Versuch.objects.filter(sitzung__kind=kind_b).exists()
    uhr.weiter(days=3)
    sb = start(kind_b, mathe, vorhaben="wiederholen")
    b = services.frage_stellen(sb, zufall=rng)
    assert b.frage.pk != a.frage.pk  # fällig war nur etwas bei Kind A
    assert Lernstand.objects.get(kind=kind_a, frage=a.frage)  # Kind A unverändert
    # Aufgaben eines Kindes sind für ein anderes nie "neu" in Vokabel-Auswahl
    t = a.frage.thema
    assert not selectors.nutzbare_fragen(t, kind_b).filter(pk=a.frage.pk).exists()
    assert selectors.nutzbare_fragen(t, kind_b, mit_generierten=True).filter(pk=a.frage.pk).exists()


def test_fremde_sitzung_bekommt_keine_aufgabe_des_anderen(kind_a, kind_b, mathe, kind_client):
    stufe(kind_a, mathe, 3)
    stufe(kind_b, mathe, 3)
    s = start(kind_b, mathe)
    services.frage_stellen(s, zufall=random.Random(20))
    assert kind_client.get(reverse("lernen:sitzung", args=[s.pk])).status_code == 404


# --- Einstellungen --------------------------------------------------------------------------------


def test_rechenarten_koennen_abgeschaltet_werden(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    aus = [k for k in registry.schluessel_alle() if k != "einmaleins"]
    einstellungen.setzen("lernen.mathe_rechenarten_aus", aus, akteur=None)
    s = start(kind_a, mathe)
    rng = random.Random(21)
    assert {richtig(s, rng)[0].frage.generator for _i in range(10)} == {"einmaleins"}
    assert selectors.mathe_rechenarten() == {"einmaleins"}


def test_ohne_rechenarten_gibt_es_nichts_zu_ueben(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    einstellungen.setzen(
        "lernen.mathe_rechenarten_aus", list(registry.schluessel_alle()), akteur=None
    )
    s = start(kind_a, mathe)
    assert services.frage_stellen(s, zufall=random.Random(22)) is None
    assert not selectors.ist_generatorthema(thema(mathe, "mathe_3_plusminus"))


def test_abgeschaltetes_thema_erscheint_nicht_in_der_auswahl(kind_a, mathe, kind_client):
    stufe(kind_a, mathe, 6)
    einstellungen.setzen(
        "lernen.mathe_rechenarten_aus",
        [g.schluessel for g in registry.generatoren_fuer(thema="mathe_6_brueche")],
        akteur=None,
    )
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "Prozentrechnung" in html and "Dezimalzahlen" in html
    assert "Brüche" not in html


def test_obergrenze_fuer_zahlenraeume(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("add_sub_1000")
    einstellungen.setzen("lernen.mathe_zahlenraum_max", 100, akteur=None)
    s = start(kind_a, mathe)
    rng = random.Random(23)
    for _i in range(20):
        a, _ = richtig(s, rng)
        p = a.frage.gen_daten["parameter"]
        assert p["a"] <= 100 and p["b"] <= 100 and p["grenze"] == 100


def test_startseite_zeigt_mathe_themen_der_klassenstufe(kind_a, mathe, kind_client):
    stufe(kind_a, mathe, 6)
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "Brüche" in html and "Rechengesetze und Klammern" in html
    assert "Dreisatz" not in html  # Klasse 8


# --- Ablauf über die Seiten -----------------------------------------------------------------------


def test_ganzer_ablauf_per_seite(kind_client, kind_a, mathe):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("einmaleins")
    antwort = kind_client.post(
        reverse("lernen:los"),
        {
            "was": f"fach:{mathe.pk}",
            "intensitaet": "normal",
            "vorhaben": "neu",
            "strategie": "laut",
        },
    )
    s = Lernsitzung.objects.get(pk=int(antwort["Location"].rstrip("/").split("/")[-1]))
    seite = kind_client.get(reverse("lernen:sitzung", args=[s.pk])).content.decode()
    assert "data-lernen-frage" in seite and "=" in seite
    aufgabe = services.frage_stellen(s)
    post = kind_client.post(reverse("lernen:antwort", args=[s.pk]), {"eingabe": aufgabe.loesung})
    assert post.status_code == 200
    assert Versuch.objects.get(sitzung=s).ergebnis == Ergebnis.RICHTIG


# --- Aufräumen ------------------------------------------------------------------------------------


def _alt_machen(*fragen, tage=100):
    Frage.objects.filter(pk__in=[f.pk for f in fragen]).update(
        erstellt=zeit.jetzt() - timedelta(days=tage)
    )


def test_aufraeumen_loescht_alte_zeilen_ohne_lernstand(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    s = start(kind_a, mathe)
    rng = random.Random(24)
    erste, _ = richtig(s, rng)  # hat Lernstand
    offen = services.frage_stellen(s, zufall=rng).frage  # offene Aufgabe, noch ohne Versuch
    ohne_stand = mathe_aufgaben.speichern(registry.erzeugen("einmaleins", 1, 5), erste.frage.thema)
    neu = mathe_aufgaben.speichern(registry.erzeugen("einmaleins", 1, 6), erste.frage.thema)
    _alt_machen(erste.frage, ohne_stand)
    Lernstand.objects.filter(frage=erste.frage).update(faellig_am=zeit.heute() + timedelta(days=5))
    assert mathe_aufgaben.aufraeumen(zeit.jetzt()) == 1
    assert Frage.objects.filter(pk=erste.frage.pk).exists()  # hat noch einen Termin
    assert not Frage.objects.filter(pk=ohne_stand.pk).exists()
    assert Frage.objects.filter(pk__in=[neu.pk, offen.pk]).count() == 2  # jung genug


def test_aufraeumen_vergisst_sehr_alte_staende_und_loescht_dann_die_zeile(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    s = start(kind_a, mathe)
    a, _ = richtig(s, random.Random(25))
    _alt_machen(a.frage)
    Lernstand.objects.filter(frage=a.frage).update(faellig_am=zeit.heute() - timedelta(days=200))
    assert mathe_aufgaben.aufraeumen(zeit.jetzt()) == 1
    assert not Frage.objects.filter(pk=a.frage.pk).exists()
    assert not Versuch.objects.filter(sitzung=s).exists()  # Versuche gehen mit
    s.refresh_from_db()
    assert s.versuche == 1  # die Zähler der Sitzung bleiben


def test_aufraeumen_ohne_erzeugte_zeilen_ist_leer_und_laesst_andere_fragen(kind_a, mathe, fach):
    n = Frage.objects.count()
    assert mathe_aufgaben.aufraeumen(zeit.jetzt()) == 0
    assert Frage.objects.count() == n


def test_aufraeumen_laeuft_beim_start_einer_sitzung(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    alt = mathe_aufgaben.speichern(
        registry.erzeugen("einmaleins", 1, 5), thema(mathe, "mathe_3_einmaleins")
    )
    _alt_machen(alt)
    start(kind_a, mathe)
    assert not Frage.objects.filter(pk=alt.pk).exists()


def test_aufbewahrungsfrist_ist_eine_einstellung(kind_a, mathe):
    alt = mathe_aufgaben.speichern(
        registry.erzeugen("einmaleins", 1, 5), thema(mathe, "mathe_3_einmaleins")
    )
    _alt_machen(alt, tage=20)
    assert mathe_aufgaben.aufraeumen(zeit.jetzt()) == 0
    einstellungen.setzen("lernen.mathe_aufbewahren_tage", 10, akteur=None)
    assert mathe_aufgaben.aufraeumen(zeit.jetzt()) == 1


# --- Prüfungsplan und Probe-Prüfung ---------------------------------------------------------------


def _pruefung(kind, mathe, *schluessel, tage=21):
    return plan_services.pruefung_anlegen(
        kind,
        mathe,
        "Mathe-Arbeit",
        zeit.heute() + timedelta(days=tage),
        themen=[thema(mathe, k) for k in schluessel],
    )


def test_pruefungspool_ist_fest_und_idempotent(kind_a, kind_b, mathe):
    stufe(kind_a, mathe, 6)
    t = thema(mathe, "mathe_6_brueche")
    ids = mathe_aufgaben.pruefungspool(t, kind_a)
    assert len(ids) == len(set(ids)) == einstellungen.wert("lernen.mathe_pruefung_aufgaben")
    n = Frage.objects.filter(generiert=True).count()
    assert mathe_aufgaben.pruefungspool(t, kind_a) == ids
    assert Frage.objects.filter(generiert=True).count() == n
    assert {f.gen_daten["thema"] for f in Frage.objects.filter(pk__in=ids)} == {"mathe_6_brueche"}
    # je Kind eigene Seeds
    assert set(mathe_aufgaben.pruefungspool(t, kind_b)).isdisjoint(ids)
    # Rechenarten durchmischt
    assert len({f.generator for f in Frage.objects.filter(pk__in=ids)}) == 3


def test_pruefungsplan_mit_mathe_thema_und_portionen(kind_a, mathe, uhr):
    stufe(kind_a, mathe, 6)
    p = _pruefung(kind_a, mathe, "mathe_6_brueche", "mathe_6_prozent")
    assert p.plan_ok and p.portionen.exists()
    ids = set(plan_selectors.stoffe_fragen(p).popitem()[1])
    assert ids and all(Frage.objects.get(pk=i).generiert for i in ids)
    portion = p.portionen.filter(art="neu").order_by("datum").first()
    s = plan_services.portion_starten(kind_a, portion, jetzt=uhr.jetzt)
    assert s.portion_id == portion.pk
    rng = random.Random(26)
    gestellt = []
    for _i in range(s.ziel_fragen):
        a = services.frage_stellen(s, zufall=rng)
        if a is None:
            break
        assert a.frage.pk in portion.fragen and a.generiert
        gestellt.append(a.frage.pk)
        assert services.antworten(s, a.loesung).ergebnis == Ergebnis.RICHTIG
    assert gestellt and len(set(gestellt)) == len(gestellt)
    s.refresh_from_db()
    assert s.richtig == s.versuche == len(gestellt)


def test_pruefung_ohne_generator_thema_bleibt_wie_vorher(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    geo = Thema.objects.get(fach=mathe, klassenstufe=3, name="Geometrische Formen")
    assert not selectors.ist_generatorthema(geo)
    assert (
        plan_selectors.stoff_fragen(
            Pruefung.objects.create(
                kind=kind_a, fach=mathe, titel="x", termin=zeit.heute()
            ).stoffe.create(thema=geo),
            kind_a,
        )
        == []
    )


def test_eltern_frage_in_generatorthema_zaehlt_im_plan_mit(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    t = thema(mathe, "mathe_6_brueche")
    eigene = Frage.objects.create(
        thema=t, typ="frage", frage="Was ist 1/2 + 1/2?", antwort="1", quelle="eltern"
    )
    p = _pruefung(kind_a, mathe, "mathe_6_brueche")
    ids = plan_selectors.stoff_fragen(p.stoffe.get(), kind_a)
    assert eigene.pk in ids and len(ids) == einstellungen.wert("lernen.mathe_pruefung_aufgaben") + 1


def test_probe_pruefung_mit_generierten_aufgaben(kind_a, mathe, uhr):
    stufe(kind_a, mathe, 6)
    p = _pruefung(kind_a, mathe, "mathe_6_brueche", "mathe_6_dezimal")
    probe = plan_services.probe_starten(p, jetzt=uhr.jetzt, zufall=random.Random(27))
    assert len(probe.fragen) == einstellungen.wert("lernen.pruefung_probe_fragen")
    assert all(Frage.objects.get(pk=i).generiert for i in probe.fragen)
    n = 0
    while (a := plan_services.probe_aufgabe(probe)) is not None:
        assert a.generiert
        plan_services.probe_antworten(probe, a.loesung if n % 3 else "-1", jetzt=uhr.jetzt)
        probe.refresh_from_db()
        n += 1
    assert probe.ende is not None and n == len(probe.fragen)
    ergebnis = {e.thema.schluessel: e for e in plan_services.probe_ergebnis(probe)}
    assert set(ergebnis) <= {"mathe_6_brueche", "mathe_6_dezimal"} and ergebnis


def test_laufende_pruefung_schuetzt_ihre_aufgaben_vor_dem_aufraeumen(kind_a, mathe):
    stufe(kind_a, mathe, 6)
    p = _pruefung(kind_a, mathe, "mathe_6_brueche")
    ids = plan_selectors.stoff_fragen(p.stoffe.get(), kind_a)
    _alt_machen(*Frage.objects.filter(pk__in=ids), tage=500)
    mathe_aufgaben.aufraeumen(zeit.jetzt())
    assert Frage.objects.filter(pk__in=ids).count() == len(ids)
    Pruefung.objects.filter(pk=p.pk).update(status=PruefungStatus.ABGESCHLOSSEN)
    mathe_aufgaben.aufraeumen(zeit.jetzt())
    assert not Frage.objects.filter(pk__in=ids).exists()


def test_themen_zur_auswahl_im_plan_enthalten_mathe(kind_a, mathe):
    stufe(kind_a, mathe, 8)
    namen = {t.schluessel for t in plan_selectors.themen_zur_auswahl(kind_a, mathe)}
    assert "mathe_8_terme" in namen and "mathe_3_plusminus" in namen


# --- Vokabeln unverändert -------------------------------------------------------------------------


def test_vokabel_ueben_ist_vom_generator_unberuehrt(kind_a, fach, mathe):
    s = services.sitzung_starten(kind_a, fach)
    rng = random.Random(28)
    a = services.frage_stellen(s, zufall=rng)
    assert not a.generiert and a.frage.typ == "vokabel"
    assert services.antworten(s, a.loesung).ergebnis == Ergebnis.RICHTIG
    assert not Frage.objects.filter(generiert=True).exists()


def test_thema_ohne_generator_im_mathe_fach_nutzt_gespeicherte_fragen(kind_a, mathe):
    stufe(kind_a, mathe, 3)
    geo = Thema.objects.get(fach=mathe, klassenstufe=3, name="Geometrische Formen")
    Frage.objects.create(
        thema=geo, typ="frage", frage="Ecken eines Dreiecks?", antwort="3", quelle="eltern"
    )
    s = start(kind_a, mathe, thema=geo)
    a = services.frage_stellen(s, zufall=random.Random(29))
    assert not a.generiert and a.loesung == "3"
    assert services.antworten(s, "3").ergebnis == Ergebnis.RICHTIG


# --- Schwierigkeit (rein) -------------------------------------------------------------------------


def test_schwierigkeit_start_und_bereiche():
    assert [
        schwierigkeit.start_stufe("grund", i) for i in ("aufwaermen", "normal", "herausforderung")
    ] == [1, 2, 3]
    assert [
        schwierigkeit.start_stufe("erweitert", i)
        for i in ("aufwaermen", "normal", "herausforderung")
    ] == [2, 3, 4]
    assert schwierigkeit.bereich("grund", "aufwaermen") == (1, 2)
    assert schwierigkeit.bereich("grund", "normal") == (1, 3)
    assert schwierigkeit.bereich("erweitert", "herausforderung") == (3, 5)
    assert schwierigkeit.quote([]) is None and schwierigkeit.quote([(1, True), (1, False)]) == 0.5


def test_schwierigkeit_steigt_nur_nach_genug_richtigen_und_nie_ueber_den_bereich():
    f = schwierigkeit.schwierigkeit
    assert f("grund", "normal", [(2, True)] * 3) == 2  # zu wenige Antworten
    assert f("grund", "normal", [(2, True)] * 4) == 3
    assert f("grund", "normal", [(3, True)] * 20) == 3  # Obergrenze Normal
    assert f("grund", "herausforderung", [(4, True)] * 20) == 4  # Grundniveau hört bei 4 auf
    assert f("erweitert", "herausforderung", [(5, True)] * 20) == 5
    assert f("grund", "normal", [(2, False)] * 4) == 1
    assert f("grund", "normal", [(2, True)] * 3 + [(2, False)]) == 2  # 75 % im Zielbereich
    assert f("grund", "aufwaermen", [(1, False)] * 8) == 1
    assert f("grund", "normal", [(2, True)] * 4, frust=True) == 2  # 3 minus 1
    assert f("grund", "normal", []) == 2 and f("grund", "normal", [], frust=True) == 1


def test_schwierigkeit_betrachtet_nur_die_letzte_stufe():
    f = schwierigkeit.schwierigkeit
    verlauf = [(2, False)] * 6 + [(3, True)] * 2
    assert f("erweitert", "normal", verlauf) == 3  # auf Stufe 3 erst zwei Antworten
    verlauf = [(2, False)] * 6 + [(3, True)] * 4
    assert f("erweitert", "normal", verlauf) == 4


def test_aufgabentext_folgt_der_sprache():
    from django.utils import translation

    with translation.override("en"):
        englisch = registry.erzeugen("geld", 3, 1).text
        schritt = registry.erzeugen("dezimal_runden", 1, 1).text
    assert "costs" in englisch and "Wie viel" not in englisch
    assert schritt.startswith("Round ") and "units" in schritt
    with translation.override("de"):
        assert registry.erzeugen("geld", 3, 1).text.startswith("Ein Heft kostet")


def test_einstellungs_editor_zeigt_und_speichert_mathe_einstellungen(eltern_client, db):
    antwort = eltern_client.get(reverse("oberflaeche:einstellungen"))
    html = antwort.content.decode()
    assert antwort.status_code == 200
    assert "Mathe: Aufgaben je Runde" in html and "Mathe: abgeschaltete Rechenarten" in html
    assert "bruch_addsub" in html and "Mathe: Obergrenze für Zahlen" in html


def test_tutor_haelt_erzeugte_antworten_nicht_fuer_geheime_loesungen(kind_a, mathe):
    from apps.lernen import tutor_selectors
    from apps.lernen.models import TutorGespraech

    t = thema(mathe, "mathe_3_einmaleins")
    mathe_aufgaben.speichern(registry.erzeugen("einmaleins", 1, 5), t)
    g = TutorGespraech.objects.create(
        kind=kind_a, thema=t, beginn=zeit.jetzt(), letzte_aktivitaet=zeit.jetzt()
    )
    assert tutor_selectors.bekannte_antworten(g) == []  # kurze Zahlen wären Fehlalarme
    # steht die Aufgabe im Text des Kindes, bleibt ihre Lösung geschützt
    aufgabe = Frage.objects.get(generiert=True)
    assert aufgabe.antwort in tutor_selectors.bekannte_antworten(g, [aufgabe.frage])
