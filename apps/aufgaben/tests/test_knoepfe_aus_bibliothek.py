"""Bibliothek -> Schnell-Knöpfe: Einteilung der Startwerte, Doppel-Schutz, Job, Migration 0016."""

import importlib

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command

from apps.aufgaben import knoepfe_start, schnellknopf
from apps.aufgaben.models import Aufgabe, SchnellknopfModus, Vorlage
from apps.kern import einstellungen
from apps.kern.models import AuditEintrag

JEDES = {
    "Zimmer gründlich reinigen und aufräumen",
    "Wäsche zusammenlegen & einräumen",
    "Vokabeln lernen 15 Min",
    "Zimmer saugen",
}
EINER = {
    "Altglas",
    "Restmüll",
    "Biomüll",
    "Müll rausbringen",
    "Mülltonnen rausstellen",
    "Leergut",
    "Spülmaschine ausräumen",
    "Spülmaschine einräumen",
    "Tisch decken/abräumen",
    "Einkaufsliste",
    "Wäsche waschen",
    "Wäsche aufhängen",
    "Flur saugen",
    "Bad putzen",
    "Rasen mähen",
    "Auto aussaugen",
    "Waschmaschine ausräumen",
}
MERKER = "aufgaben.knoepfe_aus_bibliothek"


def modus_von(titel):
    return Aufgabe.objects.get(titel=titel, wiederholungsart="bei_bedarf").schnellknopf_modus


def test_neue_vorlagen_und_umbenennung(db):
    zimmer = Vorlage.objects.get(titel="Zimmer gründlich reinigen und aufräumen")
    assert zimmer.punkte == 50 and zimmer.freigabeart == "nachweis" and zimmer.je_kind
    assert not Vorlage.objects.filter(titel="Zimmer gründlich").exists()
    saugen = Vorlage.objects.get(titel="Zimmer saugen")
    assert (saugen.punkte, saugen.kategorie.name, saugen.emoji) == (15, "Haushalt", "🧹")
    waschmaschine = Vorlage.objects.get(titel="Waschmaschine ausräumen")
    assert (waschmaschine.punkte, waschmaschine.kategorie.name, waschmaschine.emoji) == (
        10,
        "Wäsche",
        "🧺",
    )


def test_job_macht_aus_jeder_vorlage_einen_knopf_mit_richtigem_modus(mama):
    schnellknopf.schnellknoepfe_sicherstellen()
    knoepfe = Aufgabe.objects.filter(wiederholungsart="bei_bedarf")
    assert knoepfe.count() == Vorlage.objects.filter(aktiv=True).count() == 21
    for titel in JEDES:
        assert modus_von(titel) == SchnellknopfModus.JEDES, titel
    for titel in EINER:
        assert modus_von(titel) == SchnellknopfModus.EINER, titel
    assert JEDES | EINER == set(Vorlage.objects.values_list("titel", flat=True))
    zimmer = Aufgabe.objects.get(titel="Zimmer gründlich reinigen und aufräumen")
    assert zimmer.punkte == 50 and zimmer.freigabeart == "nachweis"
    assert zimmer.schnellknopf_wer == "alle" and zimmer.erstellt_von == mama
    assert zimmer.vorlage == Vorlage.objects.get(titel=zimmer.titel)
    assert zimmer.kategorie.name == "Haushalt"
    assert Aufgabe.objects.get(titel="Zimmer saugen").emoji == "🧹"
    assert all(a.emoji for a in knoepfe)
    assert einstellungen.wert(MERKER) is True


def test_audit_je_neuem_knopf(mama):
    schnellknopf.schnellknoepfe_sicherstellen()
    quellen = AuditEintrag.objects.filter(aktion="aufgabe.angelegt").values_list(
        "details__quelle", flat=True
    )
    assert list(quellen).count("bibliothek_umwandlung") == 18


def test_doppel_schutz_normalisierter_titel(mama):
    vorhanden = Aufgabe.objects.create(
        titel="  wäsche WASCHEN ",
        punkte=99,
        erstellt_von=mama,
        wiederholungsart="bei_bedarf",
    )
    schnellknopf.schnellknoepfe_sicherstellen()
    assert Aufgabe.objects.filter(titel__icontains="wäsche waschen").count() == 1
    vorhanden.refresh_from_db()
    assert vorhanden.punkte == 99


def test_wiederkehrende_aufgaben_bleiben_unberuehrt(mama):
    taeglich = Aufgabe.objects.create(
        titel="Bad putzen", punkte=7, erstellt_von=mama, wiederholungsart="intervall"
    )
    schnellknopf.schnellknoepfe_sicherstellen()
    taeglich.refresh_from_db()
    assert (taeglich.punkte, taeglich.wiederholungsart) == (7, "intervall")
    assert taeglich.schnellknopf_modus == SchnellknopfModus.EINER
    assert Aufgabe.objects.filter(titel="Bad putzen").count() == 2  # plus der neue Knopf


def test_bestehender_zimmer_knopf_bekommt_modus_jedes(mama):
    alt = Aufgabe.objects.create(
        titel="Zimmer aufräumen", punkte=10, erstellt_von=mama, wiederholungsart="bei_bedarf"
    )
    schnellknopf.schnellknoepfe_sicherstellen()
    alt.refresh_from_db()
    assert alt.schnellknopf_modus == SchnellknopfModus.JEDES


def test_idempotent_und_geloeschter_knopf_kommt_nicht_wieder(mama):
    schnellknopf.schnellknoepfe_sicherstellen()
    Aufgabe.objects.filter(titel="Rasen mähen").delete()
    assert schnellknopf.schnellknoepfe_sicherstellen() == 0
    assert not Aufgabe.objects.filter(titel="Rasen mähen").exists()


def test_inaktive_vorlage_wird_kein_knopf(mama):
    Vorlage.objects.filter(titel="Rasen mähen").update(aktiv=False)
    schnellknopf.schnellknoepfe_sicherstellen()
    assert not Aufgabe.objects.filter(titel="Rasen mähen").exists()


def test_ohne_eltern_nichts_dann_per_job_nachgeholt(db):
    assert schnellknopf.schnellknoepfe_sicherstellen() == 0
    assert not Aufgabe.objects.exists() and einstellungen.wert(MERKER) is False
    from apps.konten import services as konten

    konten.eltern_anlegen("Mama", rolle_label="mama")
    call_command("schnellknoepfe_sicherstellen")
    assert Aufgabe.objects.count() == 21


@pytest.mark.parametrize("titel", ["Zimmer gründlich", "zimmer saugen ", "Zimmer aufräumen"])
def test_modus_fuer_normalisiert(titel):
    assert knoepfe_start.modus_fuer(titel) == "jedes"
    assert knoepfe_start.modus_fuer("Altglas") == "einer"


# --- Datenmigration 0016 ----------------------------------------------------------------------


@pytest.fixture
def migration():
    return importlib.import_module("apps.aufgaben.migrations.0016_startwerte_bibliothek_knoepfe")


def test_migration_benennt_alte_vorlage_um_und_legt_knoepfe_an(db, mama, migration):
    Vorlage.objects.filter(titel="Zimmer gründlich reinigen und aufräumen").update(
        titel="Zimmer gründlich", punkte=30
    )
    Vorlage.objects.filter(titel="Zimmer saugen").delete()
    migration.umwandeln(django_apps, None)
    assert Vorlage.objects.get(titel="Zimmer gründlich reinigen und aufräumen").punkte == 50
    assert Vorlage.objects.filter(titel="Zimmer saugen").exists()
    assert Aufgabe.objects.filter(wiederholungsart="bei_bedarf").count() == 18  # ohne Start-Knöpfe
    assert modus_von("Zimmer saugen") == SchnellknopfModus.JEDES
    assert einstellungen.wert(MERKER) is True
    migration.umwandeln(django_apps, None)  # zweimal: kein Doppel
    assert Aufgabe.objects.filter(wiederholungsart="bei_bedarf").count() == 18


def test_migration_ohne_eltern_tut_nichts_an_aufgaben(db, migration):
    migration.umwandeln(django_apps, None)
    assert not Aufgabe.objects.exists() and einstellungen.wert(MERKER) is False
