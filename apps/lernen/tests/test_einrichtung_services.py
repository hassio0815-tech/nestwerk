"""Services und Prüfungen der Lernen-Schritte im Assistenten (ohne Weboberfläche, ohne Netz)."""

import pytest
from django.core.exceptions import ValidationError

from apps.kern import einstellungen, registry
from apps.kern.models import AuditEintrag
from apps.lernen import einrichtung_services as dienste
from apps.lernen import speicher
from apps.lernen.models import Fach, KiAnbieter, KiZuordnung, Leistungsstufe, Lernmappe

SCHLUESSEL = "sk-test-geheim-0123456789"  # erfunden


# --- Grundwerte ----------------------------------------------------------------------------------


def test_grundwerte_ausserhalb_der_grenzen_ist_validierungsfehler(db):
    with pytest.raises(ValidationError):
        dienste.grundwerte_speichern(faecher=["mathe"], tagesziel=0, lernpunkte=True, tutor=False)
    assert einstellungen.wert("lernen.tagesziel_minuten") == 20
    assert Fach.objects.filter(aktiv=True).count() == 2  # Rollback: nichts halb gespeichert


def test_grundwerte_idempotent_mit_audit_ohne_privates(db):
    for _ in range(2):
        dienste.grundwerte_speichern(faecher=["mathe"], tagesziel=30, lernpunkte=False, tutor=True)
    stand = dienste.grundwerte()
    assert stand["tagesziel"] == 30 and stand["tutor"] is True and stand["lernpunkte"] is False
    assert [f.schluessel for f, an in stand["faecher"] if an] == ["mathe"]
    eintrag = AuditEintrag.objects.filter(aktion="lernen.einrichtung_grundwerte").first()
    assert eintrag.details == {"faecher": 1, "lernpunkte": False, "tutor": True}


# --- Speicher ------------------------------------------------------------------------------------


def test_pfad_pruefen_ok_und_aufgeloest(tmp_path):
    (tmp_path / "ziel").mkdir()
    assert speicher.pfad_pruefen(f"  {tmp_path}/ziel ") == (tmp_path / "ziel").resolve()
    assert list((tmp_path / "ziel").iterdir()) == []


@pytest.mark.parametrize("pfad", [None, "", "  ", "a\x00b", "/tmp/a\nb", "/" + "x" * 400])
def test_pfad_pruefen_ungueltig(pfad):
    with pytest.raises(speicher.PfadFehler):
        speicher.pfad_pruefen(pfad)


def test_pfad_fehler_ist_value_error_und_speicher_fehler():
    assert issubclass(speicher.PfadFehler, ValueError)
    assert issubclass(speicher.PfadFehler, speicher.SpeicherFehler)


def test_speicher_pfad_als_einstellung_pruefen_bei_jeder_aenderung(db, tmp_path):
    with pytest.raises(einstellungen.EinstellungFehler):
        einstellungen.setzen("lernen.speicher_pfad", "/etc", akteur=None)
    einstellungen.setzen("lernen.speicher_pfad", str(tmp_path), akteur=None)
    einstellungen.setzen("lernen.speicher_pfad", "", akteur=None)  # leer = Standard


def test_speicher_nutzt_gewaehlten_pfad_sonst_standard(db, tmp_path, settings):
    settings.LERNEN_SPEICHER_DIR = tmp_path / "standard"
    assert speicher.Speicher().basis == (tmp_path / "standard").resolve()
    (tmp_path / "nas").mkdir()
    dienste.speicher_speichern(modus="pfad", pfad=str(tmp_path / "nas"))
    assert speicher.Speicher().basis == (tmp_path / "nas").resolve()
    assert speicher.Speicher(tmp_path / "x").basis == (tmp_path / "x").resolve()
    dienste.speicher_speichern(modus="volume")
    assert speicher.Speicher().basis == (tmp_path / "standard").resolve()


def test_konfigurierter_pfad_ohne_wert_ist_leer(db):
    from apps.kern.models import Einstellung

    Einstellung.objects.filter(schluessel="lernen.speicher_pfad").delete()
    assert speicher.konfigurierter_pfad() == ""


# --- Kinder --------------------------------------------------------------------------------------


def test_kind_speichern_nur_fuer_kinder(db, mama):
    with pytest.raises(ValidationError):
        dienste.kind_speichern(mama, klassenstufe="5", schulform="", stufen={}, sofort=False)
    assert not Lernmappe.objects.exists()


def test_kind_pruefen_bereinigt_leerzeichen():
    klasse, form, stufen = dienste.kind_pruefen(
        klassenstufe=" 7 ", schulform="  Beispiel   Schule ", stufen={"mathe": "", "englisch": None}
    )
    assert (klasse, form, stufen) == (7, "Beispiel Schule", {"mathe": "", "englisch": ""})
    assert dienste.kind_pruefen(klassenstufe=None, schulform=None, stufen={})[0] is None


def test_kind_speichern_idempotent_und_profile(db, kind_a):
    for _ in range(2):
        dienste.kind_speichern(
            kind_a,
            klassenstufe="5",
            schulform="Beispielschule",
            stufen={"mathe": "Grundniveau", "englisch": ""},
            sofort=True,
        )
    assert Lernmappe.objects.filter(kind=kind_a).count() == 1
    assert Leistungsstufe.objects.filter(kind=kind_a).count() == 2
    (profil,) = [p for p in dienste.kinder_profile() if p.kind == kind_a]
    assert profil.klassenstufe == 5 and profil.schulform == "Beispielschule" and profil.sofort
    assert profil.stufen == {"mathe": "Grundniveau", "englisch": ""}
    audit = AuditEintrag.objects.filter(aktion="lernen.einrichtung_kind").first()
    assert "Beispielschule" not in str(audit.details)  # keine Schulangaben im Audit


# --- KI ------------------------------------------------------------------------------------------


def test_ki_abschalten_ohne_anbieter_ist_leerlauf(db):
    dienste.ki_abschalten()
    assert dienste.ki_einrichten(modus="keine").anbieter is None


def test_ki_einrichten_lokal_test_und_werte(db, transport):
    erg = dienste.ki_einrichten(
        modus="openai_kompatibel",
        name="Lokal",
        basis_url="http://dein-ki-server:11434/v1",
        modell="dein-modellname",
        api_key=SCHLUESSEL,
        aufgaben=["bewerten", "unbekannt"],
        testen=True,
    )
    assert erg.test.ok and erg.test_text
    werte = dienste.ki_werte()
    assert werte["modus"] == "openai_kompatibel" and werte["aufgaben"] == ["bewerten"]
    assert werte["hat_schluessel"] and SCHLUESSEL not in str(werte)
    assert KiAnbieter.objects.get().aktiv
    text = dienste.zusammenfassung()
    assert any("Lokal" in t for _l, t in text["zeilen"])
    assert SCHLUESSEL not in str(text)


def test_ki_cloud_ohne_einwilligung_rollback(db, transport):
    with pytest.raises(ValidationError):
        dienste.ki_einrichten(
            modus="openai", name="Cloud", modell="m", api_key=SCHLUESSEL, aufgaben=["tutor"]
        )
    assert not KiAnbieter.objects.exists() and not KiZuordnung.objects.exists()
    assert transport.aufrufe == []


def test_ki_werte_ohne_anbieter_tutor_vorbelegt(db):
    assert dienste.ki_werte()["aufgaben"] == ["auslesen", "fragen_erzeugen", "bewerten"]
    einstellungen.setzen("lernen.tutor_aktiv", True, akteur=None)
    assert dienste.ki_werte()["aufgaben"][-1] == "tutor"


def test_zusammenfassung_ohne_alles_und_links(db, kind_a):
    z = dienste.zusammenfassung()
    zeilen = dict(z["zeilen"])
    assert zeilen["Tutor"] == "aus" and zeilen["Speicherort"].startswith("Docker-Volume")
    assert "aus (keine KI" in zeilen["KI"]
    assert [adresse for _t, adresse in z["spaeter"]] == [
        "/eltern/lernen/ki/",
        "/eltern/lernen/tutor/",
        "/eltern/lernen/material/",
        "/eltern/lernen/",
    ]
    assert zeilen[kind_a.anzeigename] == "Eltern geben frei"


# --- Registry ------------------------------------------------------------------------------------


def test_registry_schritte_sortiert_und_doppelt_ist_fehler():
    schritte = registry.einrichtungsschritte()
    assert [s.reihenfolge for s in schritte] == sorted(s.reihenfolge for s in schritte)
    assert all(s.modul == "lernen" for s in schritte)
    with pytest.raises(Exception, match="doppelt"):
        registry.einrichtung_registrieren(schritte[0])
    with registry.isoliert():
        assert registry.einrichtungsschritte() == []
    assert len(registry.einrichtungsschritte()) == 4  # nach isoliert() wiederhergestellt
