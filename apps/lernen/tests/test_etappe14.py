"""Etappe 14: Punkte-Lücken (W-9), Runde nach Zeit und Pause nach Zeit (W-10), Kalibrierung,
Fehlergrund und Strategie-Funktion (W-8.1/8.2/8.5)."""

import random
from datetime import timedelta

import pytest
from django.urls import reverse

from apps.kern import einstellungen, zeit
from apps.lernen import plan_services, selectors, services, strategie
from apps.lernen.models import (
    Ergebnis,
    Erwartung,
    Fehlergrund,
    Frage,
    Intensitaet,
    Lerntag,
    Strategie,
    Thema,
    Versuch,
    Vorhaben,
)
from apps.lernen.tests.test_mathe_integration import (  # noqa: F401  (Fixtures und Helfer)
    alle_generatoren_aus_ausser,
    mathe,
    start,
    stufe,
)
from apps.punkte import selectors as punkte
from apps.punkte.models import Buchung

HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def minuten_modus(db):
    """Die Startwerte der Migration: Runden zählen nach Minuten."""
    einstellungen.setzen("lernen.runde_ziel", "minuten", akteur=None)


def lang(fach, anzahl=40):
    t = Thema.objects.create(
        fach=fach, klassenstufe=5, name=f"Langes Thema {Thema.objects.count()}"
    )
    for i in range(anzahl):
        Frage.objects.create(thema=t, typ="frage", frage=f"Frage {i}", antwort=f"a{i}")
    return t


@pytest.fixture(autouse=True)
def viele_fragen(fach):
    """Genug Stoff, damit keine Runde mangels Fragen endet."""
    lang(fach, 60)


def starten(kind, fach, **extra):
    return services.sitzung_starten(kind, fach, **extra)


def antwort_schritt(s, uhr, richtig=True, sekunden=30, seed=1):
    a = services.frage_stellen(s, zufall=random.Random(seed), jetzt=uhr.jetzt)
    assert a is not None
    uhr.weiter(seconds=sekunden)
    return services.antworten(s, a.loesung if richtig else "völlig daneben", jetzt=uhr.jetzt)


def mit_antworten(s, uhr, anzahl, richtig=True):
    for i in range(anzahl):
        antwort_schritt(s, uhr, richtig=richtig, seed=i)


def probe_machen(kind, fach, uhr):
    t = lang(fach, 20)
    p = plan_services.pruefung_anlegen(
        kind, fach, "Test", zeit.heute() + timedelta(days=14), themen=[t]
    )
    probe = plan_services.probe_starten(p, jetzt=uhr.jetzt, zufall=random.Random(1))
    while probe.ende is None:
        plan_services.probe_antworten(probe, "egal", jetzt=uhr.jetzt)
        probe.refresh_from_db()
    return probe


def schluessel(kind, wo):
    return list(
        Buchung.objects.filter(kind=kind, idempotenz_schluessel__startswith=f"lernen:{wo}:")
    )


# --- W-9: Punkte-Lücken ------------------------------------------------------------------------


def test_startwerte_der_punkte():
    assert einstellungen.wert("lernen.lernpunkte_tageslimit") == 8
    assert einstellungen.wert("lernen.tagesziel_punkte") == 5
    assert einstellungen.wert("lernen.punkte_selbsttest") == 3
    assert einstellungen.wert("lernen.punkte_fehlerueberarbeitung") == 3
    assert einstellungen.wert("lernen.punkte_rueckschau") == 1


def test_selbsttest_gibt_drei_punkte_einmal_pro_tag(kind_a, fach, uhr):
    probe_machen(kind_a, fach, uhr)
    assert punkte.guthaben(kind_a) == 3
    assert len(schluessel(kind_a, "selbsttest")) == 1
    probe_machen(kind_a, fach, uhr)  # zweite Probe am selben Tag: nichts mehr
    assert punkte.guthaben(kind_a) == 3
    uhr.weiter(days=1)
    probe_machen(kind_a, fach, uhr)
    assert punkte.guthaben(kind_a) == 6


def test_selbsttest_beenden_ist_idempotent(kind_a, fach, uhr):
    probe = probe_machen(kind_a, fach, uhr)
    plan_services.probe_beenden(probe, jetzt=uhr.jetzt)
    assert punkte.guthaben(kind_a) == 3


def test_fehlerueberarbeitung_braucht_fuenf_antworten_und_das_vorhaben(kind_a, fach, uhr):
    kurz = starten(kind_a, fach, vorhaben=Vorhaben.STOLPERSTELLEN)
    mit_antworten(kurz, uhr, 4, richtig=False)
    services.sitzung_beenden(kurz, jetzt=uhr.jetzt)
    assert schluessel(kind_a, "fehlerueberarbeitung") == []
    anders = starten(kind_a, fach, vorhaben=Vorhaben.WIEDERHOLEN)
    mit_antworten(anders, uhr, 6)
    services.sitzung_beenden(anders, jetzt=uhr.jetzt)
    assert schluessel(kind_a, "fehlerueberarbeitung") == []
    voll = starten(kind_a, fach, vorhaben=Vorhaben.STOLPERSTELLEN)
    mit_antworten(voll, uhr, 5)
    services.sitzung_beenden(voll, jetzt=uhr.jetzt)
    assert len(schluessel(kind_a, "fehlerueberarbeitung")) == 1
    assert punkte.guthaben(kind_a) == 3
    nochmal = starten(kind_a, fach, vorhaben=Vorhaben.STOLPERSTELLEN)
    mit_antworten(nochmal, uhr, 5)
    services.sitzung_beenden(nochmal, jetzt=uhr.jetzt)
    assert punkte.guthaben(kind_a) == 3  # höchstens einmal am Tag


def test_rueckschau_gibt_einen_punkt_nur_wenn_ausgefuellt(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    mit_antworten(s, uhr, 2)
    services.rueckschau_speichern(s, "", "", "")
    assert punkte.guthaben(kind_a) == 0
    s2 = starten(kind_a, fach)
    mit_antworten(s2, uhr, 2)
    services.rueckschau_speichern(s2, "", "Laut sagen", "")
    assert punkte.guthaben(kind_a) == 1
    s3 = starten(kind_a, fach)
    mit_antworten(s3, uhr, 2)
    services.rueckschau_speichern(s3, "Rechnen", "Aufschreiben", "passend")
    assert punkte.guthaben(kind_a) == 1  # einmal am Tag
    uhr.weiter(days=1)
    s4 = starten(kind_a, fach)
    mit_antworten(s4, uhr, 2)
    services.rueckschau_speichern(s4, "x", "", "")
    assert punkte.guthaben(kind_a) == 2


def test_tageslimit_haelt_ueber_alle_arten(kind_a, fach, uhr):
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    s = starten(kind_a, fach)
    for _ in range(14):
        uhr.weiter(seconds=100)
        services.frage_stellen(s, jetzt=uhr.jetzt)
    assert punkte.guthaben(kind_a) == 5  # Tagesziel
    probe_machen(kind_a, fach, uhr)
    assert punkte.guthaben(kind_a) == 8  # + Selbsttest 3 = Limit
    voll = starten(kind_a, fach, vorhaben=Vorhaben.STOLPERSTELLEN)
    mit_antworten(voll, uhr, 5)
    services.rueckschau_speichern(voll, "schwer", "geholfen", "passend")
    assert punkte.guthaben(kind_a) == 8
    tag = Lerntag.objects.get(kind=kind_a, datum=zeit.heute())
    assert tag.punkte == 8
    summe = sum(Buchung.objects.filter(kind=kind_a).values_list("guthaben_delta", flat=True))
    assert summe == 8


def test_keine_punkte_pro_antwort(kind_a, fach, uhr):
    s = starten(kind_a, fach, intensitaet=Intensitaet.HERAUSFORDERUNG)
    mit_antworten(s, uhr, 11)
    assert punkte.guthaben(kind_a) == 0
    assert Buchung.objects.filter(kind=kind_a).count() == 0


def test_lernpunkte_aus_gilt_auch_fuer_die_neuen_arten(kind_a, fach, uhr):
    einstellungen.setzen("lernen.lernpunkte_aktiv", False, akteur=None)
    probe_machen(kind_a, fach, uhr)
    s = starten(kind_a, fach, vorhaben=Vorhaben.STOLPERSTELLEN)
    mit_antworten(s, uhr, 5)
    services.rueckschau_speichern(s, "a", "b", "passend")
    assert Buchung.objects.filter(kind=kind_a).count() == 0


# --- W-10: Runde nach Zeit, Pause nach Zeit ----------------------------------------------------


def test_runde_hat_ziel_in_minuten(kind_a, fach, minuten_modus):
    for stufe_, minuten in (
        (Intensitaet.AUFWAERMEN, 5),
        (Intensitaet.NORMAL, 10),
        (Intensitaet.HERAUSFORDERUNG, 15),
    ):
        assert starten(kind_a, fach, intensitaet=stufe_).ziel_minuten == minuten


def test_fragenmodus_bleibt_waehlbar(kind_a, fach):
    einstellungen.setzen("lernen.runde_ziel", "fragen", akteur=None)
    s = starten(kind_a, fach)
    assert (s.ziel_minuten, s.ziel_fragen) == (0, 10)


def test_runde_endet_nach_der_zeit_nicht_nach_fragen(kind_a, fach, uhr, minuten_modus):
    lang(fach, 30)
    s = starten(kind_a, fach, intensitaet=Intensitaet.AUFWAERMEN)
    assert s.ziel_fragen > 20  # Fragenzahl ist nur noch eine Obergrenze
    n = 0
    while True:
        a = services.frage_stellen(s, zufall=random.Random(n), jetzt=uhr.jetzt)
        if a is None:
            break
        uhr.weiter(seconds=30)
        services.antworten(s, a.loesung, jetzt=uhr.jetzt)
        n += 1
        assert n < 40
    assert n == 10  # 10 x 30 s = 5 Minuten
    s.refresh_from_db()
    assert s.dauer_sekunden == 300


def test_weiche_grenze_die_offene_frage_darf_fertig_werden(kind_a, fach, uhr, minuten_modus):
    lang(fach, 30)
    s = starten(kind_a, fach, intensitaet=Intensitaet.AUFWAERMEN)
    for i in range(9):
        antwort_schritt(s, uhr, seed=i)
    a = services.frage_stellen(s, zufall=random.Random(99), jetzt=uhr.jetzt)
    assert a is not None
    uhr.weiter(seconds=60)  # über das Ziel hinaus
    rueck = services.antworten(s, a.loesung, jetzt=uhr.jetzt)
    assert rueck.ergebnis == Ergebnis.RICHTIG
    assert services.frage_stellen(s, jetzt=uhr.jetzt) is None


def test_pause_nach_zeit_einmal_pro_runde(kind_a, fach, uhr, minuten_modus):
    lang(fach, 40)
    einstellungen.setzen("lernen.pause_nach_minuten", 2, akteur=None)
    s = starten(kind_a, fach, intensitaet=Intensitaet.HERAUSFORDERUNG)
    ergebnisse = [antwort_schritt(s, uhr, seed=i) for i in range(8)]
    # nach 4 x 30 s = 2 Minuten kommt der Vorschlag, danach nicht noch einmal
    assert [r.pause_vorschlag for r in ergebnisse] == [False, False, False, True] + [False] * 4
    assert ergebnisse[3].pause_grund == "zeit"
    s.refresh_from_db()
    assert s.pause_vorgeschlagen


def test_pause_nach_zeit_aus_bei_null(kind_a, fach, uhr, minuten_modus):
    lang(fach, 40)
    einstellungen.setzen("lernen.pause_nach_minuten", 0, akteur=None)
    s = starten(kind_a, fach, intensitaet=Intensitaet.HERAUSFORDERUNG)
    assert not any(antwort_schritt(s, uhr, seed=i).pause_vorschlag for i in range(8))


def test_pause_nach_zeit_ueberlebt_das_tageslimit(kind_a, fach, uhr, minuten_modus):
    """Pause und Punkte sind getrennt: die Pause ändert nie die Buchungen."""
    lang(fach, 40)
    einstellungen.setzen("lernen.pause_nach_minuten", 1, akteur=None)
    s = starten(kind_a, fach, intensitaet=Intensitaet.HERAUSFORDERUNG)
    for i in range(6):
        antwort_schritt(s, uhr, seed=i)
    assert punkte.guthaben(kind_a) == 0


def test_frust_pause_hat_den_grund_frust(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    grund = [antwort_schritt(s, uhr, richtig=False, seed=i) for i in range(4)]
    treffer = [r for r in grund if r.pause_vorschlag]
    assert treffer and treffer[0].pause_grund == "frust"


# --- W-8.2: Fehlergrund ------------------------------------------------------------------------


def klasse(kind, fach, k):
    services.leistungsstufe_setzen(kind, fach, klassenstufe=k)


def test_fehlergrund_frage_ab_klasse_6(kind_a, fach, uhr):
    klasse(kind_a, fach, 6)
    s = starten(kind_a, fach)
    falsch = antwort_schritt(s, uhr, richtig=False)
    assert falsch.fehlergrund_frage and falsch.versuch_id
    richtig = antwort_schritt(s, uhr, richtig=True, seed=2)
    assert not richtig.fehlergrund_frage


def test_kein_fehlergrund_unter_klasse_6_oder_ohne_klasse(kind_a, fach, uhr):
    s = starten(kind_a, fach)
    assert not antwort_schritt(s, uhr, richtig=False).fehlergrund_frage  # keine Klasse
    klasse(kind_a, fach, 5)
    s2 = starten(kind_a, fach)
    assert not antwort_schritt(s2, uhr, richtig=False, seed=3).fehlergrund_frage


def test_fehlergrund_speichern(kind_a, fach, uhr):
    klasse(kind_a, fach, 7)
    s = starten(kind_a, fach)
    rueck = antwort_schritt(s, uhr, richtig=False)
    services.fehlergrund_speichern(s, rueck.versuch_id, Fehlergrund.ZU_SCHNELL)
    assert Versuch.objects.get(pk=rueck.versuch_id).fehlergrund == "zu_schnell"
    services.fehlergrund_speichern(s, rueck.versuch_id, Fehlergrund.VERRECHNET)
    assert Versuch.objects.get(pk=rueck.versuch_id).fehlergrund == "verrechnet"


def test_fehlergrund_nur_fuer_noch_nicht_der_eigenen_sitzung(kind_a, kind_b, fach, uhr):
    klasse(kind_a, fach, 7)
    s = starten(kind_a, fach)
    ok = antwort_schritt(s, uhr, richtig=True)
    ok_id = Versuch.objects.filter(sitzung=s).latest("id").pk
    assert ok.ergebnis == Ergebnis.RICHTIG
    with pytest.raises(services.LernenFehler):
        services.fehlergrund_speichern(s, ok_id, Fehlergrund.NICHT_GEWUSST)
    falsch = antwort_schritt(s, uhr, richtig=False, seed=5)
    with pytest.raises(services.LernenFehler):
        services.fehlergrund_speichern(s, falsch.versuch_id, "quatsch")
    fremd = starten(kind_b, fach)
    with pytest.raises(services.LernenFehler):
        services.fehlergrund_speichern(fremd, falsch.versuch_id, Fehlergrund.NICHT_GEWUSST)


def test_sitzung_endet_auch_ohne_fehlergrund(kind_a, fach, uhr):
    klasse(kind_a, fach, 8)
    s = starten(kind_a, fach)
    antwort_schritt(s, uhr, richtig=False)
    services.sitzung_beenden(s, jetzt=uhr.jetzt)
    services.rueckschau_speichern(s, "", "", "")
    s.refresh_from_db()
    assert s.ende is not None and s.rueckschau_fertig
    assert Versuch.objects.get(sitzung=s).fehlergrund == ""


def test_fehlergrund_ansicht(kind_client, kind_a, fach):
    klasse(kind_a, fach, 6)
    s = starten(kind_a, fach)
    services.frage_stellen(s, zufall=random.Random(1))
    antwort = kind_client.post(reverse("lernen:antwort", args=[s.pk]), {"eingabe": "nix"}, **HX)
    html = antwort.content.decode()
    assert "data-lernen-fehlergrund" in html
    for wert in Fehlergrund.values:
        assert f'value="{wert}"' in html
    versuch = Versuch.objects.get(sitzung=s)
    url = reverse("lernen:fehlergrund", args=[s.pk])
    gespeichert = kind_client.post(url, {"versuch": versuch.pk, "grund": "nicht_gewusst"}, **HX)
    assert gespeichert.status_code == 200
    versuch.refresh_from_db()
    assert versuch.fehlergrund == "nicht_gewusst"
    # Ungültiges stürzt nicht ab und ändert nichts
    kind_client.post(url, {"versuch": versuch.pk, "grund": "quatsch"}, **HX)
    versuch.refresh_from_db()
    assert versuch.fehlergrund == "nicht_gewusst"


def test_fehlergrund_ansicht_fremde_sitzung_404(kind_client, kind_b, fach):
    s = starten(kind_b, fach)
    assert kind_client.post(reverse("lernen:fehlergrund", args=[s.pk]), {}).status_code == 404


def test_keine_fehlergrund_knoepfe_unter_klasse_6(kind_client, kind_a, fach):
    s = starten(kind_a, fach)
    services.frage_stellen(s, zufall=random.Random(1))
    html = kind_client.post(
        reverse("lernen:antwort", args=[s.pk]), {"eingabe": "nix"}, **HX
    ).content.decode()
    assert "data-lernen-fehlergrund" not in html


# --- W-8.1: Kalibrierung -----------------------------------------------------------------------


def test_kalibrierung_satz_nennt_erwartung_und_ergebnis(kind_a, fach, uhr):
    s = starten(kind_a, fach, erwartung=Erwartung.VIELES)
    mit_antworten(s, uhr, 3)
    antwort_schritt(s, uhr, richtig=False, seed=7)
    services.sitzung_beenden(s, jetzt=uhr.jetzt)
    satz = selectors.kalibrierung_satz(s)
    assert "3 von 4" in satz
    assert str(Erwartung.VIELES.label) in satz


def test_kalibrierung_satz_leer_ohne_antworten(kind_a, fach):
    s = starten(kind_a, fach)
    assert selectors.kalibrierung_satz(s) == ""


def test_kalibrierung_woche_zaehlt_treffer(kind_a, kind_b, fach, uhr):
    def runde(kind, erwartung, richtig_n, falsch_n):
        s = starten(kind, fach, erwartung=erwartung)
        mit_antworten(s, uhr, richtig_n)
        for i in range(falsch_n):
            antwort_schritt(s, uhr, richtig=False, seed=20 + i)
        services.sitzung_beenden(s, jetzt=uhr.jetzt)

    runde(kind_a, Erwartung.VIELES, 5, 0)  # passt
    runde(kind_a, Erwartung.WENIGES, 5, 0)  # mehr als gedacht
    runde(kind_a, Erwartung.EINIGES, 3, 2)  # passt (60 %)
    runde(kind_b, Erwartung.VIELES, 1, 4)  # anderes Kind
    treffer, gesamt = selectors.kalibrierung_woche(kind_a, zeit.heute())
    assert (treffer, gesamt) == (2, 3)
    assert selectors.kalibrierung_woche(kind_b, zeit.heute()) == (0, 1)
    uhr.weiter(days=8)
    assert selectors.kalibrierung_woche(kind_a, zeit.heute()) == (0, 0)


def test_kalibrierung_auf_der_ergebnisseite_und_der_startseite(kind_client, kind_a, fach, uhr):
    for _ in range(2):
        s = starten(kind_a, fach, erwartung=Erwartung.VIELES)
        mit_antworten(s, uhr, 4)
        services.sitzung_beenden(s, jetzt=uhr.jetzt)
    html = kind_client.get(reverse("lernen:sitzung", args=[s.pk])).content.decode()
    assert "data-lernen-kalibrierung" in html and "4 von 4" in html
    start_html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "data-lernen-kalibrierung-woche" in start_html


def test_kalibrierung_woche_erst_ab_zwei_runden_sichtbar(kind_client, kind_a, fach, uhr):
    s = starten(kind_a, fach, erwartung=Erwartung.VIELES)
    mit_antworten(s, uhr, 4)
    services.sitzung_beenden(s, jetzt=uhr.jetzt)
    start_html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "data-lernen-kalibrierung-woche" not in start_html


# --- W-8.5: Strategie-Funktion -----------------------------------------------------------------


def test_jede_strategie_hat_einen_hinweis_und_mathe_redet_nicht_von_woertern():
    for s in Strategie.values:
        assert strategie.hinweis(s, mathe=False)
        mathe_text = strategie.hinweis(s, mathe=True)
        assert mathe_text
        assert "Wort" not in mathe_text and "Vokabel" not in mathe_text


def test_neue_strategien_aufschreiben_und_beispiel():
    assert {"aufschreiben", "beispiel"} <= set(Strategie.values)
    assert "Blatt" in strategie.hinweis(Strategie.AUFSCHREIBEN, mathe=True)
    assert strategie.karte_offen(Strategie.BEISPIEL)
    assert not strategie.karte_offen(Strategie.ABDECKEN)


def test_strategie_labels_nennen_kein_wort_fuer_mathe():
    assert "Wort" not in str(Strategie.LAUT.label)


def test_hinweis_steht_auf_der_fragenseite(kind_client, kind_a, fach):
    s = starten(kind_a, fach, strategie=Strategie.AUFSCHREIBEN)
    html = kind_client.get(reverse("lernen:sitzung", args=[s.pk])).content.decode()
    assert "data-lernen-strategie-hinweis" in html
    assert strategie.hinweis(Strategie.AUFSCHREIBEN, mathe=False) in html


def test_beispiel_strategie_klappt_die_mathe_karte_auf(kind_client, kind_a, mathe):
    stufe(kind_a, mathe, 3)
    alle_generatoren_aus_ausser("add_sub_100")
    offen = start(kind_a, mathe, strategie=Strategie.BEISPIEL)
    html = kind_client.get(reverse("lernen:sitzung", args=[offen.pk])).content.decode()
    assert "data-lernen-karte=" in html
    karte = html.split("data-lernen-karte=")[1].split(">")[0]
    assert " open" in karte
    zu = start(kind_a, mathe, strategie=Strategie.ABDECKEN)
    html = kind_client.get(reverse("lernen:sitzung", args=[zu.pk])).content.decode()
    karte = html.split("data-lernen-karte=")[1].split(">")[0]
    assert " open" not in karte


def test_startseite_bietet_alle_strategien(kind_client, fach):
    html = kind_client.get(reverse("lernen:start")).content.decode()
    for wert in Strategie.values:
        assert f'<option value="{wert}"' in html


# --- Migration 0026 ----------------------------------------------------------------------------


def test_migration_senkt_nur_das_alte_tageslimit():
    from importlib import import_module

    from django.apps import apps as django_apps

    from apps.kern.models import Einstellung

    migration = import_module("apps.lernen.migrations.0026_startwerte_punkte")
    Einstellung.objects.filter(schluessel="lernen.lernpunkte_tageslimit").update(wert=10)
    migration.anlegen(django_apps, None)
    assert einstellungen.wert("lernen.lernpunkte_tageslimit") == 8
    Einstellung.objects.filter(schluessel="lernen.lernpunkte_tageslimit").update(wert=9)
    migration.anlegen(django_apps, None)
    assert einstellungen.wert("lernen.lernpunkte_tageslimit") == 9  # eigener Wert bleibt
