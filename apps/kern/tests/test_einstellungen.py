from datetime import date, time

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError

from apps.kern.einstellungen import (
    EinstellungFehlt,
    Typ,
    UnbekannteEinstellung,
    UngueltigerWert,
)
from apps.kern.models import AuditEintrag, Einstellung


@pytest.fixture
def e(einstellungs_verzeichnis):
    e = einstellungs_verzeichnis
    e.definieren("test.stunden", Typ.GANZZAHL, "Stunden", minimum=1, maximum=168)
    e.definieren("test.aktiv", Typ.BOOL, "Aktiv")
    e.definieren("test.modus", Typ.TEXT, "Modus", auswahl=("showcase", "held"))
    e.definieren("test.start", Typ.DATUM, "Start")
    e.definieren("test.von", Typ.UHRZEIT, "Von")
    e.definieren("test.zone", Typ.ZEITZONE, "Zone")
    e.definieren("test.arten", Typ.LISTE, "Arten", element_typ=Typ.TEXT, auswahl=("a", "b", "c"))
    return e


# --- Grundregel: kein Code-Default -----------------------------------------------------------


@pytest.mark.django_db
def test_einstellung_ohne_db_wert_wirft_klaren_fehler(e):
    with pytest.raises(EinstellungFehlt, match="test.stunden"):
        e.wert("test.stunden")


@pytest.mark.django_db
def test_werte_nennt_alle_fehlenden_schluessel(e):
    e.setzen("test.aktiv", True)
    with pytest.raises(EinstellungFehlt) as info:
        e.werte("test.stunden", "test.aktiv", "test.modus")
    assert "test.stunden" in str(info.value) and "test.modus" in str(info.value)
    assert "test.aktiv" not in str(info.value)


def test_definition_kennt_keinen_default(e):
    with pytest.raises(TypeError):
        e.definieren("test.mit_default", Typ.GANZZAHL, "x", default=5)


@pytest.mark.django_db
def test_unbekannte_einstellung(e):
    with pytest.raises(UnbekannteEinstellung):
        e.wert("test.gibt_es_nicht")
    with pytest.raises(UnbekannteEinstellung):
        e.setzen("test.gibt_es_nicht", 1)


@pytest.mark.django_db
def test_fehlende_listet_deklarierte_ohne_wert(e):
    e.setzen("test.stunden", 48)
    fehlend = e.fehlende()
    assert "test.stunden" not in fehlend
    assert {"test.aktiv", "test.modus", "allgemein.zeitzone"} <= set(fehlend)


# --- Lesen und Schreiben ---------------------------------------------------------------------


@pytest.mark.django_db
def test_setzen_und_lesen_typisiert(e):
    assert e.setzen("test.stunden", 48) == 48
    assert e.setzen("test.start", date(2026, 11, 1)) == date(2026, 11, 1)
    assert e.setzen("test.von", "07:30") == time(7, 30)
    assert e.setzen("test.arten", ("a", "c")) == ["a", "c"]
    assert e.wert("test.stunden") == 48
    assert e.wert("test.start") == date(2026, 11, 1)
    assert e.wert("test.von") == time(7, 30)
    assert e.werte("test.arten", "test.stunden") == {"test.arten": ["a", "c"], "test.stunden": 48}
    zeile = Einstellung.objects.get(schluessel="test.start")
    assert zeile.wert == "2026-11-01" and zeile.modul == "test"


@pytest.mark.django_db
def test_setzen_protokolliert_aenderung(e):
    e.setzen("test.stunden", 48)
    e.setzen("test.stunden", 48)  # unverändert -> kein zweiter Eintrag
    e.setzen("test.stunden", 24)
    eintraege = list(AuditEintrag.objects.filter(aktion="einstellung.geaendert").order_by("id"))
    assert [x.details for x in eintraege] == [{"alt": None, "neu": 48}, {"alt": 48, "neu": 24}]
    assert eintraege[0].objekt_id == "test.stunden" and eintraege[0].rolle == "system"


@pytest.mark.parametrize(
    ("schluessel", "wert"),
    [
        ("test.stunden", 0),
        ("test.stunden", 169),
        ("test.stunden", "48"),
        ("test.stunden", True),
        ("test.stunden", 4.5),
        ("test.aktiv", 1),
        ("test.aktiv", "ja"),
        ("test.modus", "rohpunkte"),
        ("test.modus", 3),
        ("test.start", "01.11.2026"),
        ("test.start", "2026-02-30"),
        ("test.von", "7:30"),
        ("test.von", "24:00"),
        ("test.von", time(7, 30, 15)),
        ("test.zone", "Europe/Bielefeld"),
        ("test.arten", "a"),
        ("test.arten", ["a", "x"]),
    ],
)
@pytest.mark.django_db
def test_validierung_lehnt_ab(e, schluessel, wert):
    with pytest.raises(UngueltigerWert):
        e.setzen(schluessel, wert)
    assert not Einstellung.objects.filter(schluessel=schluessel).exists()


@pytest.mark.django_db
def test_eigene_validatoren(einstellungs_verzeichnis):
    e = einstellungs_verzeichnis

    def gerade(wert):
        if wert % 2:
            raise ValidationError("muss gerade sein")

    e.definieren("test.gerade", Typ.GANZZAHL, "Gerade", validatoren=[gerade])
    assert e.setzen("test.gerade", 4) == 4
    with pytest.raises(UngueltigerWert, match="gerade"):
        e.setzen("test.gerade", 5)


@pytest.mark.django_db
def test_ungueltiger_db_wert_wird_beim_lesen_erkannt(e):
    Einstellung.objects.create(schluessel="test.stunden", wert="viele", modul="test")
    with pytest.raises(UngueltigerWert):
        e.wert("test.stunden")


# --- Deklaration -----------------------------------------------------------------------------


def test_doppelte_deklaration_ist_fehler(e):
    with pytest.raises(ImproperlyConfigured):
        e.definieren("test.stunden", Typ.GANZZAHL, "nochmal")


@pytest.mark.parametrize(
    "schluessel", ["ohnepunkt", "Test.gross", "test.", "a.b.c", "test.mit-strich"]
)
def test_ungueltiger_schluessel(einstellungs_verzeichnis, schluessel):
    with pytest.raises(ImproperlyConfigured):
        einstellungs_verzeichnis.definieren(schluessel, Typ.BOOL, "x")


def test_liste_braucht_element_typ(einstellungs_verzeichnis):
    with pytest.raises(ImproperlyConfigured):
        einstellungs_verzeichnis.definieren("test.liste", Typ.LISTE, "x")
    with pytest.raises(ImproperlyConfigured):
        einstellungs_verzeichnis.definieren("test.zahl", Typ.GANZZAHL, "x", element_typ=Typ.TEXT)


def test_kern_deklariert_allgemein(e):
    schluessel = [d.schluessel for d in e.definitionen("allgemein")]
    assert schluessel == [
        "allgemein.anzeigename",
        "allgemein.einrichtung_abgeschlossen",
        "allgemein.go_live_datum",
        "allgemein.joblauf_aufbewahrung_tage",
        "allgemein.sprache",
        "allgemein.zeitzone",
    ]


# --- Startwerte für Datenmigrationen ---------------------------------------------------------


@pytest.mark.django_db
def test_startwerte_ueberschreiben_nie(e):
    e.setzen("test.stunden", 24)
    e.startwerte_schreiben(Einstellung, {"test.stunden": 48, "test.aktiv": True})
    assert e.wert("test.stunden") == 24
    assert e.wert("test.aktiv") is True


@pytest.mark.django_db
def test_startwerte_werden_validiert(e):
    with pytest.raises(UngueltigerWert):
        e.startwerte_schreiben(Einstellung, {"test.stunden": 0})
    with pytest.raises(UnbekannteEinstellung):
        e.startwerte_schreiben(Einstellung, {"test.unbekannt": 1})


@pytest.mark.django_db
def test_langer_schluessel_wird_protokolliert(einstellungs_verzeichnis):
    """Regression: AuditEintrag.objekt_id war auf 40 Zeichen begrenzt (Schlüssel bis 100)."""
    schluessel = "test." + "s" * 95
    einstellungs_verzeichnis.definieren(schluessel, Typ.GANZZAHL, "Lang", minimum=0)
    einstellungs_verzeichnis.setzen(schluessel, 7, akteur=None)
    eintrag = AuditEintrag.objects.get(aktion="einstellung.geaendert", objekt_id=schluessel)
    assert len(eintrag.objekt_id) == 100
