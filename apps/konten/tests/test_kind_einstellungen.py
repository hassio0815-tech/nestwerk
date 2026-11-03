"""Kind-Einstellungen im Dienst: Name, Spitzname, Code ändern (Sperre, Audit) und Mood-Katalog."""

import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied, ValidationError

from apps.kern.models import AuditEintrag
from apps.konten import moods, selectors, services
from apps.konten.models import MoodEigen, MoodVorschlag, VorschlagStatus

from .conftest import FALSCHE_PIN, PIN

NEUE_PIN = "2580"


# --- Name und Spitzname -------------------------------------------------------------------------


def test_name_und_spitzname_aendern(anna):
    services.kind_selbst_aendern(anna, "  Annabelle ", "  Anni  ")
    anna.refresh_from_db()
    assert (anna.anzeigename, anna.spitzname, anna.rufname) == ("Annabelle", "Anni", "Anni")
    eintrag = AuditEintrag.objects.get(aktion="konten.kind_profil_geaendert")
    assert eintrag.details["felder"] == ["anzeigename", "spitzname"]


def test_spitzname_ist_optional(anna):
    services.kind_selbst_aendern(anna, "Anna", "")
    anna.refresh_from_db()
    assert anna.spitzname == "" and anna.rufname == "Anna"
    assert not AuditEintrag.objects.filter(aktion="konten.kind_profil_geaendert").exists()


def test_name_ist_eindeutig_ohne_gross_klein(anna, ben):
    with pytest.raises(ValidationError):
        services.kind_selbst_aendern(anna, "BEN", "")
    with pytest.raises(ValidationError):
        services.kind_selbst_aendern(anna, "ben", "")
    anna.refresh_from_db()
    assert anna.anzeigename == "Anna"


def test_eigener_name_in_anderer_schreibweise_ist_erlaubt(anna):
    services.kind_selbst_aendern(anna, "ANNA", "")
    anna.refresh_from_db()
    assert anna.anzeigename == "ANNA"


def test_name_pflicht_und_laengen(anna):
    for name in ("", "   ", "x" * 41):
        with pytest.raises(ValidationError):
            services.kind_selbst_aendern(anna, name, "")
    with pytest.raises(ValidationError):
        services.kind_selbst_aendern(anna, "Anna", "x" * 21)


@pytest.mark.parametrize("spitzname", ["<b>Hi</b>", "Anni\x00", "a>b"])
def test_spitzname_ungueltige_zeichen(anna, spitzname):
    with pytest.raises(ValidationError):
        services.kind_selbst_aendern(anna, "Anna", spitzname)


# --- Code ändern --------------------------------------------------------------------------------


def test_code_aendern_mit_altem_code(anna):
    services.pin_aendern(anna, PIN, NEUE_PIN, neue_pin2=NEUE_PIN)
    assert authenticate(None, kind=anna, pin=NEUE_PIN) == anna
    assert authenticate(None, kind=anna, pin=PIN) is None
    eintrag = AuditEintrag.objects.get(aktion="konten.pin_geaendert")
    assert eintrag.kind == anna
    assert PIN not in str(eintrag.details) and NEUE_PIN not in str(eintrag.details)


@pytest.mark.parametrize("alt", [FALSCHE_PIN, "", "abcd"])
def test_falscher_alter_code_aendert_nichts(anna, alt):
    with pytest.raises(ValidationError):
        services.pin_aendern(anna, alt, NEUE_PIN, neue_pin2=NEUE_PIN)
    assert authenticate(None, kind=anna, pin=PIN) == anna
    assert AuditEintrag.objects.filter(aktion="konten.pin_aenderung_abgelehnt").exists()


@pytest.mark.parametrize("neu", ["12", "abcd", "12345", ""])
def test_neuer_code_muss_vier_ziffern_sein(anna, neu):
    with pytest.raises(ValidationError):
        services.pin_aendern(anna, PIN, neu, neue_pin2=neu)
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_neuer_code_zweimal_gleich(anna):
    with pytest.raises(ValidationError):
        services.pin_aendern(anna, PIN, NEUE_PIN, neue_pin2="9999")
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_fehlversuche_sperren_die_aenderung_und_die_anmeldung(anna, uhr):
    for _ in range(4):
        with pytest.raises(ValidationError):
            services.pin_aendern(anna, FALSCHE_PIN, NEUE_PIN, neue_pin2=NEUE_PIN)
    assert selectors.kind_gesperrt_bis(anna) is None
    with pytest.raises(services.PinGesperrt):  # der fünfte Fehlversuch sperrt
        services.pin_aendern(anna, FALSCHE_PIN, NEUE_PIN, neue_pin2=NEUE_PIN)
    assert selectors.kind_gesperrt_bis(anna) is not None
    # auch der richtige alte Code geht jetzt nicht, und die Anmeldung ist gesperrt
    with pytest.raises(services.PinGesperrt):
        services.pin_aendern(anna, PIN, NEUE_PIN, neue_pin2=NEUE_PIN)
    assert authenticate(None, kind=anna, pin=PIN) is None
    uhr.weiter(minutes=6)
    services.pin_aendern(anna, PIN, NEUE_PIN, neue_pin2=NEUE_PIN)
    assert authenticate(None, kind=anna, pin=NEUE_PIN) == anna


def test_erfolg_setzt_fehlversuche_zurueck(anna):
    for _ in range(3):
        with pytest.raises(ValidationError):
            services.pin_aendern(anna, FALSCHE_PIN, NEUE_PIN)
    services.pin_aendern(anna, PIN, NEUE_PIN)
    anna.kindprofil.refresh_from_db()
    assert anna.kindprofil.pin_fehlversuche == 0


def test_eltern_koennen_code_jederzeit_aendern(anna, mama):
    for _ in range(5):
        authenticate(None, kind=anna, pin=FALSCHE_PIN)
    services.pin_setzen(anna, NEUE_PIN, von=mama)  # auch während der Sperre, hebt sie auf
    assert authenticate(None, kind=anna, pin=NEUE_PIN) == anna
    assert AuditEintrag.objects.filter(aktion="konten.pin_zurueckgesetzt", kind=anna).exists()
    with pytest.raises(ValidationError):
        services.pin_setzen(anna, "12", von=mama)


# --- Mood-Katalog -------------------------------------------------------------------------------


def test_katalog_hat_50_moods_mit_emoji():
    assert len(moods.KATALOG) == 50
    assert len({m.schluessel for m in moods.KATALOG}) == 50
    assert len({str(m.text) for m in moods.KATALOG}) == 50
    gruppen = {k for k, _name in moods.GRUPPEN}
    for m in moods.KATALOG:
        assert m.emoji and str(m.text) and m.gruppe in gruppen
        assert len(str(m.text)) <= moods.TEXT_MAX
        assert len(m.schluessel) <= 20  # Benutzer.mood


def test_mood_setzen_und_loeschen(anna):
    services.mood_setzen(anna, "faultier")
    anna.refresh_from_db()
    assert selectors.mood_text(anna) == "🦥 Faultier-Modus"
    services.mood_setzen(anna, "")
    anna.refresh_from_db()
    assert selectors.mood_text(anna) == ""


def test_unbekannter_mood_wird_abgelehnt(anna):
    with pytest.raises(ValidationError):
        services.mood_setzen(anna, "gibt-es-nicht")
    with pytest.raises(ValidationError):
        services.mood_setzen(anna, "eigen-999")


def test_ausgeblendeter_mood_ist_nicht_waehlbar_und_wird_nicht_gezeigt(anna, mama):
    services.mood_setzen(anna, "pizza")
    services.mood_katalog_ausblenden("pizza", True, von=mama)
    anna.refresh_from_db()
    assert selectors.mood_text(anna) == ""
    with pytest.raises(ValidationError):
        services.mood_setzen(anna, "pizza")
    assert "pizza" not in {s for s, _t, _g in selectors.mood_auswahl()}
    services.mood_katalog_ausblenden("pizza", False, von=mama)
    assert selectors.mood_text(anna) == "🍕 Pizza-Power"


def test_eigener_mood_der_eltern(anna, ben, mama):
    eigen = services.mood_eigen_anlegen("Waffel-Laune", von=mama)
    services.mood_setzen(anna, eigen.schluessel)
    services.mood_setzen(ben, eigen.schluessel)  # gilt für alle Kinder
    assert selectors.mood_text(anna) == "⭐ Waffel-Laune"
    services.mood_eigen_entfernen(eigen, von=mama)
    anna.refresh_from_db()
    assert selectors.mood_text(anna) == ""
    with pytest.raises(ValidationError):
        services.mood_eigen_anlegen("pizza-power", von=mama)  # gibt es als Katalog-Mood
    with pytest.raises(ValidationError):
        services.mood_eigen_anlegen("", von=mama)


def test_kinder_duerfen_moods_nicht_verwalten(anna):
    with pytest.raises(PermissionDenied):
        services.mood_eigen_anlegen("Hack", von=anna)
    with pytest.raises(PermissionDenied):
        services.mood_katalog_ausblenden("pizza", True, von=anna)


# --- Vorschläge ---------------------------------------------------------------------------------


def test_vorschlag_anlegen_und_zulassen(anna, ben, mama):
    v = services.mood_vorschlagen(anna, "  Waffel   Laune ")
    assert v.text == "Waffel Laune" and v.status == VorschlagStatus.OFFEN
    assert selectors.mood_vorschlaege_offen_anzahl() == 1
    services.mood_vorschlag_entscheiden(v, True, von=mama)
    v.refresh_from_db()
    assert v.status == VorschlagStatus.ZUGELASSEN and v.entschieden_von == mama
    assert v.entschieden_am is not None
    eigen = MoodEigen.objects.get(text="Waffel Laune")
    services.mood_setzen(ben, eigen.schluessel)  # gilt für alle
    assert selectors.mood_text(ben) == "⭐ Waffel Laune"
    assert selectors.mood_vorschlaege_offen_anzahl() == 0


def test_vorschlag_ablehnen(anna, mama):
    v = services.mood_vorschlagen(anna, "Doofer Mood")
    services.mood_vorschlag_entscheiden(v, False, von=mama)
    v.refresh_from_db()
    assert v.status == VorschlagStatus.ABGELEHNT
    assert not MoodEigen.objects.exists()
    with pytest.raises(ValidationError):  # nur einmal entscheiden
        services.mood_vorschlag_entscheiden(v, True, von=mama)


def test_hoechstens_drei_offene_vorschlaege(anna, ben, mama):
    for text in ("Eins", "Zwei", "Drei"):
        services.mood_vorschlagen(anna, text)
    with pytest.raises(ValidationError):
        services.mood_vorschlagen(anna, "Vier")
    services.mood_vorschlagen(ben, "Vier")  # je Kind
    offen = MoodVorschlag.objects.filter(kind=anna).first()
    services.mood_vorschlag_entscheiden(offen, False, von=mama)
    services.mood_vorschlagen(anna, "Vier")  # wieder Platz


def test_vorschlag_pruefung(anna):
    for text in ("", "   ", "x" * 41, "<script>", "Pizza-Power", "pizza-power"):
        with pytest.raises(ValidationError):
            services.mood_vorschlagen(anna, text)
    services.mood_vorschlagen(anna, "Neu")
    with pytest.raises(ValidationError):
        services.mood_vorschlagen(anna, "neu")  # doppelt


def test_kinder_entscheiden_nicht(anna, ben):
    v = services.mood_vorschlagen(anna, "Neu")
    with pytest.raises(PermissionDenied):
        services.mood_vorschlag_entscheiden(v, True, von=ben)
    v.refresh_from_db()
    assert v.status == VorschlagStatus.OFFEN
