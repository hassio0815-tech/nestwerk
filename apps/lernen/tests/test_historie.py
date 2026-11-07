"""Etappe 11: Karte und Historie (W-3), Hilfe zählt (W-1), Rückschau sichtbar (W-8.3),
"zu leicht/zu schwer" wirkt (W-8.4) und Vorbelegung der letzten Auswahl."""

import random
import re
from datetime import timedelta

import pytest
from django.urls import reverse

from apps.kern import zeit
from apps.lernen import historie, mathe_aufgaben, services, woche_selectors
from apps.lernen.mathe import schwierigkeit
from apps.lernen.models import (
    Ergebnis,
    Fach,
    Frage,
    Karte,
    Lernsitzung,
    Lernstand,
    Versuch,
)


@pytest.fixture
def mathe(db):
    return Fach.objects.get(schluessel="mathe")


def _start(kind, fach, **extra):
    extra.setdefault("ziel_fragen", 100)
    return services.sitzung_starten(kind, fach, **extra)


def _richtig(s, seed=1):
    a = services.frage_stellen(s, zufall=random.Random(seed))
    return a, services.antworten(s, a.loesung)


def _vokabel_richtig(s, hilfe=0):
    a = services.frage_stellen(s, zufall=random.Random(3))
    s.aktuell_hilfe = hilfe
    s.save()
    return a, services.antworten(s, a.erwartet)


# --- W-3 Karte und Historie -----------------------------------------------------------------------


def test_versuch_ueberlebt_aufraeumen_und_behaelt_die_karte(kind_a, mathe):
    services.leistungsstufe_setzen(kind_a, mathe, "Grundniveau", 3)
    s = _start(kind_a, mathe)
    a, _ = _richtig(s, 25)
    Frage.objects.filter(pk=a.frage.pk).update(erstellt=zeit.jetzt() - timedelta(days=100))
    Lernstand.objects.filter(frage=a.frage).update(faellig_am=zeit.heute() - timedelta(days=200))
    assert mathe_aufgaben.aufraeumen(zeit.jetzt()) == 1
    assert not Frage.objects.filter(pk=a.frage.pk).exists()
    v = Versuch.objects.get(sitzung=s)
    assert v.frage is None
    assert v.karte is not None
    assert v.karte.kind == kind_a
    assert a.frage.generator in v.karte.schluessel
    assert v.thema_id == a.frage.thema_id
    s.refresh_from_db()
    assert s.versuche == 1


def test_karte_je_kind_fach_und_schluessel_ist_stabil(kind_a, kind_b, fach):
    s = _start(kind_a, fach)
    a, _ = _vokabel_richtig(s)
    k1 = Versuch.objects.get().karte
    assert k1.fach_id == fach.pk
    assert historie.karte_holen(kind_a, a.frage, a.richtung).pk == k1.pk  # kein Duplikat
    assert historie.karte_holen(kind_b, a.frage, a.richtung).pk != k1.pk  # eigene Karte je Kind
    andere = "en_de" if a.richtung == "de_en" else "de_en"
    assert historie.karte_holen(kind_a, a.frage, andere).pk != k1.pk  # Richtung zählt
    assert Karte.objects.filter(kind=kind_a).count() == 2


def test_versuch_speichert_abstand_und_geplanten_tag(kind_a, fach, uhr):
    s = _start(kind_a, fach)
    a, _ = _vokabel_richtig(s)
    erster = Versuch.objects.get()
    assert erster.abstand_tage is None  # noch kein früherer Versuch
    assert erster.geplant_am is None
    stand = Lernstand.objects.get()
    heute = zeit.heute()
    Lernstand.objects.filter(pk=stand.pk).update(
        zuletzt=zeit.jetzt() - timedelta(days=5), faellig_am=heute - timedelta(days=2)
    )
    s.aktuell_frage = a.frage
    s.aktuell_richtung = a.richtung
    s.aktuell_seit = zeit.jetzt()
    s.save()
    services.antworten(s, a.erwartet)
    zweiter = Versuch.objects.order_by("-id").first()
    assert zweiter.abstand_tage == 5
    assert zweiter.geplant_am == heute - timedelta(days=2)


def test_karten_nachtragen_fuellt_bestandsdaten(kind_a, fach):
    s = _start(kind_a, fach)
    a, _ = _vokabel_richtig(s)
    # Zustand vor der Migration herstellen: Versuch und Lernstand ohne Karte und Thema
    Versuch.objects.update(karte=None, thema=None)
    Lernstand.objects.update(karte=None)
    Karte.objects.all().delete()
    historie.karten_nachtragen()
    historie.karten_nachtragen()  # idempotent
    v = Versuch.objects.get()
    assert v.karte is not None and v.thema_id == a.frage.thema_id
    assert Lernstand.objects.get().karte_id == v.karte_id
    assert Karte.objects.count() == 1


# --- W-1 Hilfe zählt ------------------------------------------------------------------------------


def test_richtig_mit_hilfe_5_rueckt_die_karte_nicht_vor(kind_a, fach):
    s = _start(kind_a, fach)
    _vokabel_richtig(s, hilfe=5)
    stand = Lernstand.objects.get()
    assert stand.box == 0
    assert stand.versuche == 1 and stand.richtige == 0
    assert stand.faellig_am == zeit.heute() + timedelta(days=1)  # erste Box, nicht weiter
    assert Versuch.objects.get().ergebnis == Ergebnis.RICHTIG  # Punkte und Anzeige unverändert


def test_hilfe_3_haelt_eine_vorgerueckte_karte_in_ihrer_box(kind_a, fach):
    s = _start(kind_a, fach)
    a, _ = _vokabel_richtig(s)
    assert Lernstand.objects.get().box == 1
    s.aktuell_frage, s.aktuell_richtung, s.aktuell_seit = a.frage, a.richtung, zeit.jetzt()
    s.aktuell_hilfe = 3
    s.save()
    services.antworten(s, a.erwartet)
    assert Lernstand.objects.get().box == 1


def test_hilfe_2_rueckt_weiter_wie_bisher(kind_a, fach):
    s = _start(kind_a, fach)
    _vokabel_richtig(s, hilfe=2)
    assert Lernstand.objects.get().box == 1


def test_falsch_mit_hilfe_faellt_wie_bisher_zurueck(kind_a, fach):
    s = _start(kind_a, fach)
    a, _ = _vokabel_richtig(s)
    s.aktuell_frage, s.aktuell_richtung, s.aktuell_seit = a.frage, a.richtung, zeit.jetzt()
    s.aktuell_hilfe = 4
    s.save()
    services.antworten(s, "xyzxyzxyz")
    assert Lernstand.objects.get().box == 0


# --- W-8.3 Rückschau sichtbar ---------------------------------------------------------------------


def _rueckschau(kind, fach, geholfen, schwer="", einschaetzung="", **extra):
    s = _start(kind, fach, **extra)
    services.rueckschau_speichern(s, schwer=schwer, geholfen=geholfen, einschaetzung=einschaetzung)
    return s


def test_rueckschau_erscheint_beim_naechsten_start(kind_a, kind_client, fach):
    _rueckschau(kind_a, fach, "Laut vorlesen", schwer="Die langen Wörter")
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "Laut vorlesen" in html
    assert "Die langen Wörter" in html
    assert "data-lernen-rueckschau" in html
    assert "data-lernen-rueckschau-hinweis" in html  # Kind erfährt, dass Eltern mitlesen


def test_ohne_rueckschau_kein_block(kind_a, kind_client, fach):
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "data-lernen-rueckschau" not in html


def test_leere_rueckschau_wird_nicht_gezeigt(kind_a, kind_client, fach):
    _rueckschau(kind_a, fach, "")
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "data-lernen-rueckschau" not in html


def test_rueckschau_des_anderen_kindes_bleibt_unsichtbar(kind_a, kind_b, kind_client, fach):
    _rueckschau(kind_b, fach, "Geheimtipp-von-B")
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "Geheimtipp-von-B" not in html


def test_eltern_sehen_die_letzten_drei_rueckschauen(kind_a, kind_b, eltern_client, fach, uhr):
    for i in range(4):
        uhr.weiter(hours=1)
        _rueckschau(kind_a, fach, f"Tipp-Nr-{i}")
    _rueckschau(kind_b, fach, "Tipp-von-B")
    bild = woche_selectors.wochenbild(kind_a, zeit.heute(), None)
    assert [r.geholfen for r in bild.rueckschauen] == ["Tipp-Nr-3", "Tipp-Nr-2", "Tipp-Nr-1"]
    html = eltern_client.get(reverse("lernen:eltern_woche")).content.decode()
    assert "Tipp-Nr-3" in html and "Tipp-Nr-1" in html
    assert "Tipp-Nr-0" not in html
    assert "Tipp-von-B" in html  # eigener Block des Kindes B
    assert [r.geholfen for r in woche_selectors.wochenbild(kind_b, zeit.heute()).rueckschauen] == [
        "Tipp-von-B"
    ]


# --- W-8.4 zu leicht / zu schwer wirkt ------------------------------------------------------------


def test_schwierigkeit_nimmt_versatz_an_und_bleibt_im_bereich():
    basis = schwierigkeit.schwierigkeit("grund", "normal", [])
    assert schwierigkeit.schwierigkeit("grund", "normal", [], versatz=1) == basis + 1
    assert schwierigkeit.schwierigkeit("grund", "normal", [], versatz=-1) == basis - 1
    assert schwierigkeit.schwierigkeit("grund", "normal", [], versatz=5) == 3  # Obergrenze
    assert schwierigkeit.schwierigkeit("grund", "normal", [], versatz=-5) == 1


def _stufe_der_naechsten(kind, mathe):
    s = _start(kind, mathe)
    return mathe_aufgaben.stufe_fuer(kind, mathe, s, "einmaleins", {})


@pytest.mark.parametrize(
    "wahl,delta", [("zu_schwer", -1), ("zu_leicht", 1), ("passend", 0), ("", 0)]
)
def test_einschaetzung_wirkt_auf_die_naechste_sitzung(kind_a, mathe, wahl, delta):
    services.leistungsstufe_setzen(kind_a, mathe, "Grundniveau", 3)
    basis = _stufe_der_naechsten(kind_a, mathe)
    s = _start(kind_a, mathe)
    services.rueckschau_speichern(s, einschaetzung=wahl)
    assert _stufe_der_naechsten(kind_a, mathe) == basis + delta


def test_einschaetzung_gilt_nur_fuer_die_naechste_sitzung_und_nur_dieses_kind(
    kind_a, kind_b, mathe
):
    for k in (kind_a, kind_b):
        services.leistungsstufe_setzen(k, mathe, "Grundniveau", 3)
    basis = _stufe_der_naechsten(kind_b, mathe)
    s = _start(kind_a, mathe)
    services.rueckschau_speichern(s, einschaetzung="zu_schwer")
    assert _stufe_der_naechsten(kind_b, mathe) == basis
    # danach eine Sitzung mit "passend": der Versatz ist weg
    s2 = _start(kind_a, mathe)
    services.rueckschau_speichern(s2, einschaetzung="passend")
    assert _stufe_der_naechsten(kind_a, mathe) == basis


# --- Vorbelegung der letzten Auswahl --------------------------------------------------------------


def _checked(html, name):
    m = re.search(rf'name="{name}" value="([a-z_]+)" checked', html)
    return m.group(1) if m else None


def test_start_ohne_vorgeschichte_hat_die_bisherigen_standardwerte(kind_a, kind_client, fach):
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert _checked(html, "vorhaben") == "wiederholen"
    assert _checked(html, "strategie") == "abdecken"
    assert _checked(html, "erwartung") == "einiges"
    assert _checked(html, "intensitaet") == "normal"


def test_start_ist_mit_der_letzten_auswahl_vorbelegt(kind_a, kind_client, fach):
    s = _start(
        kind_a,
        fach,
        vorhaben="neu",
        strategie="laut",
        erwartung="vieles",
        intensitaet="herausforderung",
    )
    services.sitzung_beenden(s)
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert _checked(html, "vorhaben") == "neu"
    assert _checked(html, "erwartung") == "vieles"
    assert _checked(html, "intensitaet") == "herausforderung"
    assert _checked(html, "strategie") == Lernsitzung.objects.get().strategie


def test_vorbelegung_nimmt_das_zuletzt_geuebte_fach(kind_a, kind_client, fach):
    s = _start(kind_a, fach)
    services.sitzung_beenden(s)
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert re.search(rf'<option value="fach:{fach.pk}" selected', html)
