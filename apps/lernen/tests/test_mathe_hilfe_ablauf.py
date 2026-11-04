"""Mathe-Hilfe im Üben (Etappe 10b): Hilfeleiter, Erklärkarten, Fehlerhinweis und Seiten.

Lokal und ohne KI. Isolation der Kinder, Rollenschutz, EN-Ansicht und Wochenbild."""

import random

from django.urls import reverse
from django.utils import timezone

from apps.kern import einstellungen
from apps.lernen import selectors, services, woche_selectors
from apps.lernen.mathe import registry
from apps.lernen.models import Ergebnis, Lernsitzung, Versuch
from apps.lernen.tests.test_mathe_integration import (  # noqa: F401  (Fixtures und Helfer)
    alle_generatoren_aus_ausser,
    mathe,
    start,
    stufe,
)

HX = {"HTTP_HX_REQUEST": "true"}


def sitzung_mit(kind, mathe, generator, klasse=3, seed=1):
    stufe(kind, mathe, klasse)
    alle_generatoren_aus_ausser(generator)
    s = start(kind, mathe)
    a = services.frage_stellen(s, zufall=random.Random(seed))
    return s, a


# --- Die Leiter im Ablauf --------------------------------------------------------------------


def test_hilfe_steigt_je_wunsch_um_eine_stufe_bis_fuenf(kind_a, mathe):
    s, a = sitzung_mit(kind_a, mathe, "add_sub_100")
    for erwartet in (1, 2, 3, 4, 5, 5):
        assert services.hilfe(s) == ""
        s.refresh_from_db()
        assert s.aktuell_hilfe == erwartet and s.hilfestufe_max == erwartet
    assert [t.stufe for t in services.hilfe_stufen(s)] == [1, 2, 3, 4, 5]


def test_hilfe_zeigt_nie_die_loesung_im_ablauf(kind_a, mathe):
    s, a = sitzung_mit(kind_a, mathe, "einmaleins")
    for _i in range(5):
        services.hilfe(s)
    s.refresh_from_db()
    for t in services.hilfe_stufen(s):
        if t.stufe == 3:
            continue
        assert a.loesung not in "\n".join([*t.absaetze, *t.zeilen]).split()


def test_hilfestufe_wird_beim_antworten_gespeichert_und_kostet_nichts(kind_a, mathe):
    s, a = sitzung_mit(kind_a, mathe, "einmaleins", seed=3)
    services.hilfe(s)
    services.hilfe(s)
    services.hilfe(s)
    rueck = services.antworten(s, a.loesung)
    assert rueck.ergebnis == Ergebnis.RICHTIG  # kein Abzug, nicht bestraft
    v = Versuch.objects.get(sitzung=s)
    assert v.hilfestufe == 3
    s.refresh_from_db()
    assert s.hilfestufe_max == 3 and s.aktuell_hilfe == 0
    assert s.richtig == 1


def test_naechste_aufgabe_beginnt_wieder_ohne_hilfe(kind_a, mathe):
    s, _a = sitzung_mit(kind_a, mathe, "einmaleins", seed=4)
    services.hilfe(s)
    b = services.frage_stellen(s)
    services.antworten(s, b.loesung)
    c = services.frage_stellen(s, zufall=random.Random(5))
    s.refresh_from_db()
    assert c.frage != b.frage and s.aktuell_hilfe == 0 and services.hilfe_stufen(s) == []


def test_loesung_zeigen_merkt_die_hoechste_stufe(kind_a, mathe):
    s, a = sitzung_mit(kind_a, mathe, "einmaleins", seed=6)
    for _i in range(4):
        services.hilfe(s)
    services.loesung_zeigen(s)
    assert Versuch.objects.get(sitzung=s).hilfestufe == 4
    s2, _b = sitzung_mit(kind_a, mathe, "einmaleins", seed=7)
    services.loesung_zeigen(s2)
    assert Versuch.objects.get(sitzung=s2).hilfestufe == 2  # wie bisher


def test_erlaubte_hoechste_stufe_ist_eine_einstellung(kind_a, mathe):
    einstellungen.setzen("lernen.mathe_hilfe_max_stufe", 3, akteur=None)
    s, _a = sitzung_mit(kind_a, mathe, "einmaleins")
    for _i in range(6):
        services.hilfe(s)
    s.refresh_from_db()
    assert s.aktuell_hilfe == 3 and len(services.hilfe_stufen(s)) == 3
    assert services.mathe_hilfe_stufe_max() == 3


def test_vokabeln_behalten_den_anfangsbuchstaben_hinweis(kind_a, fach):
    s = services.sitzung_starten(kind_a, fach, ziel_fragen=3)
    a = services.frage_stellen(s, zufall=random.Random(1))
    hinweis = services.hilfe(s)
    assert hinweis.replace(" ", "")[0] == a.loesung[0] and "_" in hinweis
    assert services.hilfe_stufen(s) == []
    assert services.hilfe_kontext(s, a) == {"hilfe_weiter": True, "hilfe_text": "Tipp"}


def test_kontext_ohne_aufgabe_ist_leer(kind_a, mathe):
    s, _a = sitzung_mit(kind_a, mathe, "einmaleins")
    assert services.hilfe_kontext(s, None) == {}
    s.aktuell_frage = None
    s.save()
    assert services.hilfe_stufen(s) == []


# --- Fehlerhinweis im Ablauf -----------------------------------------------------------------


def _naechste_mit_uebertrag(s, rng):
    """Die nächste Aufgabe mit Übertrag und die Antwort "Übertrag vergessen"; andere Aufgaben
    werden richtig beantwortet."""
    for _i in range(200):
        a = services.frage_stellen(s, zufall=rng)
        p = a.frage.gen_daten["parameter"]
        if a.frage.gen_daten["typ"] == "add_mit_uebertrag" and p["a"] % 10 + p["b"] % 10 >= 10:
            ohne = (p["a"] % 10 + p["b"] % 10) % 10 + (p["a"] // 10 + p["b"] // 10) * 10
            if ohne != p["a"] + p["b"]:
                return a, str(ohne)
        services.antworten(s, a.loesung)
    raise AssertionError("keine Aufgabe mit Übertrag gefunden")


def _addition(kind, mathe):
    stufe(kind, mathe, 3)
    alle_generatoren_aus_ausser("add_sub_100")
    s = start(kind, mathe)
    a, falsch = _naechste_mit_uebertrag(s, random.Random(0))
    return s, a, falsch


def test_erkannter_fehler_gibt_hinweis_und_zweiten_versuch(kind_a, mathe):
    s, a, falsch = _addition(kind_a, mathe)
    rueck = services.antworten(s, falsch)
    assert rueck.ergebnis == Ergebnis.FAST and rueck.nochmal
    assert "Übertrag" in rueck.text and rueck.hinweis == rueck.text
    assert a.loesung not in rueck.text.split()
    v = Versuch.objects.filter(sitzung=s).latest("id")
    assert v.fehlertyp == "uebertrag_vergessen" and v.ergebnis == Ergebnis.FAST
    assert services.frage_stellen(s).frage == a.frage  # dieselbe Aufgabe noch einmal
    s.refresh_from_db()
    assert s.versuche == s.richtig  # noch nicht verbucht
    ok = services.antworten(s, a.loesung)
    assert ok.ergebnis == Ergebnis.RICHTIG


def test_zweiter_fehler_zeigt_die_loesung_mit_hinweis(kind_a, mathe):
    s, a, falsch = _addition(kind_a, mathe)
    services.antworten(s, falsch)
    rueck = services.antworten(s, falsch)
    assert rueck.ergebnis == Ergebnis.NOCH_NICHT and not rueck.nochmal
    assert rueck.loesung == a.loesung and "Übertrag" in rueck.hinweis
    assert Versuch.objects.filter(sitzung=s).latest("id").fehlertyp == "uebertrag_vergessen"


def test_unerkannter_fehler_zeigt_gleich_die_loesung_mit_neutralem_hinweis(kind_a, mathe):
    s, a = sitzung_mit(kind_a, mathe, "add_sub_100", seed=9)
    rueck = services.antworten(s, "99999")
    assert rueck.ergebnis == Ergebnis.NOCH_NICHT and rueck.loesung == a.loesung
    assert "Schritt für Schritt" in rueck.hinweis
    assert Versuch.objects.get(sitzung=s).fehlertyp == ""


def test_hinweis_nennt_nie_die_loesung_im_ablauf(kind_a, mathe):
    s, a, falsch = _addition(kind_a, mathe)
    rueck = services.antworten(s, falsch)
    assert a.loesung not in rueck.hinweis


# --- Seiten ----------------------------------------------------------------------------------


def test_seite_zeigt_hilfestufen_karte_und_knopf(kind_a, mathe, kind_client):
    s, a = sitzung_mit(kind_a, mathe, "add_sub_100")
    url = reverse("lernen:sitzung", args=[s.pk])
    html = kind_client.get(url).content.decode()
    assert "data-lernen-karte" in html and "Rechen-Tipp:" in html and "Plus und Minus" in html
    assert "Hilfe" in html and "data-lernen-hilfe-stufe" not in html
    html = kind_client.post(reverse("lernen:hilfe", args=[s.pk]), **HX).content.decode()
    assert 'data-lernen-hilfe-stufe="1"' in html and "Stufe 1: Nachfragen" in html
    assert "Mehr Hilfe" in html and "Gesucht ist" in html
    for _i in range(4):
        html = kind_client.post(reverse("lernen:hilfe", args=[s.pk]), **HX).content.decode()
    assert 'data-lernen-hilfe-stufe="5"' in html and "Stufe 5: So gehst du vor" in html
    assert "___" in html and "Zu den Rechen-Tipps" in html
    assert reverse("lernen:hilfe", args=[s.pk]) not in html  # Stufe 5 erreicht: kein Knopf mehr
    assert (
        f">{a.loesung}<"
        not in html.split('data-lernen-hilfe-stufe="4"')[1].split('data-lernen-hilfe-stufe="5"')[0]
    )


def test_hilfe_ist_auf_englisch_uebersetzt(kind_a, mathe, kind_client):
    s, _a = sitzung_mit(kind_a, mathe, "einmaleins")
    kind_client.post(reverse("lernen:hilfe", args=[s.pk]), HTTP_ACCEPT_LANGUAGE="en", **HX)
    html = kind_client.post(
        reverse("lernen:hilfe", args=[s.pk]), HTTP_ACCEPT_LANGUAGE="en", **HX
    ).content.decode()
    assert "Step 2: Nudge" in html and "Step 1: Questions" in html
    assert "Nachfragen" not in html and "Denkanstoß" not in html


def test_fremde_sitzung_ist_tabu_fuer_hilfe_und_erklaerung(kind_a, kind_b, mathe, kind_client):
    stufe(kind_b, mathe, 3)
    s = start(kind_b, mathe)
    services.frage_stellen(s, zufall=random.Random(2))
    for name in ("lernen:hilfe", "lernen:erklaerung", "lernen:antwort", "lernen:loesung"):
        assert kind_client.post(reverse(name, args=[s.pk])).status_code == 404
    s.refresh_from_db()
    assert s.aktuell_hilfe == 0


def test_eltern_duerfen_nicht_hilfe_holen(kind_a, mathe, eltern_client):
    s, _a = sitzung_mit(kind_a, mathe, "einmaleins")
    assert eltern_client.post(reverse("lernen:hilfe", args=[s.pk])).status_code == 403
    assert eltern_client.post(reverse("lernen:erklaerung", args=[s.pk])).status_code == 403
    s.refresh_from_db()
    assert s.aktuell_hilfe == 0


def test_fehlerhinweis_steht_auf_der_seite(kind_a, mathe, kind_client):
    s, a, falsch = _addition(kind_a, mathe)
    html = kind_client.post(
        reverse("lernen:antwort", args=[s.pk]), {"eingabe": falsch}, **HX
    ).content.decode()
    assert "Übertrag" in html and 'data-lernen-zustand="frage"' in html
    html = kind_client.post(
        reverse("lernen:antwort", args=[s.pk]), {"eingabe": falsch}, **HX
    ).content.decode()
    assert "data-lernen-fehlerhinweis" in html and "Die Lösung ist:" in html
    assert "So heißt es" not in html  # das ist die Vokabel-Formulierung
    assert "autofocus" in html  # "Weiter" hat den Fokus: Enter geht zur nächsten Aufgabe


def test_eingabefeld_hat_passende_handy_tastatur(kind_a, mathe, kind_client):
    s, a = sitzung_mit(kind_a, mathe, "add_sub_100")
    html = kind_client.get(reverse("lernen:sitzung", args=[s.pk])).content.decode()
    assert 'inputmode="decimal"' in html and 'enterkeyhint="send"' in html
    s2, a2 = sitzung_mit(kind_a, mathe, "negative_zahlen", klasse=8)
    assert a2.eingabemodus == ("decimal" if a2.frage.antwort.isdigit() else "text")


def test_rechnung_bricht_nicht_mitten_in_der_rechnung():
    from apps.lernen.templatetags.lernen_text import rechnung

    assert rechnung("2x + 3 = 11: Probe: 2 · 4 + 3 = 11.") == (
        "2x\u00a0+ 3\u00a0= 11: Probe: 2\u00a0·\u00a04\u00a0+ 3\u00a0= 11."
    )
    assert rechnung("47 + 38: Einer") == "47\u00a0+ 38: Einer"  # Satz-Doppelpunkt bleibt


# --- Rechen-Tipps ----------------------------------------------------------------------------


def test_kind_sieht_alle_rechen_tipps_in_seiner_sprachstufe(kind_a, mathe, kind_client):
    stufe(kind_a, mathe, 3)
    html = kind_client.get(reverse("lernen:tipps")).content.decode()
    assert html.count("data-lernen-tipp=") == 28
    assert "Rechne von rechts nach links: erst die Einer" in html  # Sprachstufe 1
    assert "Klasse 3 und 4" in html and "Ab Klasse 8" in html
    start_html = kind_client.get(reverse("lernen:start")).content.decode()
    assert reverse("lernen:tipps") in start_html and "data-lernen-tipps" in start_html


def test_rechen_tipps_folgen_der_klassenstufe_und_sprache(kind_a, mathe, kind_client):
    stufe(kind_a, mathe, 8)
    html = kind_client.get(reverse("lernen:tipps")).content.decode()
    assert "Addiere und subtrahiere stellenweise von rechts" in html  # Sprachstufe 3
    en = kind_client.get(reverse("lernen:tipps"), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "Calculation tips" in en
    assert "Rechen-Tipps" not in en and "Merksatz" not in en


def test_eltern_sehen_tipps_lesend_in_waehlbarer_stufe(kind_a, mathe, eltern_client):
    html = eltern_client.get(reverse("lernen:eltern_tipps")).content.decode()
    assert html.count("data-lernen-tipp=") == 28
    j = eltern_client.get(reverse("lernen:eltern_tipps") + "?stufe=1").content.decode()
    assert "Rechne von rechts nach links" in j
    kaputt = eltern_client.get(reverse("lernen:eltern_tipps") + "?stufe=x").content.decode()
    assert "Addiere und subtrahiere" not in kaputt or "data-lernen-tipps-stufen" in kaputt
    assert "data-lernen-tipps-stufen" in html
    eltern_start = eltern_client.get(reverse("lernen:eltern")).content.decode()
    assert reverse("lernen:eltern_tipps") in eltern_start
    assert eltern_client.post(reverse("lernen:eltern_tipps")).status_code in (200, 405)


def test_tipps_sind_rollengeschuetzt(kind_client, eltern_client, db):
    from django.test import Client

    assert kind_client.get(reverse("lernen:eltern_tipps")).status_code == 403
    assert eltern_client.get(reverse("lernen:tipps")).status_code == 403
    assert Client().get(reverse("lernen:tipps")).status_code in (302, 401)
    assert Client().get(reverse("lernen:eltern_tipps")).status_code in (302, 401)


def test_tipps_enthalten_keine_aufgabenloesung_einer_offenen_aufgabe(kind_a, mathe, kind_client):
    """Die Seite zeigt feste Beispiele; sie kennt keine offene Aufgabe."""
    s, a = sitzung_mit(kind_a, mathe, "einmaleins")
    html = kind_client.get(reverse("lernen:tipps")).content.decode()
    assert a.text not in html


# --- Wochenbild für die Eltern ---------------------------------------------------------------


def test_wochenbild_nennt_haeufige_fehlerarten(kind_a, mathe, eltern_client):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("add_sub_100")
    for seed in (0, 1):  # je Sitzung ein Fehler (mehr würde die Frust-Erkennung auslösen)
        s = start(kind_a, mathe)
        a, falsch = _naechste_mit_uebertrag(s, random.Random(seed))
        services.antworten(s, falsch)  # erster Fehler: Hinweis und zweiter Versuch
        services.antworten(s, falsch)  # zweiter Fehler: Lösung, Aufgabe ist erledigt
        services.sitzung_beenden(s)
    bild = woche_selectors.wochenbild(kind_a, timezone.localdate())
    typen = {f.typ: f.anzahl for f in bild.fehlerarten}
    assert typen.get("uebertrag_vergessen", 0) >= 4
    assert all(f.hinweis for f in bild.fehlerarten) and len(bild.fehlerarten) <= 3
    html = eltern_client.get(reverse("lernen:eltern_woche")).content.decode()
    assert "Häufige Stolpersteine" in html and "data-lernen-fehlerarten" in html


def test_wochenbild_ohne_fehler_zeigt_keine_fehlerarten(kind_a, mathe, eltern_client):
    s, a = sitzung_mit(kind_a, mathe, "einmaleins")
    services.antworten(s, a.loesung)
    bild = woche_selectors.wochenbild(kind_a, timezone.localdate())
    assert bild.fehlerarten == []
    assert (
        "Häufige Stolpersteine"
        not in eltern_client.get(reverse("lernen:eltern_woche")).content.decode()
    )


def test_kind_b_sieht_nichts_von_den_fehlern_des_kindes_a(kind_a, kind_b, mathe):
    s, a, falsch = _addition(kind_a, mathe)
    services.antworten(s, falsch)
    services.antworten(s, falsch)
    assert woche_selectors.wochenbild(kind_b, timezone.localdate()).fehlerarten == []


def test_einstellungen_haben_startwerte_fuer_die_hilfe(db):
    assert einstellungen.wert("lernen.mathe_hilfe_max_stufe") == 5
    assert einstellungen.wert("lernen.mathe_einkleidung_ki") is False
    assert einstellungen.wert("lernen.mathe_textaufgaben_prozent") == 0


def test_jede_rechenart_hat_eine_seite_mit_hilfe(kind_a, mathe, kind_client):
    """Rauchtest: Für jede Rechenart lässt sich Stufe 1 bis 5 auf der Seite ansehen."""
    for generator in registry.schluessel_alle():
        klasse = {3: 3, 6: 6, 8: 8}[registry.holen(generator).klassenstufe]
        s, _a = sitzung_mit(kind_a, mathe, generator, klasse=klasse, seed=11)
        for _i in range(5):
            html = kind_client.post(reverse("lernen:hilfe", args=[s.pk]), **HX).content.decode()
        assert 'data-lernen-hilfe-stufe="5"' in html, generator
        services.sitzung_beenden(s)
        Lernsitzung.objects.filter(pk=s.pk).update(ende=timezone.now())
        selectors  # noqa: B018


def test_gegeben_trennt_dezimalzahlen_mit_semikolon(kind_a, mathe):
    s, a = sitzung_mit(kind_a, mathe, "dezimal_rechnen", klasse=6)
    for _ in range(2):
        services.hilfe(s)
    s.refresh_from_db()
    erste = services.hilfe_stufen(s)[0]
    gegeben = next(x for x in erste.absaetze if x.startswith("Gegeben ist:"))
    assert ";" in gegeben and gegeben.endswith(".") and gegeben.count(",") == 2
