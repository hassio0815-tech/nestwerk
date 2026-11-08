"""Wechseltext der Startseite: Textvorrat, Filter, Anonymität, eigene Sprüche, Offene Aufgaben."""

import json
import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import translation

from apps.aufgaben import wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.kern import einstellungen, zeit
from apps.lernen.models import Lerntag
from apps.oberflaeche import sprueche, wechseltext

BERLIN = ZoneInfo("Europe/Berlin")
MINDESTMENGEN = {"spruch": 100, "weisheit": 80, "fakt": 120, "gruss": 18}


def zu(jahr, monat, tag, stunde):
    return datetime(jahr, monat, tag, stunde, 0, tzinfo=BERLIN)


# --- Datenmodul ------------------------------------------------------------------------------


@pytest.mark.parametrize("art,mindestens", MINDESTMENGEN.items())
def test_mindestmengen_je_art(art, mindestens):
    assert sum(1 for e in sprueche.EINTRAEGE if e["art"] == art) >= mindestens


def test_jeder_eintrag_hat_de_en_und_gueltige_tags():
    for e in sprueche.EINTRAEGE:
        assert e["art"] in sprueche.ARTEN
        assert e["tageszeit"] in sprueche.TAGESZEITEN
        assert e["jahreszeit"] in sprueche.JAHRESZEITEN
        assert e["wochentage"] is None or all(0 <= w <= 6 for w in e["wochentage"])
        for lang in ("de", "en"):
            text = e[lang]
            assert text.strip() == text and text, e
            assert len(text) <= sprueche.MAX_LAENGE, text


def test_keine_doppelten_texte_und_hoechstens_ein_emoji():
    for lang in ("de", "en"):
        texte = [e[lang] for e in sprueche.EINTRAEGE]
        assert len(texte) == len(set(texte))
        for t in texte:
            assert len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", t)) <= 1, t


def test_englisch_ist_nicht_einfach_deutsch():
    gleich = [e["de"] for e in sprueche.EINTRAEGE if e["de"] == e["en"]]
    assert gleich == []


# --- Filter ----------------------------------------------------------------------------------


def test_morgens_keine_gute_nacht_und_abends_kein_guten_morgen():
    morgens = [e["de"] for e in wechseltext.passende_eintraege(zu(2026, 11, 9, 8), "gruss")]
    assert morgens and not any("Nacht" in t or "Abend" in t for t in morgens)
    abends = [e["de"] for e in wechseltext.passende_eintraege(zu(2026, 11, 9, 20), "gruss")]
    assert abends and not any("Morgen" in t or "Mahlzeit" in t for t in abends)
    nachts = [e["de"] for e in wechseltext.passende_eintraege(zu(2026, 11, 9, 23), "gruss")]
    assert any("Gute Nacht" in t for t in nachts)


def test_wochentage_und_jahreszeiten_filtern():
    montag = zu(2026, 11, 9, 12)  # Montag
    sonntag = zu(2026, 11, 8, 12)
    assert "Montag ist nur ein Dienstag, der sich zu früh angemeldet hat." in [
        e["de"] for e in wechseltext.passende_eintraege(montag)
    ]
    assert "Montag ist nur ein Dienstag, der sich zu früh angemeldet hat." not in [
        e["de"] for e in wechseltext.passende_eintraege(sonntag)
    ]
    winter = [e["de"] for e in wechseltext.passende_eintraege(zu(2026, 1, 15, 12))]
    sommer = [e["de"] for e in wechseltext.passende_eintraege(zu(2026, 7, 15, 12))]
    assert any("Winter" in t for t in winter) and not any("Sommerhitze" in t for t in winter)
    assert any("Sommerhitze" in t for t in sommer)


def test_tageszeit_und_jahreszeit_grenzen():
    assert [sprueche.tageszeit(h) for h in (4, 5, 10, 11, 13, 14, 17, 18, 21, 22, 0)] == [
        "nacht", "morgen", "morgen", "mittag", "mittag", "nachmittag", "nachmittag",
        "abend", "abend", "nacht", "nacht",
    ]  # fmt: skip
    assert [sprueche.jahreszeit(m) for m in (12, 3, 6, 9)] == [
        "winter",
        "fruehling",
        "sommer",
        "herbst",
    ]


# --- Mischung ----------------------------------------------------------------------------------


def test_liste_hat_dreissig_texte_und_beginnt_mit_dem_gruss(db):
    texte = wechseltext.wechseltexte(zu(2026, 11, 9, 8), zufall=random.Random(1), lang="de")
    assert len(texte) == wechseltext.ANZAHL
    assert texte[0] == "Guten Morgen!"
    assert len(set(texte)) == len(texte)


def test_sprache_folgt_der_aktiven_sprache(db):
    with translation.override("en"):
        texte = wechseltext.wechseltexte(zu(2026, 11, 9, 8), zufall=random.Random(2))
    assert texte[0] == "Good morning!"
    assert not any(t.startswith("Wusstest du") for t in texte)
    assert any(t.startswith("Did you know?") for t in texte) or len(texte) > 5


def test_eigene_sprueche_erscheinen_sprachunabhaengig(db):
    einstellungen.setzen("oberflaeche.eigene_sprueche", ["Wir sind das beste Nest!", "  ", "Hopp!"])
    assert wechseltext.eigene_sprueche() == ["Wir sind das beste Nest!", "Hopp!"]
    for lang in ("de", "en"):
        texte = wechseltext.wechseltexte(zu(2026, 11, 9, 8), zufall=random.Random(3), lang=lang)
        assert "Wir sind das beste Nest!" in texte and "Hopp!" in texte


def test_ohne_eigene_sprueche_wert_kein_absturz(db):
    from apps.kern.models import Einstellung

    Einstellung.objects.filter(schluessel="oberflaeche.eigene_sprueche").delete()
    assert wechseltext.eigene_sprueche() == []


# --- Familien-Infos: anonym ------------------------------------------------------------------


FIX = zu(2026, 11, 10, 16)  # Dienstagnachmittag


@pytest.fixture
def tagesdaten(db, mama, anna, ben):
    """Lernminuten, eine Erledigung, freie Aufgabe und eine feste Aufgabe für jeden Tag (am FIX)."""
    jetzt = FIX
    Lerntag.objects.create(kind=anna, datum=zeit.heute(jetzt), sekunden=600, ziel_minuten=15)
    Lerntag.objects.create(kind=ben, datum=zeit.heute(jetzt), sekunden=180, ziel_minuten=15)
    erledigt = Aufgabe.objects.create(
        titel="Tisch decken", punkte=10, erstellt_von=mama, wiederholungsart="einmalig"
    )
    AufgabenInstanz.objects.create(
        aufgabe=erledigt, kind=anna, status=InstanzStatus.BESTAETIGT, bestaetigt_am=jetzt,
        titel_snapshot="Tisch decken", punkte_snapshot=10, freigabeart_snapshot="eltern",
    )  # fmt: skip
    frei = Aufgabe.objects.create(
        titel="Keller fegen", punkte=10, erstellt_von=mama, wiederholungsart="einmalig"
    )
    AufgabenInstanz.objects.create(
        aufgabe=frei, status=InstanzStatus.OFFEN, titel_snapshot="Keller fegen",
        punkte_snapshot=10, freigabeart_snapshot="eltern",
    )  # fmt: skip
    Aufgabe.objects.create(
        titel="Restmüll rausstellen", punkte=10, erstellt_von=mama,
        wiederholungsart=wiederholung.WOECHENTLICH, wochentage=127,
        start_datum=zeit.heute(jetzt) - timedelta(days=30),
    )  # fmt: skip
    Aufgabe.objects.create(  # einem Kind zugeteilt: darf die Startseite nicht verraten
        titel="Zimmer saugen", punkte=10, erstellt_von=mama, zugewiesen_an=ben,
        wiederholungsart=wiederholung.WOECHENTLICH, wochentage=127,
        start_datum=zeit.heute(jetzt) - timedelta(days=30),
    )  # fmt: skip


def test_infos_enthalten_zahlen_aber_keine_namen(tagesdaten, mama, anna, ben):
    with translation.override("de"):
        infos = wechseltext.familien_infos(FIX, "de")
    assert {"lernen", "erledigt", "offen", "morgen", "wochenende"} <= set(infos)
    gesamt = " ".join(t for texte in infos.values() for t in texte)
    for name in ("Anna", "Ben", "Mama", mama.anzeigename, anna.anzeigename, ben.anzeigename):
        assert name not in gesamt
    assert any("Restmüll rausstellen" in t for t in infos["morgen"])
    assert not any("Zimmer saugen" in t for t in infos["morgen"])  # zugeteilt = nicht frei
    assert all("Tage" in t or "Tag" in t or "Wochenende" in t for t in infos["wochenende"])


def test_lernminuten_summe_ist_anonym(tagesdaten):
    from apps.lernen import selectors

    assert selectors.lernminuten_heute(zeit.heute(FIX)) == 13  # 600 s + 180 s = 13 Minuten


def test_wochenende_zaehlt_tage(db):
    lokal = zu(2026, 11, 9, 10)  # Montag -> Samstag in 5 Tagen
    texte = wechseltext._info_wochenende(lokal, "de")
    assert all("5 Tage" in t for t in texte)
    assert wechseltext._info_wochenende(zu(2026, 11, 13, 10), "de")[0].startswith("Nur noch einmal")
    assert "weekend" in wechseltext._info_wochenende(zu(2026, 11, 14, 10), "en")[0]


def test_fehler_in_einer_info_laesst_nur_diese_weg(db, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(wechseltext, "_info_lernen", kaputt)
    monkeypatch.setattr(
        wechseltext, "INFOS", (("lernen", kaputt), ("wochenende", wechseltext._info_wochenende))
    )
    infos = wechseltext.familien_infos(zu(2026, 11, 10, 16), "de")
    assert list(infos) == ["wochenende"]


def test_null_minuten_werden_nicht_gezeigt_morgens(db):
    assert wechseltext._info_lernen(zu(2026, 11, 10, 9), "de") == []
    assert wechseltext._info_lernen(zu(2026, 11, 10, 16), "de")  # aufmunternde Variante
    assert not any("0 Minuten" in t for t in wechseltext._info_lernen(zu(2026, 11, 10, 16), "de"))


# --- Startseite -------------------------------------------------------------------------------


def _wechseltexte_aus(html):
    treffer = re.search(
        r'<script id="wechseltexte-daten" type="application/json">(.*?)</script>', html, re.S
    )
    assert treffer, "json_script fehlt"
    return json.loads(treffer.group(1))


def test_startseite_liefert_wechseltexte_ohne_namen(client, tagesdaten):
    html = client.get("/").content.decode()
    assert 'data-wechseltext="wechseltexte-daten"' in html
    texte = _wechseltexte_aus(html)
    assert len(texte) >= 20
    assert not any(re.search(r"\b(Anna|Ben)\b", t) for t in texte)
    assert "<script>" not in html.split("wechseltexte-daten")[1].split("</script>")[0]


def test_startseite_kippt_nicht_wenn_wechseltext_scheitert(client, mama, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(wechseltext, "wechseltexte", kaputt)
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "data-wechseltext" not in antwort.content.decode()


def test_startseite_zeigt_nur_unzugeordnete_offene_aufgaben(client, mama, anna, ben):
    def offen(titel, zugewiesen_an=None, kind=None, status=InstanzStatus.OFFEN):
        aufgabe = Aufgabe.objects.create(
            titel=titel, punkte=10, erstellt_von=mama, wiederholungsart="einmalig",
            zugewiesen_an=zugewiesen_an,
        )  # fmt: skip
        return AufgabenInstanz.objects.create(
            aufgabe=aufgabe, kind=kind, status=status, titel_snapshot=titel,
            punkte_snapshot=10, freigabeart_snapshot="eltern",
        )  # fmt: skip

    offen("Frei für alle")
    offen("Nur für Ben", zugewiesen_an=ben)
    offen("Schon bei Anna", kind=anna)
    html = client.get("/").content.decode()
    assert "Frei für alle" in html
    assert "Nur für Ben" not in html
    assert "Schon bei Anna" not in html
    assert "· Ben" not in html


def test_eigene_sprueche_in_der_startseite(client, mama):
    einstellungen.setzen("oberflaeche.eigene_sprueche", ["Unser eigener Familienspruch"])
    texte = _wechseltexte_aus(client.get("/").content.decode())
    assert "Unser eigener Familienspruch" in texte


def test_alle_infos_liefern_in_beiden_sprachen_text(tagesdaten):
    for lang in ("de", "en"):
        infos = wechseltext.familien_infos(FIX, lang)
        assert {"lernen", "erledigt", "offen", "morgen", "wochenende"} <= set(infos)
        for texte in infos.values():
            assert all(t and "{" not in t for t in texte)
    assert any("13 Minuten" in t for t in wechseltext.familien_infos(FIX, "de")["lernen"])
    assert any("13 minutes" in t for t in wechseltext.familien_infos(FIX, "en")["lernen"])
