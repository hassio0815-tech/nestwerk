"""lernen mit DB: Modelle, Startdaten (Datenmigration), Einstellungen, Services, Selektoren."""

import json
from collections import Counter

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.kern import einstellungen
from apps.lernen import selectors, services, startdaten
from apps.lernen.models import (
    Fach,
    Frage,
    Freigabe,
    Intensitaet,
    Lernmappe,
    Lernsitzung,
    Quelle,
    Thema,
)
from apps.lernen.speicher import Speicher

pytestmark = pytest.mark.django_db


def test_einstellungen_startwerte_aus_migration():
    assert einstellungen.wert("lernen.mindesttag_minuten") == 5
    assert einstellungen.wert("lernen.tagesziel_minuten") == 20
    assert einstellungen.wert("lernen.freigabe_durch_eltern") is True
    assert einstellungen.wert("lernen.tutor_aktiv") is False
    assert einstellungen.wert("lernen.speicher_limit_mb") > 0
    assert einstellungen.wert("lernen.lernpunkte_tageslimit") > 0


def test_einstellung_wird_validiert():
    with pytest.raises(Exception):  # noqa: B017 - ValidationError der Definition
        einstellungen.setzen("lernen.mindesttag_minuten", 0, akteur=None)


def test_startfaecher_und_themen():
    assert set(Fach.objects.values_list("schluessel", flat=True)) == {"englisch", "mathe"}
    for stufe in (3, 6, 8):
        assert Thema.objects.filter(fach__schluessel="englisch", klassenstufe=stufe).exists()
        assert Thema.objects.filter(fach__schluessel="mathe", klassenstufe=stufe).exists()
    assert not Frage.objects.filter(thema__fach__schluessel="mathe").exists()


def test_startvokabeln_sauber_und_freigegeben():
    daten = json.loads(startdaten.DATEI.read_text(encoding="utf-8"))
    erwartet = sum(len(k["vokabeln"]) for k in daten.values())
    assert Frage.objects.count() == erwartet
    for f in Frage.objects.all():
        assert f.frage.strip() and f.antwort.strip()
        assert (f.typ, f.quelle, f.freigabe, f.kind_id) == (
            "vokabel",
            Quelle.SYSTEM,
            Freigabe.FREIGEGEBEN,
            None,
        )
    # keine Doppelten je Thema
    zaehler = Counter(Frage.objects.values_list("thema_id", "frage", "antwort"))
    assert max(zaehler.values()) == 1


def test_startdaten_sind_idempotent():
    vorher = (Fach.objects.count(), Thema.objects.count(), Frage.objects.count())
    startdaten.anlegen(Fach, Thema, Frage)
    assert (Fach.objects.count(), Thema.objects.count(), Frage.objects.count()) == vorher


def test_bereinigte_eintraege_fehlen():
    de = set(Frage.objects.values_list("frage", flat=True))
    assert {"Mopeď", "Siemarin", "Brummipack", "Predator"}.isdisjoint(de)
    assert {"Moped", "Sieg"} <= de


def test_fach_und_themennamen_sind_markiert():
    # gettext_noop liefert den Text unverändert; Namen sind deutsch
    assert Fach.objects.get(schluessel="englisch").name == "Englisch"
    assert Fach.objects.get(schluessel="mathe").name == "Mathe"


def test_system_frage_ohne_kind_erzwungen(kind_a):
    thema = Thema.objects.filter(fach__schluessel="englisch").first()
    with pytest.raises(IntegrityError), transaction.atomic():
        Frage.objects.create(thema=thema, frage="x", antwort="y", quelle=Quelle.SYSTEM, kind=kind_a)


def test_lernmappe_eins_zu_eins_und_ordner(kind_a, tmp_path):
    speicher = Speicher(tmp_path)
    m1 = services.lernmappe_sicherstellen(kind_a, speicher)
    m2 = services.lernmappe_sicherstellen(kind_a, speicher)
    assert m1.pk == m2.pk
    assert Lernmappe.objects.filter(kind=kind_a).count() == 1
    for bereich in ("inbox", "archiv", "tests"):
        assert speicher.ordner(kind_a.pk, bereich).is_dir()
    with pytest.raises(IntegrityError), transaction.atomic():
        Lernmappe.objects.create(kind=kind_a)


def test_freigabe_folgt_einstellung(kind_a):
    thema = Thema.objects.filter(fach__schluessel="englisch").first()
    ki = services.frage_anlegen(thema, "frage", "F?", "A", quelle=Quelle.KI, kind=kind_a)
    assert ki.freigabe == Freigabe.OFFEN
    eltern = services.frage_anlegen(thema, "frage", "F2?", "A", quelle=Quelle.ELTERN, kind=kind_a)
    assert eltern.freigabe == Freigabe.FREIGEGEBEN
    einstellungen.setzen("lernen.freigabe_durch_eltern", False, akteur=None)
    sofort = services.frage_anlegen(thema, "frage", "F3?", "A", quelle=Quelle.KI, kind=kind_a)
    assert sofort.freigabe == Freigabe.FREIGEGEBEN
    with pytest.raises(ValueError):
        services.frage_anlegen(thema, "frage", "F4?", "A", quelle=Quelle.SYSTEM)


def test_geschwister_sehen_fragen_nicht(kind_a, kind_b):
    thema = Thema.objects.filter(fach__schluessel="englisch").first()
    eigene = services.frage_anlegen(
        thema, "frage", "Nur A?", "ja", quelle=Quelle.ELTERN, kind=kind_a
    )
    assert eigene in selectors.nutzbare_fragen(thema, kind_a)
    assert eigene not in selectors.nutzbare_fragen(thema, kind_b)
    ki = services.frage_anlegen(thema, "frage", "Offen?", "ja", quelle=Quelle.KI, kind=kind_a)
    assert ki not in selectors.nutzbare_fragen(thema, kind_a)
    assert list(selectors.offene_fragen(kind_a)) == [ki]
    assert list(selectors.offene_fragen(kind_b)) == []


def test_themen_nach_klassenstufe():
    englisch = Fach.objects.get(schluessel="englisch")
    assert selectors.themen(englisch, 3).count() == 5
    assert selectors.themen(englisch).count() == Thema.objects.filter(fach=englisch).count()


def test_leistungsstufe_je_kind_und_fach(kind_a):
    fach = Fach.objects.get(schluessel="mathe")
    services.leistungsstufe_setzen(kind_a, fach, "Grundniveau", 6)
    services.leistungsstufe_setzen(kind_a, fach, "Erweiterungsniveau", 6)
    assert selectors.leistungsstufe(kind_a, fach).stufe == "Erweiterungsniveau"
    assert kind_a.leistungsstufen.count() == 1


def test_lernsitzung_standardwerte(kind_a):
    s = Lernsitzung.objects.create(kind=kind_a, beginn=timezone.now())
    assert s.intensitaet == Intensitaet.NORMAL
    assert (s.hilfestufe_max, s.dauer_sekunden, s.versuche) == (0, 0, 0)
    assert s.selbsteinschaetzung == "" and s.rueckschau == ""


def test_start_namen_englisch_eltern_namen_bleiben():
    from django.utils import translation

    from apps.kern.sprache import uebersetzt

    with translation.override("en"):
        assert uebersetzt(Fach.objects.get(schluessel="mathe").name) == "Maths"
        namen = set(Thema.objects.values_list("name", flat=True))
        assert {uebersetzt(n) for n in namen} != namen
        assert uebersetzt("Mein eigenes Thema") == "Mein eigenes Thema"
