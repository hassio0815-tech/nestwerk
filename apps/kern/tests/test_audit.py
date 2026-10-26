from types import SimpleNamespace

import pytest
from django.db import DatabaseError, connection, transaction

from apps.kern import audit
from apps.kern.db import NurEinfuegenFehler, wartung
from apps.kern.models import AuditEintrag, JobSperre

pytestmark = pytest.mark.django_db


@pytest.fixture
def eintrag():
    return audit.protokollieren("test.angelegt", details={"punkte": 5})


def test_system_eintrag(eintrag):
    assert eintrag.pk is not None
    assert (eintrag.rolle, eintrag.akteur_name) == ("system", "System")
    assert eintrag.details == {"punkte": 5}
    assert eintrag.zeit is not None


def test_akteur_und_objekt_werden_uebernommen():
    papa = SimpleNamespace(anzeigename="Papa", rolle="eltern")
    objekt = JobSperre.objects.create(name="x", inhaber="h", gehalten_bis="2026-01-01T00:00Z")
    e = audit.protokollieren("aufgabe.bestaetigt", akteur=papa, objekt=objekt)
    assert (e.akteur_name, e.rolle) == ("Papa", "eltern")
    assert (e.objekt_typ, e.objekt_id) == ("kern.jobsperre", "x")


# --- insert-only -----------------------------------------------------------------------------


def test_save_auf_bestehendem_eintrag_verboten(eintrag):
    eintrag.aktion = "test.manipuliert"
    with pytest.raises(NurEinfuegenFehler):
        eintrag.save()


def test_delete_verboten(eintrag):
    with pytest.raises(NurEinfuegenFehler):
        eintrag.delete()
    with pytest.raises(NurEinfuegenFehler):
        AuditEintrag.objects.all().delete()


def test_queryset_update_verboten(eintrag):
    with pytest.raises(NurEinfuegenFehler):
        AuditEintrag.objects.filter(pk=eintrag.pk).update(aktion="test.x")
    with pytest.raises(NurEinfuegenFehler):
        AuditEintrag.objects.bulk_update([eintrag], ["aktion"])
    with pytest.raises(NurEinfuegenFehler):
        AuditEintrag.objects.update_or_create(pk=eintrag.pk, defaults={"aktion": "test.x"})


def test_trigger_verhindert_update_per_sql(eintrag):
    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE kern_auditeintrag SET aktion = 'x.y' WHERE id = %s", [eintrag.pk])
    eintrag.refresh_from_db()
    assert eintrag.aktion == "test.angelegt"


def test_trigger_verhindert_delete_per_sql(eintrag):
    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("DELETE FROM kern_auditeintrag")
    assert AuditEintrag.objects.filter(pk=eintrag.pk).exists()


def test_delete_per_sql_nur_im_wartungsmodus(eintrag):
    with wartung(), connection.cursor() as cur:
        cur.execute("DELETE FROM kern_auditeintrag")
    assert not AuditEintrag.objects.exists()


def test_update_per_sql_auch_im_wartungsmodus_verboten(eintrag):
    with pytest.raises(DatabaseError, match="insert-only"):
        with wartung(), transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE kern_auditeintrag SET aktion = 'x.y'")


def test_trigger_sind_angelegt():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = %s",
            ["kern_auditeintrag"],
        )
        namen = {zeile[0] for zeile in cur.fetchall()}
    assert namen == {"kern_auditeintrag_kein_update", "kern_auditeintrag_kein_delete"}


def test_rollback_hinterlaesst_keinen_eintrag():
    with pytest.raises(RuntimeError), transaction.atomic():
        audit.protokollieren("test.angelegt")
        raise RuntimeError
    assert not AuditEintrag.objects.exists()


# --- keine sensiblen Inhalte -----------------------------------------------------------------


@pytest.mark.parametrize(
    "details",
    [
        {"pin": "1234"},
        {"PIN": "1234"},
        {"neue_pin": "1234"},
        {"passwort": "geheim"},
        {"smtp_passwort": "x"},
        {"pin_hash": "argon2..."},
        {"token": "abc"},
        {"nachweis": {"inhalt": "Text des Kindes"}},
        {"liste": [{"foto": "base64..."}]},
    ],
)
def test_sensible_details_abgelehnt(details):
    with pytest.raises(audit.SensiblerInhalt):
        audit.protokollieren("test.sensibel", details=details)
    assert not AuditEintrag.objects.exists()


def test_details_groesse_und_typ_begrenzt():
    with pytest.raises(ValueError, match="zu groß"):
        audit.protokollieren("test.gross", details={"text": "x" * 5000})
    with pytest.raises(ValueError, match="dict"):
        audit.protokollieren("test.liste", details=["a"])
    with pytest.raises(ValueError, match="JSON"):
        audit.protokollieren("test.objekt", details={"x": object()})


@pytest.mark.parametrize("aktion", ["ohnepunkt", "Gross.klein", "", "a." + "x" * 80])
def test_ungueltige_aktion(aktion):
    with pytest.raises(ValueError):
        audit.protokollieren(aktion)


def test_ungueltige_rolle():
    with pytest.raises(ValueError, match="Rolle"):
        audit.protokollieren("test.x", akteur=SimpleNamespace(anzeigename="X", rolle="gast"))


@pytest.mark.django_db(transaction=True)
def test_transaktionaler_test_kann_audit_tabelle_leeren():
    """Teardown-Flush (DELETE) läuft im Wartungsmodus; ohne ihn würde der Trigger abbrechen."""
    audit.protokollieren("test.angelegt")
    assert AuditEintrag.objects.count() == 1


def test_objekt_id_bis_100_zeichen_und_trigger_greifen_weiter():
    """Migration 0004 (objekt_id 40 -> 100) baut die Tabelle neu auf; Trigger bleiben aktiv."""
    lang = "x" * 100
    e = audit.protokollieren("einstellung.geaendert", akteur=None, objekt_typ="t", objekt_id=lang)
    e.refresh_from_db()
    assert e.objekt_id == lang
    with pytest.raises(ValueError, match="max. 100"):
        audit.protokollieren("einstellung.geaendert", akteur=None, objekt_id="x" * 101)
    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE kern_auditeintrag SET objekt_id = 'y' WHERE id = %s", [e.pk])
    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("DELETE FROM kern_auditeintrag WHERE id = %s", [e.pk])


def test_migration_0004_rueckwaerts_und_vorwaerts_behaelt_trigger(transactional_db):
    from django.core.management import call_command

    def trigger():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = %s",
                ["kern_auditeintrag"],
            )
            return {zeile[0] for zeile in cur.fetchall()}

    erwartet = {"kern_auditeintrag_kein_update", "kern_auditeintrag_kein_delete"}
    try:
        call_command("migrate", "kern", "0003", verbosity=0)
        assert trigger() == erwartet
    finally:
        call_command("migrate", verbosity=0)
    assert trigger() == erwartet
