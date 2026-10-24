"""Bauplan-Format, Prüfung, Erzeugen (Grundlage für AP25) und der Befehl avatar_pruefen."""

import copy
import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.avatar.generator import bauplaene, bibliothek, renderer, svgsicher
from apps.avatar.models import ModDefinition, Slot, Thema


def gueltig():
    return copy.deepcopy(bibliothek.bauplaene_aus_dateien()[0])


def test_ein_thema_komplett_mit_allen_slots_common():
    plaene = [p for p in bibliothek.bauplaene_aus_dateien() if p["thema"] == "ritter"]
    assert {p["slot"] for p in plaene} == set(bibliothek.slot_schluessel())
    assert {p["seltenheit"] for p in plaene} == {1}
    for p in plaene:
        assert bauplaene.bauplan_pruefen(p) == []
        assert svgsicher.svg_pruefen(renderer.rendern(bauplaene.zustand_fuer_vorschau(p))) is None


@pytest.mark.parametrize("thema", [t["schluessel"] for t in bibliothek.kind_themen()])
def test_generator_liefert_fuer_alle_36_pro_thema_gueltige_baupleane(thema):
    schluessel = set()
    for slot in bibliothek.slot_schluessel():
        for stufe in range(1, 7):
            plan = bauplaene.bauplan_erzeugen(thema, slot, stufe)
            assert bauplaene.bauplan_pruefen(plan) == [], plan
            assert plan == bauplaene.bauplan_erzeugen(thema, slot, stufe)  # deterministisch
            schluessel.add(plan["schluessel"])
            renderer.rendern(bauplaene.zustand_fuer_vorschau(plan))
    assert len(schluessel) == 36


@pytest.mark.parametrize(
    ("aenderung", "teil"),
    [
        ({"schluessel": "Gross Schreibung"}, "schluessel"),
        ({"schluessel": ""}, "schluessel"),
        ({"name": ""}, "name"),
        ({"name": "x" * 61}, "name"),
        ({"beschreibung": "x" * 201}, "beschreibung"),
        ({"thema": "gibtsnicht"}, "thema"),
        ({"thema": "eltern"}, "thema"),
        ({"slot": "fuesse"}, "slot"),
        ({"seltenheit": 0}, "seltenheit"),
        ({"seltenheit": 7}, "seltenheit"),
        ({"seltenheit": True}, "seltenheit"),
        ({"preis": -1}, "preis"),
        ({"preis": "40"}, "preis"),
        ({"bauzeit_stunden": 1.5}, "bauzeit"),
        ({"teile": []}, "teile"),
        ({"teile": "x"}, "teile"),
        ({"teile": [{"form": "gibtsnicht"}]}, "form"),
        ({"teile": [{"form": "helm_rund", "muster": "zebra"}]}, "muster"),
        ({"teile": [{"form": "helm_rund", "farben": {"a": "grün"}}]}, "farben"),
        ({"teile": [{"form": "helm_rund", "farben": {"q": "p1"}}]}, "Platzhalter"),
        ({"teile": [{"form": "helm_rund", "dx": 50}]}, "dx"),
        ({"teile": [{"form": "helm_rund", "unsinn": 1}]}, "unsinn"),
        ({"teile": [{"form": "schwert"}]}, "form"),  # Form eines anderen Slots
        ({"svg_override": "<svg><script>x</script></svg>"}, "svg_override"),
    ],
)
def test_bauplan_pruefen_findet_fehler(aenderung, teil):
    plan = {**gueltig(), **aenderung}
    fehler = bauplaene.bauplan_pruefen(plan)
    assert fehler and any(teil in f for f in fehler), fehler


def test_gueltiger_bauplan_und_nichtobjekt():
    assert bauplaene.bauplan_pruefen(gueltig()) == []
    assert bauplaene.bauplan_pruefen("x")


def test_dateien_sind_gueltig_und_eindeutig():
    plaene = bibliothek.bauplaene_aus_dateien()
    assert len({p["schluessel"] for p in plaene}) == len(plaene)
    assert len({(p["thema"], p["slot"], p["seltenheit"]) for p in plaene}) == len(plaene)
    for p in plaene:
        assert bauplaene.bauplan_pruefen(p) == [], p["schluessel"]


# --- Befehle -----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_bibliothek_ist_nach_migrate_in_der_datenbank():
    assert Slot.objects.count() == 6
    assert Thema.objects.count() == 11
    assert Thema.objects.filter(nur_eltern=True).count() == 1
    assert ModDefinition.objects.filter(thema__schluessel="ritter", seltenheit=1).count() == 6
    ritter = Thema.objects.get(schluessel="ritter")
    assert ritter.palette["p1"].startswith("#")
    assert "grundausstattung" in ritter.als_dict()


@pytest.mark.django_db
def test_avatar_laden_ist_idempotent_und_ueberschreibt_nur_auf_wunsch():
    ModDefinition.objects.filter(schluessel="ritter-kopf-1").update(name="Handarbeit")
    call_command("avatar_laden", stdout=io.StringIO())
    assert ModDefinition.objects.get(schluessel="ritter-kopf-1").name == "Handarbeit"
    call_command("avatar_laden", "--ueberschreiben", stdout=io.StringIO())
    assert ModDefinition.objects.get(schluessel="ritter-kopf-1").name == "Eisenhelm"
    assert ModDefinition.objects.count() == 6


@pytest.mark.django_db
def test_avatar_pruefen_ist_gruen():
    aus = io.StringIO()
    call_command("avatar_pruefen", stdout=aus)
    assert "alles in Ordnung" in aus.getvalue()
    assert " 0 Fehler" in aus.getvalue()


@pytest.mark.django_db
def test_avatar_pruefen_meldet_kaputte_db_baupleane():
    mod = ModDefinition.objects.get(schluessel="ritter-kopf-1")
    ModDefinition.objects.filter(pk=mod.pk).update(
        svg_override='<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>'
    )
    err = io.StringIO()
    with pytest.raises(CommandError):
        call_command("avatar_pruefen", stdout=io.StringIO(), stderr=err)
    assert "ritter-kopf-1" in err.getvalue() and "script" in err.getvalue()


@pytest.mark.django_db
def test_modelle_pruefen_override_in_clean():
    from django.core.exceptions import ValidationError

    mod = ModDefinition.objects.get(schluessel="ritter-kopf-1")
    mod.svg_override = '<svg xmlns="http://www.w3.org/2000/svg"><rect onload="x()"/></svg>'
    with pytest.raises(ValidationError):
        mod.full_clean()


def test_varianten_erzeugen_stdout_schreibt_nichts(tmp_path):
    aus = io.StringIO()
    call_command("avatar_varianten_erzeugen", "--thema", "ninja", "--stdout", stdout=aus)
    daten = json.loads(aus.getvalue())
    assert daten["format"] == 1 and len(daten["bauplaene"]) == 36
    assert not (bibliothek.DATEN / "bauplaene" / "ninja.json").exists()


def test_varianten_erzeugen_kennt_nur_kinder_themen():
    with pytest.raises(CommandError):
        call_command("avatar_varianten_erzeugen", "--thema", "eltern", "--stdout")
