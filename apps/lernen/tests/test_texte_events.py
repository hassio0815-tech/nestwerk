"""Töne nach Sprachstufe, Übersetzung, Ereignistext (DE/EN) und Registry."""

import pytest
from django.urls import reverse
from django.utils import translation

from apps.benachrichtigung import texte as benachrichtigung
from apps.ereignisse.models import Ereignis
from apps.ereignisse.registry import typ as ereignis_typ
from apps.kern import einstellungen
from apps.kern import registry as kern_registry
from apps.lernen import events, services, texte
from apps.lernen.models import (
    Ergebnis,
    Erwartung,
    Fach,
    Frage,
    Intensitaet,
    Lernmappe,
    Lernpause,
    Lernsitzung,
    Lernstand,
    Lerntag,
    Lernziel,
    Versuch,
)
from apps.lernen.tests.test_ueben import laufen


@pytest.mark.parametrize(
    ("klasse", "stufe"),
    [(None, 2), (1, 1), (4, 1), (5, 2), (7, 2), (8, 3), (13, 3)],
)
def test_stufen(klasse, stufe):
    assert texte.stufe_fuer(klasse) == stufe


def test_jeder_ton_hat_drei_stufen_und_parameter_passen():
    for schluessel in texte.schluessel():
        saetze = {texte.msgid(schluessel, s) for s in (1, 2, 3)}
        assert len(saetze) == 3, schluessel
    assert "15" in texte.ton("ziel_gesenkt", 2, minuten=15)
    assert "3" in texte.ton("serie", 1, wochen=3)
    assert texte.ton("richtig", 3) == "Richtig."


def test_ton_ohne_vorwurf():
    for schluessel in texte.schluessel():
        for s in (1, 2, 3):
            satz = texte.msgid(schluessel, s).lower()
            assert "falsch" not in satz, schluessel
            assert "schlecht" not in satz and "versagt" not in satz


def test_toene_auf_englisch():
    with translation.override("en"):
        for schluessel in texte.schluessel():
            for s in (1, 2, 3):
                msgid = texte.msgid(schluessel, s)
                params = {"minuten": 5, "wochen": 3}
                uebersetzt = texte.ton(schluessel, s, **params)
                assert uebersetzt != msgid % params if "%(" in msgid else uebersetzt != msgid, msgid


def test_ereignistyp_und_text(kind_a, fach, uhr):
    typ = ereignis_typ(events.LERNZIEL_ERREICHT)
    assert (typ.zielgruppe, typ.modul) == ("kind", "lernen")
    einstellungen.setzen("lernen.tagesziel_minuten", 6, akteur=None)
    s = services.sitzung_starten(kind_a, fach)
    laufen(s, uhr, 400)
    ereignis = Ereignis.objects.get(typ_id=events.LERNZIEL_ERREICHT)
    titel, text = benachrichtigung.rendern(ereignis, "Lernziel erreicht")
    assert (titel, text) == ("Tagesziel geschafft!", "Tagesziel geschafft. Das Dranbleiben zählt.")
    with translation.override("en"):
        titel, text = benachrichtigung.rendern(ereignis, "Lernziel erreicht")
    assert titel == "Daily goal reached!"
    assert text == "Daily goal reached. Sticking with it is what counts."


def test_metrik_im_katalog(db):
    assert kern_registry.metrik("tage_geuebt").einheit == "Tage"


def test_seiten_auf_englisch(kind_client, kind_a, fach):
    antwort = kind_client.get(reverse("lernen:start"), HTTP_ACCEPT_LANGUAGE="en")
    html = antwort.content.decode()
    assert "New round" in html and "What do you want to practise?" in html
    assert "Neue Runde" not in html


def test_modelle_haben_lesbare_namen(kind_a, fach):
    s = services.sitzung_starten(kind_a, fach, erwartung=Erwartung.EINIGES)
    frage = Frage.objects.filter(thema__fach=fach).first()
    stand = Lernstand.objects.create(
        kind=kind_a, frage=frage, richtung="de_en", faellig_am=s.beginn.date()
    )
    versuch = Versuch.objects.create(
        sitzung=s, frage=frage, richtung="de_en", ergebnis=Ergebnis.RICHTIG
    )
    tag = Lerntag.objects.get(kind=kind_a)
    ziel = Lernziel.objects.get(kind=kind_a)
    pause = Lernpause.objects.create(kind=kind_a, von=s.beginn.date())
    offene = Lernpause.objects.create(kind=None, von=s.beginn.date())
    mappe = Lernmappe.objects.create(kind=kind_a)
    for objekt in (s, stand, versuch, tag, ziel, pause, offene, mappe, frage, fach, frage.thema):
        assert str(objekt)
    assert "offen" in str(pause) and "alle" in str(offene)
    assert Intensitaet.NORMAL.label == "Normal"
    assert isinstance(Lernsitzung.objects.first(), Lernsitzung) and isinstance(fach, Fach)
