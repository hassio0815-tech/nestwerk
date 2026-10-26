"""db_sichern und backup_pruefen gegen eine echte Datei-DB (AP18)."""

import sqlite3
from datetime import datetime, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ereignisse.events import BACKUP_FEHLER
from apps.ereignisse.models import Ereignis
from apps.kern import backup
from apps.kern.models import JobLauf, JobStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def live(tmp_path):
    pfad = tmp_path / "live.sqlite3"
    con = sqlite3.connect(str(pfad))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE punkte_buchung (id INTEGER PRIMARY KEY, betrag INTEGER)")
    con.executemany("INSERT INTO punkte_buchung (betrag) VALUES (?)", [(5,), (7,)])
    con.commit()
    con.close()
    return pfad


def _sichern(live, ziel, **kw):
    call_command("db_sichern", db_pfad=str(live), ziel=str(ziel), **kw)


def test_db_sichern_schreibt_backup_und_joblauf(live, tmp_path):
    ziel = tmp_path / "bak"
    _sichern(live, ziel)
    dateien = backup.auflisten(ziel)
    assert len(dateien) == 1 and dateien[0].grund == "taeglich"
    lauf = JobLauf.objects.get(name="db_sichern")
    assert lauf.status == JobStatus.OK and lauf.info["datei"] == dateien[0].pfad.name
    # zweiter Lauf am selben Tag: überspringt, kein zweites Backup
    _sichern(live, ziel)
    assert len(backup.auflisten(ziel)) == 1
    assert JobLauf.objects.filter(name="db_sichern", status=JobStatus.OK).count() == 2


def test_db_sichern_update_ohne_joblauf(live, tmp_path):
    ziel = tmp_path / "bak"
    _sichern(live, ziel, grund="update")
    assert [b.grund for b in backup.auflisten(ziel)] == ["update"]
    assert not JobLauf.objects.filter(name="db_sichern").exists()
    with pytest.raises(CommandError):
        _sichern(tmp_path / "fehlt.sqlite3", ziel, grund="update")


def test_db_sichern_fehler_erzeugt_joblauf_und_ereignis(tmp_path):
    with pytest.raises(backup.BackupFehler):
        _sichern(tmp_path / "fehlt.sqlite3", tmp_path / "bak")
    assert JobLauf.objects.get(name="db_sichern").status == JobStatus.FEHLER
    assert Ereignis.objects.filter(typ_id=BACKUP_FEHLER).count() == 1
    # höchstens ein Ereignis je Job und Tag
    with pytest.raises(backup.BackupFehler):
        _sichern(tmp_path / "fehlt.sqlite3", tmp_path / "bak")
    assert Ereignis.objects.filter(typ_id=BACKUP_FEHLER).count() == 1


def test_backup_pruefen_ok(live, tmp_path):
    ziel = tmp_path / "bak"
    _sichern(live, ziel)
    call_command("backup_pruefen", db_pfad=str(live), ziel=str(ziel))
    lauf = JobLauf.objects.get(name="backup_pruefen")
    assert lauf.status == JobStatus.OK
    assert lauf.info["integrity"] == "ok" and lauf.info["ledger"] == {"punkte_buchung": 2}
    assert not Ereignis.objects.filter(typ_id=BACKUP_FEHLER).exists()


def test_backup_pruefen_ohne_backup_meldet_fehler(live, tmp_path):
    with pytest.raises(backup.BackupFehler):
        call_command("backup_pruefen", db_pfad=str(live), ziel=str(tmp_path / "leer"))
    assert JobLauf.objects.get(name="backup_pruefen").status == JobStatus.FEHLER
    e = Ereignis.objects.get(typ_id=BACKUP_FEHLER)
    assert e.daten["job"] == "backup_pruefen" and "Kein Backup" in e.daten["fehler"]


def test_backup_pruefen_erkennt_veraltetes_backup(live, tmp_path):
    ziel = tmp_path / "bak"
    alt = datetime.now() - timedelta(days=5)
    backup.sichern(live, ziel, jetzt=alt)
    with pytest.raises(backup.BackupFehler, match="alt"):
        call_command("backup_pruefen", db_pfad=str(live), ziel=str(ziel))


def test_benachrichtigungen_aufraeumen_laeuft():
    call_command("benachrichtigungen_aufraeumen")
    lauf = JobLauf.objects.get(name="benachrichtigungen_aufraeumen")
    assert lauf.status == JobStatus.OK and lauf.info == {
        "benachrichtigungen": 0,
        "zustellungen": 0,
        "ereignisse": 0,
        "job_laeufe": 0,
    }
