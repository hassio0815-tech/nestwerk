"""Töne, Englisch, Ereignis, Einstellungen und Modelle der Prüfungsvorbereitung."""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import translation

from apps.benachrichtigung import texte as benachrichtigung
from apps.ereignisse.models import Ereignis
from apps.ereignisse.registry import typ as ereignis_typ
from apps.kern import einstellungen, zeit
from apps.lernen import events, plan_services, plan_texte
from apps.lernen.einstellungen import STARTWERTE_PRUEFUNG
from apps.lernen.models import (
    Frage,
    PortionArt,
    ProbePruefung,
    ProbeVersuch,
    Pruefungsstoff,
    Thema,
)

PARAMETER = {"braucht": 90, "hat": 40, "tage": 3, "fragen": 12, "minuten": 25, "titel": "Test"}


def test_jeder_ton_hat_drei_stufen():
    for schluessel in plan_texte.schluessel():
        saetze = {plan_texte.msgid(schluessel, s) for s in (1, 2, 3)}
        assert len(saetze) == 3, schluessel


def test_ton_ohne_vorwurf():
    verboten = re.compile(r"falsch|schlecht|versag|schuld|faul|verpasst|nachlässig", re.IGNORECASE)
    for schluessel in plan_texte.schluessel():
        for s in (1, 2, 3):
            assert not verboten.search(plan_texte.msgid(schluessel, s)), schluessel


def test_parameter_werden_eingesetzt():
    assert "90" in plan_texte.ton("zu_viel", 2, **PARAMETER) and "40" in plan_texte.ton(
        "zu_viel", 2, **PARAMETER
    )
    assert plan_texte.ton("angepasst", 2).startswith("Kein Problem")


def test_toene_auf_englisch():
    with translation.override("en"):
        for schluessel in plan_texte.schluessel():
            for s in (1, 2, 3):
                msgid = plan_texte.msgid(schluessel, s)
                uebersetzt = plan_texte.ton(schluessel, s, **PARAMETER)
                original = msgid % PARAMETER if "%(" in msgid else msgid
                assert uebersetzt != original, msgid


def test_seiten_auf_englisch(kind_client, kind_a, fach, uhr):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name="Tierwelt")
    for i in range(30):
        Frage.objects.create(thema=t, frage=f"f{i}", antwort="a")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Test", zeit.heute() + timedelta(days=14), themen=[t]
    )
    seiten = {
        reverse("lernen:pruefungen"): ["Exams", "To the plan"],
        reverse("lernen:pruefung_neu"): ["When is the exam?", "Make plan"],
        reverse("lernen:pruefung", args=[p.pk]): ["Today", "Practice exam", "Your progress"],
    }
    for adresse, erwartet in seiten.items():
        html = kind_client.get(adresse, HTTP_ACCEPT_LANGUAGE="en").content.decode()
        for text in erwartet:
            assert text in html, (adresse, text)
        assert "Heute dran" not in html and "Wann ist die Prüfung" not in html


def test_eltern_seiten_auf_englisch(eltern_client, kind_a, fach, uhr):
    html = eltern_client.get(reverse("lernen:eltern_pruefungen"), HTTP_ACCEPT_LANGUAGE="en")
    assert "Exams" in html.content.decode() and "Prüfungen" not in html.content.decode()


def test_ereignistyp_und_text_deutsch_und_englisch(kind_a, fach, uhr):
    typ = ereignis_typ(events.PRUEFUNG_VORBEREITET)
    assert (typ.zielgruppe, typ.modul) == ("kind", "lernen")
    t = Thema.objects.create(fach=fach, klassenstufe=5, name="X")
    for i in range(10):
        Frage.objects.create(thema=t, frage=f"f{i}", antwort="a")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Mathe-Test", zeit.heute() + timedelta(days=14), themen=[t]
    )
    for x in p.portionen.all():
        if x.art == PortionArt.NEU or (x.art == PortionArt.WIEDERHOLUNG and x.pflicht):
            plan_services.portion_erledigen(x, zeit.heute())
    ereignis = Ereignis.objects.get(typ_id=events.PRUEFUNG_VORBEREITET)
    titel, text = benachrichtigung.rendern(ereignis, "Prüfung vorbereitet")
    assert titel == "Prüfungsplan eingehalten!" and "Mathe-Test" in text
    with translation.override("en"):
        titel, text = benachrichtigung.rendern(ereignis, "Prüfung vorbereitet")
    assert titel == "Exam plan kept!" and "Mathe-Test" in text and "prepared" in text.lower()


def test_startwerte_sind_generisch_und_vollstaendig():
    for schluessel, wert in STARTWERTE_PRUEFUNG.items():
        assert einstellungen.wert(schluessel) == wert
    assert (
        STARTWERTE_PRUEFUNG["lernen.pruefung_puffer_rhythmus"] == 5
    )  # ein Puffertag je 5 Lerntage


def test_modelle_haben_lesbare_namen(kind_a, fach, uhr):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name="Y")
    f = Frage.objects.create(thema=t, frage="q", antwort="a")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "T", zeit.heute() + timedelta(days=10), themen=[t]
    )
    probe = ProbePruefung.objects.create(pruefung=p, fragen=[f.pk], beginn=zeit.jetzt())
    versuch = ProbeVersuch.objects.create(
        probe=probe, frage=f, richtung="de_en", ergebnis="richtig"
    )
    stoff = p.stoffe.get()
    for objekt in (p, stoff, p.portionen.first(), probe, versuch):
        assert str(objekt)
    assert stoff.name == "Y"
    assert isinstance(stoff, Pruefungsstoff)
    assert p.portionen.filter(art=PortionArt.PUFFER).first().ist_puffer is True


def test_stoff_muss_thema_oder_material_sein(kind_a, fach, uhr):
    from django.db import IntegrityError, transaction

    t = Thema.objects.create(fach=fach, klassenstufe=5, name="Z")
    Frage.objects.create(thema=t, frage="q", antwort="a")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "T", zeit.heute() + timedelta(days=10), themen=[t]
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Pruefungsstoff.objects.create(pruefung=p)
