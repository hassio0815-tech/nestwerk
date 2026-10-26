import threading
import time
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from apps.ereignisse import registry, selectors, services, worker
from apps.ereignisse.models import Ereignis, EreignisVerarbeitung, Status
from apps.kern import audit, einstellungen
from apps.kern.models import AuditEintrag

from .conftest import TYP


def _wirkung(ereignis):
    """Handler mit DB-Wirkung: ein Audit-Eintrag je Ausführung."""
    audit.protokollieren("test.handler", objekt_typ="ereignis", objekt_id=ereignis.pk)


def _wirkungen():
    return AuditEintrag.objects.filter(aktion="test.handler").count()


def _veroeffentlichen(n):
    with transaction.atomic():
        return [services.veroeffentlichen(TYP, daten={"i": i}) for i in range(n)]


def _faellig_machen():
    EreignisVerarbeitung.objects.filter(status=Status.FEHLER).update(
        naechster_versuch=timezone.now() - timedelta(seconds=1)
    )


@pytest.mark.django_db
def test_handler_genau_einmal_bei_doppeltem_lauf(katalog):
    registry.handler_registrieren(TYP, _wirkung, name="test.wirkung")
    registry.handler_registrieren(TYP, _wirkung, name="test.zweiter")
    _veroeffentlichen(3)
    for _ in range(3):
        worker.runde()
    # zweimal verteilen derselben Ereignisse (z. B. zwei Worker) erzeugt keine Duplikate
    Ereignis.objects.update(verteilt=False)
    worker.runde()
    assert EreignisVerarbeitung.objects.count() == 6
    assert set(EreignisVerarbeitung.objects.values_list("status", "versuche")) == {(Status.OK, 1)}
    assert _wirkungen() == 6
    # direkter erneuter Aufruf einer erledigten Verarbeitung wird übersprungen
    vid = EreignisVerarbeitung.objects.first().pk
    assert worker.verarbeitung_ausfuehren(vid) == "uebersprungen"
    assert _wirkungen() == 6


@pytest.mark.django_db(transaction=True)
def test_zwei_worker_parallel_genau_einmal(katalog):
    aufrufe = []
    sperre = threading.Lock()

    def langsam(ereignis):
        with sperre:
            aufrufe.append(ereignis.pk)
        time.sleep(0.005)
        _wirkung(ereignis)

    registry.handler_registrieren(TYP, langsam, name="test.langsam")
    ereignisse = _veroeffentlichen(20)
    fehler = []
    start = threading.Barrier(2)

    def lauf():
        try:
            start.wait(5)
            for _ in range(10):
                worker.verteilen(stapel=5)
                worker.verarbeiten(stapel=5)
        except Exception as exc:  # pragma: no cover - Diagnose
            fehler.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=lauf) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not fehler
    worker.runde()  # Rest
    assert _wirkungen() == len(ereignisse)
    assert sorted(aufrufe) == sorted(e.pk for e in ereignisse)  # kein Handler doppelt gelaufen
    assert EreignisVerarbeitung.objects.filter(status=Status.OK).count() == len(ereignisse)


class Absturz(BaseException):
    """Simuliert ein Prozessende mitten im Handler (kill, OOM): wird nicht abgefangen."""


@pytest.mark.django_db
def test_neustart_verliert_nichts(katalog):
    zustand = {"absturz": True}

    def handler(ereignis):
        _wirkung(ereignis)
        if zustand["absturz"]:
            raise Absturz

    registry.handler_registrieren(TYP, handler, name="test.absturz")
    _veroeffentlichen(2)
    with pytest.raises(Absturz):
        worker.runde()
    # Wirkung und Statuswechsel sind zurückgerollt, nichts als erledigt markiert
    assert _wirkungen() == 0
    assert set(EreignisVerarbeitung.objects.values_list("status", "versuche")) == {
        (Status.OFFEN, 0)
    }

    zustand["absturz"] = False
    call_command("ereignisse_worker", "--einmal")  # "neu gestarteter" Worker
    assert _wirkungen() == 2
    assert set(EreignisVerarbeitung.objects.values_list("status", "versuche")) == {(Status.OK, 1)}


@pytest.mark.django_db
def test_worker_startet_spaeter_und_holt_nach(katalog):
    registry.handler_registrieren(TYP, _wirkung, name="test.wirkung")
    _veroeffentlichen(5)  # Worker lief nicht
    assert selectors.systemstatus()["unverteilt"] == 5
    call_command("ereignisse_worker", "--einmal")
    assert _wirkungen() == 5
    status = selectors.systemstatus()
    assert (status["unverteilt"], status["offen"], status["ok"]) == (0, 0, 5)


@pytest.mark.django_db
def test_retry_mit_backoff_und_erfolg(katalog):
    versuche = {"n": 0}

    def wackelig(ereignis):
        versuche["n"] += 1
        _wirkung(ereignis)
        if versuche["n"] < 3:
            raise RuntimeError(f"temporär {versuche['n']}")

    registry.handler_registrieren(TYP, wackelig, name="test.wackelig")
    _veroeffentlichen(1)

    vorher = timezone.now()
    assert worker.runde()["fehler"] == 1
    v = EreignisVerarbeitung.objects.get()
    assert (v.status, v.versuche) == (Status.FEHLER, 1)
    assert "temporär 1" in v.letzter_fehler
    assert timedelta(seconds=29) < v.naechster_versuch - vorher < timedelta(seconds=32)
    assert _wirkungen() == 0  # fehlgeschlagene Wirkung zurückgerollt

    assert worker.runde()["fehler"] == 0  # noch nicht fällig
    _faellig_machen()
    vorher = timezone.now()
    worker.runde()
    v.refresh_from_db()
    assert (v.status, v.versuche) == (Status.FEHLER, 2)
    assert timedelta(seconds=59) < v.naechster_versuch - vorher < timedelta(seconds=62)

    _faellig_machen()
    assert worker.runde()["ok"] == 1
    v.refresh_from_db()
    assert (v.status, v.versuche, v.letzter_fehler) == (Status.OK, 3, "")
    assert v.erledigt_am is not None
    assert _wirkungen() == 1


@pytest.mark.django_db
def test_backoff_deckel(katalog):
    einstellungen.setzen("ereignisse.max_versuche", 10)
    einstellungen.setzen("ereignisse.backoff_max_sekunden", 100)

    def kaputt(ereignis):
        raise RuntimeError("dauerhaft")

    registry.handler_registrieren(TYP, kaputt, name="test.kaputt")
    _veroeffentlichen(1)
    worker.runde()
    for _ in range(4):
        _faellig_machen()
        vorher = timezone.now()
        worker.runde()
    v = EreignisVerarbeitung.objects.get()
    assert v.versuche == 5
    assert v.naechster_versuch - vorher < timedelta(seconds=102)  # 30*2^4=480 -> gedeckelt


@pytest.mark.django_db
def test_max_versuche_aufgegeben_und_neu_einplanen(katalog):
    zustand = {"kaputt": True}

    def handler(ereignis):
        if zustand["kaputt"]:
            raise RuntimeError("dauerhaft")
        _wirkung(ereignis)

    registry.handler_registrieren(TYP, handler, name="test.handler")
    _veroeffentlichen(1)
    worker.herzschlag()
    worker.runde()
    for _ in range(5):
        _faellig_machen()
        worker.runde()
    v = EreignisVerarbeitung.objects.get()
    assert (v.status, v.versuche, v.naechster_versuch) == (Status.AUFGEGEBEN, 3, None)

    status = selectors.systemstatus()
    assert status["aufgegeben"] == 1 and status["worker_lebt"] and not status["gesund"]
    assert selectors.fehlerhafte()[0]["handler"] == "test.handler"

    zustand["kaputt"] = False
    assert services.neu_einplanen() == 1
    assert AuditEintrag.objects.filter(aktion="ereignisse.neu_eingeplant").count() == 1
    worker.runde()
    v.refresh_from_db()
    assert v.status == Status.OK and _wirkungen() == 1
    assert selectors.systemstatus()["gesund"]


@pytest.mark.django_db
def test_nicht_registrierter_handler_wird_fehler(katalog):
    registry.handler_registrieren(TYP, _wirkung, name="test.weg")
    _veroeffentlichen(1)
    worker.verteilen()
    with registry.handler_verzeichnis.isoliert():
        registry.handler_verzeichnis._eintraege.clear()  # Handler aus dem Code entfernt
        worker.verarbeiten()
    v = EreignisVerarbeitung.objects.get()
    assert v.status == Status.FEHLER and "nicht registriert" in v.letzter_fehler


@pytest.mark.django_db
def test_systemstatus_ohne_worker(katalog):
    status = selectors.systemstatus()
    assert status["worker_herzschlag"] is None
    assert not status["worker_lebt"] and not status["gesund"]
    worker.herzschlag()
    assert selectors.worker_lebt()
    assert not selectors.worker_lebt(max_alter=timedelta(seconds=-1))
