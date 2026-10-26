"""Ledger: insert-only, DB-Constraints, Salden als Summe (inkl. Hypothesis-Eigenschaftstest)."""

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.kern.db import NurEinfuegenFehler, wartung
from apps.punkte import selectors, services
from apps.punkte.models import Art, Buchung

from .conftest import TAG, gutschrift

pytestmark = pytest.mark.django_db


@pytest.fixture
def buchung(anna):
    return gutschrift(anna, 10)


# --- insert-only -----------------------------------------------------------------------------


def test_save_auf_bestehender_buchung_verboten(buchung):
    buchung.guthaben_delta = 1000
    with pytest.raises(NurEinfuegenFehler):
        buchung.save()


def test_delete_verboten(buchung):
    with pytest.raises(NurEinfuegenFehler):
        buchung.delete()
    with pytest.raises(NurEinfuegenFehler):
        Buchung.objects.all().delete()
    with pytest.raises(NurEinfuegenFehler):
        Buchung.objects.filter(pk=buchung.pk).delete()


def test_queryset_aenderungen_verboten(buchung):
    with pytest.raises(NurEinfuegenFehler):
        Buchung.objects.filter(pk=buchung.pk).update(guthaben_delta=1000)
    with pytest.raises(NurEinfuegenFehler):
        Buchung.objects.bulk_update([buchung], ["guthaben_delta"])
    with pytest.raises(NurEinfuegenFehler):
        Buchung.objects.update_or_create(pk=buchung.pk, defaults={"guthaben_delta": 1})


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE punkte_buchung SET guthaben_delta = 1000 WHERE id = %s",
        "DELETE FROM punkte_buchung WHERE id = %s",
    ],
)
def test_trigger_verhindert_aenderung_per_sql(buchung, sql):
    with pytest.raises(DatabaseError, match="insert-only"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, [buchung.pk])
    buchung.refresh_from_db()
    assert buchung.guthaben_delta == 10


def test_update_per_sql_auch_im_wartungsmodus_verboten(buchung):
    with pytest.raises(DatabaseError, match="insert-only"):
        with wartung(), transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE punkte_buchung SET xp_delta = 0")


def test_trigger_sind_angelegt():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = %s",
            ["punkte_buchung"],
        )
        namen = {zeile[0] for zeile in cur.fetchall()}
    assert namen == {"punkte_buchung_kein_update", "punkte_buchung_kein_delete"}


# --- DB-Constraints (greifen auch ohne Service) ----------------------------------------------


def _roh(kind, **kwargs):
    werte = {
        "kind": kind,
        "bezugsdatum": TAG,
        "art": Art.AUFGABE,
        "guthaben_delta": 5,
        "xp_delta": 5,
        "idempotenz_schluessel": "roh",
        "quelle_modul": "test",
    }
    werte.update(kwargs)
    with transaction.atomic():
        return Buchung.objects.create(**werte)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"xp_delta": -5},  # XP sinkt nur durch Korrektur/Storno
        {"art": Art.STORNO},  # Storno ohne Original
        {"guthaben_delta": 0, "xp_delta": 0},  # leere Buchung
    ],
)
def test_check_constraints(anna, kwargs):
    with pytest.raises(IntegrityError):
        _roh(anna, **kwargs)


def test_idempotenz_schluessel_ist_unique_in_der_db(anna):
    _roh(anna)
    with pytest.raises(IntegrityError):
        _roh(anna)


def test_korrektur_darf_xp_senken(anna):
    assert _roh(anna, art=Art.KORREKTUR, guthaben_delta=-5, xp_delta=-5).pk


# --- Salden ----------------------------------------------------------------------------------


def test_salden_ohne_buchungen(anna):
    assert selectors.salden(anna) == selectors.Saldo(guthaben=0, xp=0)
    assert selectors.verfuegbar(anna) == 0


def test_salden_je_kind_getrennt(anna, ben):
    gutschrift(anna, 30)
    gutschrift(ben, 7)
    gutschrift(anna, 10, art=Art.EINLOESUNG)
    assert selectors.salden(anna) == selectors.Saldo(guthaben=20, xp=30)
    assert selectors.salden(ben) == selectors.Saldo(guthaben=7, xp=7)
    assert selectors.xp_zeitraum(TAG, TAG) == 37
    assert selectors.xp_zeitraum(TAG, TAG, kind=ben) == 7


# --- Hypothesis: beliebige Buchungsfolgen -> Saldo = Summe -----------------------------------

POSITIV = st.integers(min_value=1, max_value=500)
SCHRITT = st.one_of(
    st.tuples(
        st.sampled_from([Art.AUFGABE, Art.SERIENBONUS, Art.SONDERPUNKTE, Art.MODUL]), POSITIV
    ),
    st.tuples(st.sampled_from([Art.EINLOESUNG, Art.MODKAUF]), POSITIV),
    st.tuples(
        st.just(Art.KORREKTUR),
        st.integers(min_value=-300, max_value=300).filter(bool),
    ),
    st.tuples(st.just(Art.STORNO), st.integers(min_value=0, max_value=50)),
    st.tuples(st.just("wiederholung"), st.integers(min_value=0, max_value=50)),
)


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(schritte=st.lists(SCHRITT, max_size=30))
def test_saldo_ist_summe_beliebiger_buchungsfolgen(anna, mama, schritte):
    with transaction.atomic():
        erwartet_g = erwartet_x = 0
        gebucht = []  # (schluessel, art, punkte) aller neuen Nicht-Storno-Buchungen
        for nr, (art, wert) in enumerate(schritte):
            vorher = Buchung.objects.count()
            if art == "wiederholung":
                if not gebucht:
                    continue
                schluessel, alt_art, punkte = gebucht[wert % len(gebucht)]
                gutschrift(anna, punkte, art=alt_art, schluessel=schluessel, von=mama)
                assert Buchung.objects.count() == vorher  # doppelter Schlüssel: nichts neu
                continue
            if art == Art.STORNO:
                kandidaten = list(Buchung.objects.exclude(art=Art.STORNO).order_by("id"))
                if not kandidaten:
                    continue
                original = kandidaten[wert % len(kandidaten)]
                schon = Buchung.objects.filter(storno_von=original).exists()
                storno = services.gegenbuchen(original, von=mama)
                if not schon:
                    erwartet_g -= original.guthaben_delta
                    erwartet_x -= original.xp_delta
                assert storno.guthaben_delta == -original.guthaben_delta
                assert storno.xp_delta == -original.xp_delta
                assert Buchung.objects.count() == vorher + (0 if schon else 1)
                continue
            g_faktor, x_faktor = services.WIRKUNG[art]
            schluessel = f"h:{nr}"
            if art in services.AUSGABEN and erwartet_g < wert:
                with pytest.raises(services.GuthabenUnzureichend):
                    gutschrift(anna, wert, art=art, schluessel=schluessel, von=mama)
                assert Buchung.objects.count() == vorher
                continue
            gutschrift(anna, wert, art=art, schluessel=schluessel, von=mama)
            gebucht.append((schluessel, art, wert))
            erwartet_g += g_faktor * wert
            erwartet_x += x_faktor * wert
            if art in services.AUSGABEN:
                assert selectors.guthaben(anna) >= 0

        saldo = selectors.salden(anna)
        zeilen = list(Buchung.objects.filter(kind=anna).values_list("guthaben_delta", "xp_delta"))
        assert saldo.guthaben == sum(g for g, _ in zeilen) == erwartet_g
        assert saldo.xp == sum(x for _, x in zeilen) == erwartet_x
        transaction.set_rollback(True)
