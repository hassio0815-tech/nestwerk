"""Einstellungen-Editor: jede Einstellung der Registry ist im Dashboard änderbar."""

import pytest
from django.urls import reverse

from apps.kern import einstellungen
from apps.kern.einstellungen import Typ, UngueltigerWert
from apps.kern.models import AuditEintrag, Einstellung
from apps.oberflaeche import einstellungen_editor as editor

DEFINITIONEN = editor.definitionen()
INTERN = [d for d in einstellungen.definitionen() if d.intern]


def anderer_wert(d, aktuell):
    """Ein gültiger, vom aktuellen verschiedener Wert (JSON-Form) oder ``None``."""
    kandidaten = []
    if d.auswahl:
        kandidaten = [[a] if d.typ is Typ.LISTE else a for a in d.auswahl]
    else:
        match d.typ:
            case Typ.GANZZAHL:
                kandidaten = [d.minimum, d.maximum, (aktuell or 0) + 1, (aktuell or 0) - 1]
            case Typ.BOOL:
                kandidaten = [not aktuell]
            case Typ.TEXT:
                kandidaten = ["Beispiel", "https://beispiel.example", "a@b.de"]
            case Typ.DATUM:
                kandidaten = ["2026-12-31", "2026-01-02"]
            case Typ.UHRZEIT:
                kandidaten = ["13:30", "06:45"]
            case Typ.ZEITZONE:
                kandidaten = ["UTC", "Europe/Berlin"]
            case Typ.LISTE:
                kandidaten = {
                    Typ.GANZZAHL: [[1], [2, 3]],
                    Typ.UHRZEIT: [["07:00"], ["08:30", "20:00"]],
                    Typ.TEXT: [["10.0.0.0/8"], ["192.168.0.0/16"], ["push.beispiel.example"]],
                }.get(d.element_typ, [[]])
    for kandidat in kandidaten:
        if kandidat is None or kandidat == aktuell:
            continue
        try:
            d.pruefen(kandidat)
        except UngueltigerWert:
            continue
        return kandidat
    return None


def post_daten(modul):
    """Formular wie der Browser: Werte aller Felder des Moduls aus der DB."""
    daten = {}
    for f in editor.felder(modul):
        if f["art"] == "bool":
            daten[f["name"]] = ["0", "1"] if f["text"] else ["0"]
        else:
            daten[f["name"]] = f["text"]
    return daten


def test_registry_ist_nicht_leer():
    assert len(DEFINITIONEN) > 20
    assert {"allgemein", "aufgaben", "belohnung", "konten", "oberflaeche"} <= {
        d.modul for d in DEFINITIONEN
    }


def test_seite_zeigt_jede_einstellung(eltern_client):
    html = eltern_client.get(reverse("oberflaeche:einstellungen")).content.decode()
    for d in DEFINITIONEN:
        assert f'name="{d.schluessel}"' in html, d.schluessel
    for modul in editor.module():
        assert f'id="modul-{modul}"' in html


@pytest.mark.parametrize("modul", editor.module())
def test_unveraenderte_formulare_speichern_fehlerfrei(eltern_client, modul):
    vorher = dict(Einstellung.objects.values_list("schluessel", "wert"))
    antwort = eltern_client.post(
        reverse("oberflaeche:einstellungen_speichern", args=[modul]), post_daten(modul)
    )
    assert antwort.status_code == 302, antwort.content.decode()[:500]
    assert dict(Einstellung.objects.values_list("schluessel", "wert")) == vorher
    assert not AuditEintrag.objects.filter(aktion="einstellung.geaendert").exists()


@pytest.mark.parametrize("d", DEFINITIONEN, ids=lambda d: d.schluessel)
def test_jede_einstellung_ist_aenderbar_mit_audit(eltern_client, mama, d):
    aktuell = Einstellung.objects.get(schluessel=d.schluessel).wert
    neu = anderer_wert(d, aktuell)
    if neu is None:
        assert d.auswahl and len(d.auswahl) == 1, f"{d.schluessel}: kein Alternativwert ableitbar"
        return  # einzige erlaubte Auswahl: nichts zu ändern (Rundlauf testet das Formular)
    daten = post_daten(d.modul)
    if d.typ is Typ.BOOL:
        daten[d.schluessel] = ["0", "1"] if neu else ["0"]
    elif d.typ is Typ.LISTE:
        daten[d.schluessel] = "\n".join(str(e) for e in neu)
    else:
        daten[d.schluessel] = str(neu)
    antwort = eltern_client.post(
        reverse("oberflaeche:einstellungen_speichern", args=[d.modul]), daten
    )
    assert antwort.status_code == 302, antwort.content.decode()[:800]
    assert Einstellung.objects.get(schluessel=d.schluessel).wert == neu
    eintrag = AuditEintrag.objects.get(aktion="einstellung.geaendert", objekt_id=d.schluessel)
    assert eintrag.akteur == mama and eintrag.details["neu"] == neu


def test_ungueltige_eingabe_speichert_nichts_und_meldet_fehler(eltern_client):
    modul = "oberflaeche"
    daten = post_daten(modul)
    daten["oberflaeche.tablet_aktualisierung_sekunden"] = "1"  # Minimum 5
    daten["oberflaeche.tablet_neuladen_stunden"] = "12"  # gültig, darf nicht gespeichert werden
    antwort = eltern_client.post(
        reverse("oberflaeche:einstellungen_speichern", args=[modul]), daten
    )
    assert antwort.status_code == 422
    assert "Minimum 5" in antwort.content.decode()
    assert einstellungen.wert("oberflaeche.tablet_neuladen_stunden") == 6
    assert einstellungen.wert("oberflaeche.tablet_aktualisierung_sekunden") == 10


def test_zahlfeld_mit_text_wird_abgewiesen(eltern_client):
    daten = post_daten("oberflaeche")
    daten["oberflaeche.tablet_aktualisierung_sekunden"] = "abc"
    antwort = eltern_client.post(
        reverse("oberflaeche:einstellungen_speichern", args=["oberflaeche"]), daten
    )
    assert antwort.status_code == 422 and "ganze Zahl" in antwort.content.decode()


def test_unbekanntes_modul_ist_404(eltern_client):
    url = reverse("oberflaeche:einstellungen_speichern", args=["gibtsnicht"])
    assert eltern_client.post(url, {}).status_code == 404


def test_neue_einstellung_erscheint_ohne_codeaenderung(eltern_client):
    with einstellungen.verzeichnis.isoliert():
        einstellungen.definieren("phase2.beispiel", Typ.GANZZAHL, "Beispiel", minimum=0, maximum=9)
        html = eltern_client.get(reverse("oberflaeche:einstellungen")).content.decode()
        assert 'name="phase2.beispiel"' in html and "Noch kein Wert gesetzt" in html
        antwort = eltern_client.post(
            reverse("oberflaeche:einstellungen_speichern", args=["phase2"]),
            {"phase2.beispiel": "4"},
        )
        assert antwort.status_code == 302
        assert einstellungen.wert("phase2.beispiel") == 4


def test_interne_einstellungen_sind_nicht_editierbar(eltern_client):
    """Regression B-08: ``allgemein.einrichtung_abgeschlossen`` war im Editor abschaltbar und
    öffnete damit den Einrichtungs-Assistenten (inkl. Passwort-Neusetzen) wieder."""
    assert {d.schluessel for d in INTERN} == {
        "allgemein.einrichtung_abgeschlossen",
        "einrichtung.schritt",
        "einrichtung.smtp_uebersprungen",
    }
    html = eltern_client.get(reverse("oberflaeche:einstellungen")).content.decode()
    for d in INTERN:
        assert f'name="{d.schluessel}"' not in html
    vorher = einstellungen.wert("allgemein.einrichtung_abgeschlossen")
    daten = post_daten("allgemein")
    daten["allgemein.einrichtung_abgeschlossen"] = ["0"]
    antwort = eltern_client.post(
        reverse("oberflaeche:einstellungen_speichern", args=["allgemein"]), daten
    )
    assert antwort.status_code == 302
    assert einstellungen.wert("allgemein.einrichtung_abgeschlossen") == vorher
