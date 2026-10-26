# ruff: noqa: F811  (Fixtures aus apps.benachrichtigung.tests.conftest)
"""Aufbewahrung (B-15, Review AP31): Fristen als Einstellungen, Ledger und Audit bleiben.

Unter tests/ (Querschnitt benachrichtigung/ereignisse/punkte/kern; lint-imports erfasst tests/
nicht)."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.benachrichtigung import services
from apps.benachrichtigung.models import Benachrichtigung, ZustellStatus, Zustellung
from apps.benachrichtigung.tests.conftest import (  # noqa: F401 (Fixtures)
    TYP_INFO,
    anna,
    katalog,
    mama,
    veroeffentlichen,
    zeitzone,
)
from apps.ereignisse import worker
from apps.ereignisse.models import Ereignis, EreignisVerarbeitung, Status
from apps.kern import audit, einstellungen
from apps.kern.models import AuditEintrag, JobLauf, JobStatus
from apps.punkte import services as punkte

pytestmark = pytest.mark.django_db
TAG = timedelta(days=1)


def _worker():
    for _ in range(5):
        worker.runde()


def _alt(ereignis, tage):
    zeit = timezone.now() - tage * TAG
    Ereignis.objects.filter(pk=ereignis.pk).update(zeit=zeit)
    Benachrichtigung.objects.filter(ereignis=ereignis).update(erstellt_am=zeit)


def test_fristen_sind_einstellungen_mit_startwerten():
    assert einstellungen.werte(
        "benachrichtigung.aufbewahrung_ungelesen_tage",
        "benachrichtigung.zustellung_aufbewahrung_tage",
        "ereignisse.aufbewahrung_tage",
        "allgemein.joblauf_aufbewahrung_tage",
    ) == {
        "benachrichtigung.aufbewahrung_ungelesen_tage": 180,
        "benachrichtigung.zustellung_aufbewahrung_tage": 90,
        "ereignisse.aufbewahrung_tage": 180,
        "allgemein.joblauf_aufbewahrung_tage": 90,
    }


def test_alte_daten_weg_junge_bleiben_ledger_und_audit_nie(katalog, mama, anna):
    alt = veroeffentlichen(TYP_INFO, kind=anna)
    mittel = veroeffentlichen(TYP_INFO, kind=anna)
    jung = veroeffentlichen(TYP_INFO, kind=anna)
    _worker()
    assert Zustellung.objects.exists()
    _alt(alt, 200)  # ungelesen > 180 -> Benachrichtigung und danach Ereignis weg
    _alt(mittel, 120)  # Zustellungen > 90 weg, ungelesene Benachrichtigung bleibt
    buchung = punkte.buchen(anna, punkte.Art.AUFGABE, 5, schluessel="b15", quelle_modul="t")
    audit.protokollieren("test.b15", akteur=None)
    audit_vorher = AuditEintrag.objects.count()
    JobLauf.objects.create(name="x", status=JobStatus.OK, gestartet_am=timezone.now() - 100 * TAG)

    ergebnis = services.aufbewahrung()

    assert not Benachrichtigung.objects.filter(ereignis=alt).exists()
    assert not Ereignis.objects.filter(pk=alt.pk).exists()
    assert not EreignisVerarbeitung.objects.filter(ereignis_id=alt.pk).exists()
    b_mittel = Benachrichtigung.objects.get(ereignis=mittel, empfaenger=mama)
    rest = list(b_mittel.zustellungen.values_list("kanal_id", "status"))
    assert rest == []
    assert Ereignis.objects.filter(pk=mittel.pk).exists()  # noch referenziert
    assert Benachrichtigung.objects.filter(ereignis=jung).exists()
    assert Zustellung.objects.filter(benachrichtigung__ereignis=jung).exists()
    assert ergebnis["job_laeufe"] == 1 and ergebnis["ereignisse"] == 1
    from apps.punkte import selectors

    assert selectors.buchung_zu_schluessel("b15") == buchung
    assert selectors.guthaben(anna) == 5
    assert AuditEintrag.objects.count() == audit_vorher
    # Doppellauf ändert nichts mehr
    assert services.aufbewahrung() == {
        "benachrichtigungen": 0,
        "zustellungen": 0,
        "ereignisse": 0,
        "job_laeufe": 0,
    }


def test_offene_oder_fehlerhafte_verarbeitung_bleibt(katalog, mama, anna):
    e = veroeffentlichen(TYP_INFO, kind=anna)
    _worker()
    Benachrichtigung.objects.filter(ereignis=e).delete()
    EreignisVerarbeitung.objects.filter(ereignis=e).update(status=Status.AUFGEGEBEN)
    _alt(e, 400)
    services.aufbewahrung()
    assert Ereignis.objects.filter(pk=e.pk).exists()  # bleibt sichtbar im Systemstatus


def test_junge_zustellung_mit_fehler_bleibt(katalog, mama, anna):
    e = veroeffentlichen(TYP_INFO, kind=anna)
    _worker()
    Zustellung.objects.update(status=ZustellStatus.FEHLER)
    _alt(e, 30)
    services.aufbewahrung()
    assert Zustellung.objects.filter(status=ZustellStatus.FEHLER).exists()


def test_job_protokolliert(katalog):
    call_command("benachrichtigungen_aufraeumen")
    assert JobLauf.objects.get(name="benachrichtigungen_aufraeumen").status == JobStatus.OK
