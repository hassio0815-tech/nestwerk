"""Aufgaben "für jedes Kind": eigene Aufgabe je Kind (Zimmer aufräumen, Wäsche ...)."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.aufgaben import services
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus, Vorlage

pytestmark = pytest.mark.django_db


def daten(**extra):
    d = {"titel": "Zimmer aufräumen", "punkte": "20", "freigabeart": "eltern"}
    d["wiederholungsart"] = "einmalig"
    d.update(extra)
    return d


def test_anlegen_je_kind_erzeugt_eine_aufgabe_pro_kind(eltern_client, anna, ben):
    antwort = eltern_client.post(reverse("aufgaben:neu"), daten(je_kind="on"))
    assert antwort.status_code == 302
    aufgaben = Aufgabe.objects.filter(titel="Zimmer aufräumen")
    assert {a.zugewiesen_an_id for a in aufgaben} == {anna.pk, ben.pk}
    # jede Aufgabe hat ihre eigene offene Instanz
    for a in aufgaben:
        assert AufgabenInstanz.objects.filter(aufgabe=a, status=InstanzStatus.OFFEN).count() == 1


def test_ohne_je_kind_bleibt_es_eine_aufgabe(eltern_client, anna, ben):
    eltern_client.post(reverse("aufgaben:neu"), daten())
    assert Aufgabe.objects.filter(titel="Zimmer aufräumen", zugewiesen_an=None).count() == 1


def test_je_kind_gilt_auch_fuer_schnellknoepfe(eltern_client, anna, ben):
    eltern_client.post(reverse("aufgaben:neu"), daten(wiederholungsart="bei_bedarf", je_kind="on"))
    assert (
        Aufgabe.objects.filter(titel="Zimmer aufräumen", wiederholungsart="bei_bedarf").count() == 2
    )


def test_bearbeiten_zeigt_kein_je_kind(eltern_client, mama):
    a = Aufgabe.objects.create(titel="A", punkte=5, erstellt_von=mama)
    html = eltern_client.get(reverse("aufgaben:bearbeiten", args=[a.pk])).content.decode()
    assert 'name="je_kind"' not in html


def test_vorlagen_zimmer_und_waesche_sind_je_kind(eltern_client):
    assert Vorlage.objects.get(titel="Zimmer gründlich").je_kind
    assert Vorlage.objects.get(titel="Wäsche zusammenlegen & einräumen").je_kind
    assert not Vorlage.objects.get(titel="Wäsche waschen").je_kind
    v = Vorlage.objects.get(titel="Zimmer gründlich")
    html = eltern_client.get(reverse("aufgaben:vorlage_als_aufgabe", args=[v.pk])).content.decode()
    assert (
        'name="je_kind"' in html
        and "checked"
        in html.split('name="je_kind"')[0][-200:] + html.split('name="je_kind"')[1][:200]
    )


def test_bestehende_aufgabe_aufteilen(mama, anna, ben):
    a = Aufgabe.objects.create(
        titel="Wäsche", punkte=10, erstellt_von=mama, wiederholungsart="einmalig"
    )
    services.instanzen_erzeugen(aufgaben=Aufgabe.objects.filter(pk=a.pk))
    neue = services.je_kind_aufteilen(a, von=mama)
    assert len(neue) == 2
    assert {x.zugewiesen_an_id for x in neue} == {anna.pk, ben.pk}
    assert Aufgabe.objects.filter(titel="Wäsche").count() == 2


def test_aufteilen_lehnt_zugewiesene_ab(mama, anna, ben):
    from django.core.exceptions import ValidationError

    a = Aufgabe.objects.create(titel="X", punkte=5, erstellt_von=mama, zugewiesen_an=anna)
    with pytest.raises(ValidationError):
        services.je_kind_aufteilen(a)


def test_befehl_teilt_auf(mama, anna, ben, capsys):
    a = Aufgabe.objects.create(titel="Zimmer", punkte=5, erstellt_von=mama)
    call_command("aufgabe_je_kind", str(a.pk))
    assert Aufgabe.objects.filter(titel="Zimmer").count() == 2
