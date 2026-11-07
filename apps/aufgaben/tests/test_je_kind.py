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
    assert Vorlage.objects.get(titel="Zimmer gründlich reinigen und aufräumen").je_kind
    assert Vorlage.objects.get(titel="Wäsche zusammenlegen & einräumen").je_kind
    assert not Vorlage.objects.get(titel="Wäsche waschen").je_kind


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


# --- Aufteilen: laufende Instanzen folgen ihrem Kind (Review P2) -----------------------------


def _laufend_fuer(aufgabe, kind, **felder):
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        kind=kind,
        titel_snapshot=aufgabe.titel,
        punkte_snapshot=aufgabe.punkte,
        freigabeart_snapshot=aufgabe.freigabeart,
        **felder,
    )


def test_aufteilen_haengt_instanzen_des_kindes_an_dessen_kopie(mama, anna, ben):
    from apps.aufgaben.models import Interesse

    a = Aufgabe.objects.create(titel="Wäsche", punkte=10, erstellt_von=mama)
    fuer_ben = _laufend_fuer(a, ben, status=InstanzStatus.RESERVIERT)
    interesse = Interesse.objects.create(instanz=fuer_ben, kind=ben, status="zugeteilt")
    fertig_ben = _laufend_fuer(a, ben, status=InstanzStatus.BESTAETIGT)
    fuer_anna = _laufend_fuer(a, anna, status=InstanzStatus.GEMELDET)
    neue = services.je_kind_aufteilen(a, von=mama)
    kopie_ben = next(x for x in neue if x.zugewiesen_an_id == ben.pk)
    original = next(x for x in neue if x.zugewiesen_an_id == anna.pk)
    for instanz in (fuer_ben, fertig_ben, fuer_anna):
        instanz.refresh_from_db()
    assert fuer_ben.aufgabe_id == fertig_ben.aufgabe_id == kopie_ben.pk
    assert fuer_anna.aufgabe_id == original.pk
    interesse.refresh_from_db()
    assert interesse.instanz.aufgabe_id == kopie_ben.pk


def test_aufteilen_plant_nur_freie_instanzen_neu(mama, anna, ben):
    a = Aufgabe.objects.create(
        titel="Wäsche", punkte=10, erstellt_von=mama, wiederholungsart="einmalig"
    )
    services.instanzen_erzeugen(aufgaben=Aufgabe.objects.filter(pk=a.pk))
    neue = services.je_kind_aufteilen(a, von=mama)
    for x in neue:
        assert AufgabenInstanz.objects.filter(aufgabe=x, status=InstanzStatus.OFFEN).count() == 1


def test_aufteilen_nur_aktive_aufgaben(mama, anna, ben):
    from django.core.exceptions import ValidationError

    a = Aufgabe.objects.create(titel="X", punkte=5, erstellt_von=mama, status="pausiert")
    with pytest.raises(ValidationError):
        services.je_kind_aufteilen(a)
    assert Aufgabe.objects.count() == 1 and a.zugewiesen_an_id is None


def test_befehl_sammelt_fehler_und_macht_weiter(mama, anna, ben, capsys):
    from django.core.management.base import CommandError

    gut = Aufgabe.objects.create(titel="Gut", punkte=5, erstellt_von=mama)
    schon = Aufgabe.objects.create(titel="Schon", punkte=5, erstellt_von=mama, zugewiesen_an=anna)
    pausiert = Aufgabe.objects.create(titel="Pause", punkte=5, erstellt_von=mama, status="pausiert")
    with pytest.raises(CommandError) as fehler:
        call_command("aufgabe_je_kind", "99999", str(schon.pk), str(pausiert.pk), str(gut.pk))
    assert "99999" in str(fehler.value)
    ausgabe = capsys.readouterr()
    assert "Schon" in ausgabe.err + ausgabe.out and "Pause" in ausgabe.err + ausgabe.out
    assert Aufgabe.objects.filter(titel="Gut").count() == 2  # trotz früherer Fehler geteilt
    assert Aufgabe.objects.filter(titel="Schon").count() == 1


def test_befehl_ueberspringt_geteilte_ohne_fehler(mama, anna, ben):
    a = Aufgabe.objects.create(titel="Zimmer", punkte=5, erstellt_von=mama)
    call_command("aufgabe_je_kind", str(a.pk))
    call_command("aufgabe_je_kind", str(a.pk))  # schon zugewiesen: Hinweis, kein Abbruch
    assert Aufgabe.objects.filter(titel="Zimmer").count() == 2


def test_befehl_dry_run_aendert_nichts(mama, anna, ben, capsys):
    a = Aufgabe.objects.create(titel="Zimmer", punkte=5, erstellt_von=mama)
    _laufend_fuer(a, ben, status=InstanzStatus.RESERVIERT)
    call_command("aufgabe_je_kind", "--dry-run", str(a.pk))
    assert "Zimmer" in capsys.readouterr().out
    assert Aufgabe.objects.filter(titel="Zimmer").count() == 1
    a.refresh_from_db()
    assert a.zugewiesen_an_id is None
    assert AufgabenInstanz.objects.get().aufgabe_id == a.pk


def test_je_kind_ohne_aktive_kinder_ist_formularhinweis(eltern_client, mama):
    antwort = eltern_client.post(
        reverse("aufgaben:neu"), daten(je_kind="on"), HTTP_HX_REQUEST="true"
    )
    assert antwort.status_code == 200
    assert "keine aktiven Kinder" in antwort.content.decode()
    assert not Aufgabe.objects.exists()
