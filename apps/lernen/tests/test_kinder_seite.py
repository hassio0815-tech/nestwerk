"""Eltern-Seite "Kinder und Leistungsstufen" und "Neues Schuljahr" (Etappe 9)."""

import uuid

import pytest
from django.urls import reverse

from apps.kern.models import AuditEintrag
from apps.lernen import einrichtung_services as dienste
from apps.lernen.models import Fach, Leistungsstufe, Lernmappe, Lernstand


def _anlegen(kind, klasse, stufe="", faecher=("mathe", "englisch")):
    for s in faecher:
        Leistungsstufe.objects.create(
            kind=kind, fach=Fach.objects.get(schluessel=s), stufe=stufe, klassenstufe=klasse
        )


def _klassen(kind):
    return sorted(
        set(Leistungsstufe.objects.filter(kind=kind).values_list("klassenstufe", flat=True)),
        key=lambda k: (k is None, k),
    )


def _profil(kind):
    return next(p for p in dienste.kinder_profile() if p.kind == kind)


def test_seite_zeigt_kinder_und_ist_verlinkt(eltern_client, kind_a, kind_b):
    html = eltern_client.get(reverse("lernen:eltern_kinder")).content.decode()
    assert "Testkind A" in html and "Testkind B" in html
    start = eltern_client.get(reverse("lernen:eltern")).content.decode()
    assert reverse("lernen:eltern_kinder") in start


def test_aendern_speichert_alle_werte(eltern_client, kind_a):
    url = reverse("lernen:eltern_kind_speichern", args=[kind_a.pk])
    antwort = eltern_client.post(
        url,
        {
            "klasse": "6",
            "schulform": "  Beispielschule  ",
            "stufe-mathe": "Grundniveau",
            "stufe-englisch": "",
            "freigabe": "sofort",
        },
    )
    assert antwort.status_code == 200
    p = _profil(kind_a)
    assert p.klassenstufe == 6 and p.schulform == "Beispielschule" and p.sofort
    assert p.stufen["mathe"] == "Grundniveau"
    # erneut ändern (Wert korrigieren)
    eltern_client.post(url, {"klasse": "7", "freigabe": "eltern"})
    p = _profil(kind_a)
    assert p.klassenstufe == 7 and not p.sofort


def test_htmx_liefert_nur_die_liste(eltern_client, kind_a):
    url = reverse("lernen:eltern_kind_speichern", args=[kind_a.pk])
    html = eltern_client.post(url, {"klasse": "5"}, headers={"HX-Request": "true"}).content.decode()
    assert 'id="kinder-liste"' in html and "<html" not in html and "Gespeichert." in html


@pytest.mark.parametrize("klasse", ["0", "14", "abc", "-1"])
def test_ungueltige_klasse_wird_abgelehnt(eltern_client, kind_a, klasse):
    _anlegen(kind_a, 5)
    url = reverse("lernen:eltern_kind_speichern", args=[kind_a.pk])
    assert eltern_client.post(url, {"klasse": klasse}).status_code == 400
    assert _klassen(kind_a) == [5]


def test_unbekannte_stufe_wird_abgelehnt(eltern_client, kind_a):
    url = reverse("lernen:eltern_kind_speichern", args=[kind_a.pk])
    assert eltern_client.post(url, {"stufe-mathe": "Gott"}).status_code == 400
    assert not Leistungsstufe.objects.filter(kind=kind_a).exists()


def test_aenderung_wird_im_audit_protokolliert(eltern_client, kind_a, mama):
    url = reverse("lernen:eltern_kind_speichern", args=[kind_a.pk])
    eltern_client.post(url, {"klasse": "5", "schulform": "Beispielschule"})
    e = AuditEintrag.objects.get(aktion="lernen.kind_geaendert")
    assert e.akteur == mama and e.kind == kind_a
    assert "Beispielschule" not in str(e.details)


def test_geschwister_bleiben_unberuehrt(eltern_client, kind_a, kind_b):
    _anlegen(kind_b, 8, "Grundniveau")
    Lernmappe.objects.create(kind=kind_b, schulform="Eigene")
    eltern_client.post(
        reverse("lernen:eltern_kind_speichern", args=[kind_a.pk]),
        {"klasse": "3", "schulform": "X", "stufe-mathe": "Grundniveau", "freigabe": "sofort"},
    )
    p = _profil(kind_b)
    assert p.klassenstufe == 8 and p.schulform == "Eigene" and not p.sofort
    assert _profil(kind_a).klassenstufe == 3


def test_unbekanntes_oder_inaktives_kind_ist_404(eltern_client, kind_a):
    assert (
        eltern_client.post(
            reverse("lernen:eltern_kind_speichern", args=[uuid.uuid4()]), {}
        ).status_code
        == 404
    )
    kind_a.aktiv = False
    kind_a.save()
    url = reverse("lernen:eltern_kind_speichern", args=[kind_a.pk])
    assert eltern_client.post(url, {"klasse": "4"}).status_code == 404


def test_eltern_koennen_nicht_ueber_den_pk_ein_elternkonto_aendern(eltern_client, mama):
    url = reverse("lernen:eltern_kind_speichern", args=[mama.pk])
    assert eltern_client.post(url, {"klasse": "4"}).status_code == 404


NAMEN = [
    ("eltern_kinder", [], "get"),
    ("eltern_kind_speichern", [uuid.uuid4()], "post"),
    ("eltern_schuljahr", [], "get"),
    ("eltern_schuljahr_bestaetigen", [], "post"),
]


@pytest.mark.parametrize(("name", "args", "methode"), NAMEN)
def test_kind_darf_die_seiten_nicht_nutzen(kind_client, kind_a, name, args, methode):
    _anlegen(kind_a, 5)
    url = reverse(f"lernen:{name}", args=args)
    antwort = getattr(kind_client, methode)(url, {"klasse": "9", "bestaetigt": "1"})
    assert antwort.status_code == 403
    assert _klassen(kind_a) == [5]


@pytest.mark.parametrize(("name", "args", "methode"), NAMEN)
def test_ohne_anmeldung_keine_seite(client, kind_a, name, args, methode):
    _anlegen(kind_a, 5)
    antwort = getattr(client, methode)(reverse(f"lernen:{name}", args=args), {"bestaetigt": "1"})
    assert antwort.status_code in (302, 401, 403)
    assert _klassen(kind_a) == [5]


# --- Neues Schuljahr -----------------------------------------------------------------------------


def test_schuljahr_hebt_alle_klassenstufen_um_eins(eltern_client, kind_a, kind_b):
    _anlegen(kind_a, 5, "Grundniveau")
    _anlegen(kind_b, 9)
    antwort = eltern_client.post(
        reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"}
    )
    assert antwort.status_code == 200
    assert _klassen(kind_a) == [6] and _klassen(kind_b) == [10]
    assert _profil(kind_a).stufen["mathe"] == "Grundniveau"  # Stufe bleibt


def test_schuljahr_ohne_bestaetigung_aendert_nichts(eltern_client, kind_a):
    _anlegen(kind_a, 5)
    url = reverse("lernen:eltern_schuljahr_bestaetigen")
    assert eltern_client.post(url).status_code == 400
    assert eltern_client.post(url, {"bestaetigt": "0"}).status_code == 400
    assert _klassen(kind_a) == [5]
    assert not AuditEintrag.objects.filter(aktion="lernen.schuljahr_wechsel").exists()


def test_schuljahr_get_zeigt_bestaetigung_und_aendert_nichts(eltern_client, kind_a):
    _anlegen(kind_a, 13)
    html = eltern_client.get(reverse("lernen:eltern_schuljahr")).content.decode()
    assert reverse("lernen:eltern_schuljahr_bestaetigen") in html
    assert _klassen(kind_a) == [13]


def test_schuljahr_obergrenze_13_bleibt(eltern_client, kind_a, kind_b):
    _anlegen(kind_a, 13)
    _anlegen(kind_b, 12)
    eltern_client.post(reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"})
    assert _klassen(kind_a) == [13] and _klassen(kind_b) == [13]
    eltern_client.post(reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"})
    assert _klassen(kind_b) == [13]  # nie über 13


def test_schuljahr_ohne_klassenstufe_und_ohne_kinder(db, kind_a):
    assert dienste.schuljahr_wechsel() == (0, 0)  # nichts eingetragen
    _anlegen(kind_a, None, "Grundniveau")
    assert dienste.schuljahr_wechsel() == (0, 0)
    assert _klassen(kind_a) == [None]


def test_schuljahr_loescht_keinen_lernstand_und_keine_mappe(eltern_client, kind_a):
    _anlegen(kind_a, 5, "Grundniveau")
    Lernmappe.objects.create(kind=kind_a, schulform="Beispielschule")
    from datetime import date

    from apps.lernen.models import Frage

    frage = Frage.objects.first()
    assert frage is not None  # Startdaten liefern Fragen
    Lernstand.objects.create(
        kind=kind_a, frage=frage, richtung="vor", box=2, faellig_am=date(2026, 11, 3)
    )
    vorher = (Lernstand.objects.count(), Leistungsstufe.objects.count())
    eltern_client.post(reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"})
    assert (Lernstand.objects.count(), Leistungsstufe.objects.count()) == vorher
    assert Lernmappe.objects.get(kind=kind_a).schulform == "Beispielschule"


def test_schuljahr_inaktive_kinder_bleiben(eltern_client, kind_a, kind_b):
    _anlegen(kind_a, 5)
    _anlegen(kind_b, 5)
    kind_b.aktiv = False
    kind_b.save()
    eltern_client.post(reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"})
    assert _klassen(kind_a) == [6] and _klassen(kind_b) == [5]


def test_schuljahr_audit_mit_zahlen_ohne_namen(eltern_client, kind_a, mama):
    _anlegen(kind_a, 13, faecher=("mathe",))
    _anlegen(kind_a, 5, faecher=("englisch",))
    eltern_client.post(reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"})
    e = AuditEintrag.objects.get(aktion="lernen.schuljahr_wechsel")
    assert e.akteur == mama
    assert e.details == {"angehoben": 1, "unveraendert": 1}


def test_schuljahr_vorschau_zaehlt_je_kind(db, kind_a, kind_b):
    _anlegen(kind_a, 13)
    _anlegen(kind_b, 7)
    assert dienste.schuljahr_vorschau() == (2, 1, 1)


def test_schuljahr_meldung_zaehlt_kinder_nicht_eintraege(eltern_client, kind_a):
    _anlegen(kind_a, 5)  # zwei Fächer, aber ein Kind
    antwort = eltern_client.post(
        reverse("lernen:eltern_schuljahr_bestaetigen"), {"bestaetigt": "1"}
    )
    assert "bei 1 Kind angehoben" in antwort.content.decode()
