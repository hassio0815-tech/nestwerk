"""Nie Klartext (DB, Audit), Audit mit Akteur, Insert-only-Trigger nach den FK-Migrationen."""

import json

import pytest
from django.core import serializers
from django.db import DatabaseError, connection, transaction

from apps.kern import audit, einstellungen
from apps.kern.db import NurEinfuegenFehler
from apps.kern.models import AuditEintrag, Einstellung
from apps.konten import services
from apps.konten.models import (
    AnmeldeVersuch,
    Benutzer,
    ElternProfil,
    ElternZugang,
    Geraet,
    KindProfil,
)

from .conftest import FALSCHE_PIN, PASSWORT, PIN, eltern_anmelden, kind_anmelden

pytestmark = pytest.mark.django_db


def alles_serialisiert():
    teile = []
    for modell in (Benutzer, KindProfil, ElternProfil, ElternZugang, Geraet, AnmeldeVersuch,
                   AuditEintrag, Einstellung):  # fmt: skip
        teile.append(serializers.serialize("json", modell.objects.all()))
    return "\n".join(teile)


def test_pin_und_passwort_sind_argon2_gehasht(anna, mama):
    assert KindProfil.objects.get(benutzer=anna).pin_hash.startswith("argon2$")
    assert ElternZugang.objects.get().passwort_hash.startswith("argon2$")
    assert PIN not in KindProfil.objects.get(benutzer=anna).pin_hash
    assert PASSWORT not in ElternZugang.objects.get().passwort_hash


def test_benutzer_haben_kein_eigenes_passwort(anna, mama):
    assert not anna.has_usable_password() and not mama.has_usable_password()


def test_weder_pin_noch_passwort_stehen_im_klartext_in_der_db(anna, mama, tablet, client, uhr):
    for pin in (FALSCHE_PIN, PIN):
        kind_anmelden(client, anna, pin)
    client.post("/abmelden/")
    eltern_anmelden(client, mama, "Falsches-Passwort-99")
    eltern_anmelden(client, mama)
    services.pin_setzen(anna, "2468", von=mama)
    services.eltern_passwort_setzen("Neues-Passwort-4711", von=mama)
    dump = alles_serialisiert()
    for geheimnis in (PASSWORT, "Falsches-Passwort-99", "Neues-Passwort-4711"):
        assert geheimnis not in dump
    # PINs: Audit-Felder und Anmeldeversuche enthalten sie nicht (Hash-Felder ausgenommen)
    for eintrag in AuditEintrag.objects.all():
        text = json.dumps(
            [
                eintrag.akteur_name,
                eintrag.aktion,
                eintrag.objekt_typ,
                eintrag.objekt_id,
                eintrag.details,
            ]  # fmt: skip
        )
        for pin in (PIN, FALSCHE_PIN, "2468"):
            assert pin not in text


def test_audit_lehnt_pin_und_passwort_in_details_ab(mama):
    for schluessel in ("pin", "passwort", "neue_pin", "passwort_hash"):
        with pytest.raises(audit.SensiblerInhalt):
            audit.protokollieren("konten.test", akteur=mama, details={schluessel: "x"})


def test_passwortaenderung_und_pin_reset_stehen_im_audit_ohne_geheimnis(anna, mama):
    services.pin_setzen(anna, "2468", von=mama)
    services.eltern_passwort_setzen("Neues-Passwort-4711", von=mama)
    pin = AuditEintrag.objects.get(aktion="konten.pin_zurueckgesetzt")
    pw = AuditEintrag.objects.filter(aktion="konten.passwort_geaendert").latest("pk")
    assert (pin.akteur, pin.kind, pin.details) == (mama, anna, {})
    assert (pw.akteur, pw.details) == (mama, {})
    assert ElternZugang.objects.get().geaendert_von == mama


def test_ungueltige_pin_und_kurzes_passwort_werden_abgelehnt(anna, mama):
    from django.core.exceptions import ValidationError

    for schlecht in ("123", "12345", "abcd"):
        with pytest.raises(ValidationError):
            services.pin_setzen(anna, schlecht, von=mama)
        with pytest.raises(ValidationError):
            services.kind_anlegen("Neu", schlecht)
    with pytest.raises(ValidationError):
        services.eltern_passwort_setzen("kurz", von=mama)


def test_akzentfarben_werden_validiert(anna, mama):
    from django.core.exceptions import ValidationError

    services.akzentfarben_setzen(anna, ["#22c55e"], von=mama)
    anna.refresh_from_db()
    assert anna.akzentfarben == ["#22c55e"]
    for schlecht in (["rot"], ["#12"], "#22c55e", ["#22c55e"] * 4, [1]):
        with pytest.raises(ValidationError):
            services.akzentfarben_setzen(anna, schlecht, von=mama)


def test_anzeigename_ist_ohne_gross_kleinschreibung_eindeutig(anna):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        services.kind_anlegen("ANNA", PIN)


def test_eltern_aktionen_werden_dem_angemeldeten_elternteil_zugeordnet(mama, papa, tablet, client):
    eltern_anmelden(client, papa)
    client.post("/eltern/geraete/", {"bezeichnung": "Papas Laptop", "typ": "persoenlich"})
    eintrag = AuditEintrag.objects.get(
        aktion="konten.geraet_registriert", details__bezeichnung="Papas Laptop"
    )
    assert (eintrag.akteur, eintrag.akteur_name, eintrag.rolle) == (papa, "Papa", "eltern")


# --- kern: Akteur aus dem Kontext, FKs, Trigger ---------------------------------------------


def test_protokollieren_nutzt_den_angemeldeten_akteur(mama, tablet):
    with audit.kontext(lambda: (mama, tablet)):
        e = audit.protokollieren("test.aktion")
    assert (e.akteur, e.akteur_name, e.rolle, e.geraet) == (mama, "Mama", "eltern", tablet)


def test_explizit_none_bleibt_system_auch_im_kontext(mama):
    with audit.kontext(lambda: (mama, None)):
        e = audit.protokollieren("test.aktion", akteur=None)
    assert (e.akteur, e.rolle, e.akteur_name) == (None, "system", "System")


def test_ohne_kontext_ist_der_akteur_das_system(db):
    e = audit.protokollieren("test.aktion")
    assert (e.akteur, e.rolle, e.geraet) == (None, "system", None)


def test_einstellung_setzen_merkt_sich_den_akteur(mama):
    with audit.kontext(lambda: (mama, None)):
        einstellungen.setzen("konten.kiosk_leerlauf_sekunden", 120)
    assert (
        Einstellung.objects.get(schluessel="konten.kiosk_leerlauf_sekunden").geaendert_von == mama
    )
    e = AuditEintrag.objects.get(aktion="einstellung.geaendert")
    assert (e.akteur, e.details) == (mama, {"alt": 300, "neu": 120})


def test_kind_feld_im_audit(anna, mama):
    e = audit.protokollieren("test.aktion", akteur=mama, kind=anna)
    assert e.kind == anna


def test_audit_trigger_greifen_nach_der_fk_migration(mama):
    e = audit.protokollieren("test.aktion", akteur=mama)
    with pytest.raises(DatabaseError, match="insert-only"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("UPDATE kern_auditeintrag SET aktion = 'x.y' WHERE id = %s", [e.pk])
    with pytest.raises(DatabaseError, match="insert-only"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("UPDATE kern_auditeintrag SET akteur_id = NULL WHERE id = %s", [e.pk])
    with pytest.raises(DatabaseError, match="insert-only"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM kern_auditeintrag WHERE id = %s", [e.pk])
    with pytest.raises(NurEinfuegenFehler):
        AuditEintrag.objects.filter(pk=e.pk).update(aktion="x.y")


def test_trigger_existieren_in_der_schemaebene(db):
    with connection.cursor() as cur:
        cur.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        namen = {z[0] for z in cur.fetchall()}
    assert {"kern_auditeintrag_kein_update", "kern_auditeintrag_kein_delete"} <= namen


def test_audit_spalten_existieren_und_sind_nullable(db):
    with connection.cursor() as cur:
        cur.execute("PRAGMA table_info(kern_auditeintrag)")
        spalten = {z[1]: z[3] for z in cur.fetchall()}  # name -> notnull
        cur.execute("PRAGMA table_info(kern_einstellung)")
        einstellung = {z[1]: z[3] for z in cur.fetchall()}
    for name in ("akteur_id", "kind_id", "geraet_id"):
        assert spalten[name] == 0
    assert einstellung["geaendert_von_id"] == 0


def test_geraete_koennen_nicht_geloescht_werden_wenn_audit_darauf_zeigt(mama, tablet):
    audit.protokollieren("test.aktion", akteur=mama, geraet=tablet)
    with pytest.raises(DatabaseError, match="insert-only"):
        tablet.delete()  # SET_NULL würde das Audit ändern -> Trigger bricht ab
