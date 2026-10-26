import threading
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.kern import jobs
from apps.kern.models import JobLauf, JobSperre, JobStatus


@pytest.mark.django_db
def test_zweite_sperre_wird_verweigert():
    erste = jobs.sperre_holen("test_job")
    assert erste is not None
    assert jobs.sperre_holen("test_job") is None
    erste.freigeben()
    assert jobs.sperre_holen("test_job") is not None


@pytest.mark.django_db
def test_abgelaufene_sperre_wird_uebernommen():
    alt = jobs.sperre_holen("test_job")
    JobSperre.objects.filter(name="test_job").update(
        gehalten_bis=timezone.now() - timedelta(seconds=1)
    )
    neu = jobs.sperre_holen("test_job")
    assert neu is not None and neu.inhaber != alt.inhaber
    # Der alte Inhaber kann die übernommene Sperre weder verlängern noch freigeben
    assert alt.verlaengern() is False
    alt.freigeben()
    assert JobSperre.objects.get(name="test_job").inhaber == neu.inhaber
    assert neu.verlaengern() is True


@pytest.mark.django_db
def test_sperre_kontextmanager_gibt_frei():
    with jobs.sperre("test_job") as s:
        assert s is not None
        with jobs.sperre("test_job") as zweite:
            assert zweite is None
    assert not JobSperre.objects.exists()


@pytest.mark.django_db
def test_ausfuehren_protokolliert_ok():
    lauf = jobs.ausfuehren("test_job", lambda s: {"erzeugt": 3})
    lauf.refresh_from_db()
    assert lauf.status == JobStatus.OK
    assert lauf.info == {"erzeugt": 3}
    assert lauf.beendet_am >= lauf.gestartet_am
    assert not JobSperre.objects.exists()


@pytest.mark.django_db
def test_doppelter_lauf_wird_uebersprungen():
    innen = {}

    def job(s):
        innen["zweiter"] = jobs.ausfuehren("test_job", lambda s2: {"doppelt": True})
        return {"erzeugt": 1}

    erster = jobs.ausfuehren("test_job", job)
    zweiter = innen["zweiter"]
    assert erster.status == JobStatus.OK
    assert zweiter.status == JobStatus.UEBERSPRUNGEN
    assert zweiter.info["grund"] == "gesperrt"
    assert JobLauf.objects.filter(name="test_job").count() == 2


@pytest.mark.django_db
def test_fehler_wird_protokolliert_und_sperre_freigegeben():
    def job(s):
        raise RuntimeError("kaputt")

    with pytest.raises(RuntimeError):
        jobs.ausfuehren("test_job", job)
    lauf = JobLauf.objects.get(name="test_job")
    assert lauf.status == JobStatus.FEHLER
    assert "kaputt" in lauf.info["fehler"]
    assert lauf.beendet_am is not None
    assert not JobSperre.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_paralleler_lauf_in_zweitem_thread_wird_verhindert():
    gestartet = threading.Event()
    weiter = threading.Event()
    ergebnis = {}

    def langer_job(s):
        gestartet.set()
        assert weiter.wait(10)
        return {"fertig": True}

    def thread_a():
        try:
            ergebnis["a"] = jobs.ausfuehren("parallel_job", langer_job)
        finally:
            connection.close()

    a = threading.Thread(target=thread_a)
    a.start()
    try:
        assert gestartet.wait(10)
        ergebnis["b"] = jobs.ausfuehren("parallel_job", lambda s: {"fertig": True})
    finally:
        weiter.set()
        a.join(10)
    assert ergebnis["a"].status == JobStatus.OK
    assert ergebnis["b"].status == JobStatus.UEBERSPRUNGEN
    assert ergebnis["b"].info["inhaber"]  # Halter (Host:PID:...) wird mitprotokolliert
    # Nach Ende von A ist die Sperre frei: nächster Lauf läuft normal
    assert jobs.ausfuehren("parallel_job", lambda s: None).status == JobStatus.OK


class _TestBefehl(jobs.JobBefehl):
    job_name = "test_befehl"

    def job(self, sperre, **optionen):
        return {"sperre": sperre.name}


@pytest.mark.django_db
def test_job_befehl(capsys):
    call_command(_TestBefehl())
    lauf = JobLauf.objects.get(name="test_befehl")
    assert lauf.status == JobStatus.OK and lauf.info == {"sperre": "test_befehl"}
    assert "test_befehl: ok" in capsys.readouterr().out
