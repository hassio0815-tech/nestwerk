import gzip
import sqlite3
from datetime import datetime, timedelta

import pytest

from apps.kern import backup


def _db(pfad, zeilen=3):
    """Echte Datei-DB im WAL-Modus mit Ledger-Tabelle."""
    con = sqlite3.connect(str(pfad))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE punkte_buchung (id INTEGER PRIMARY KEY, betrag INTEGER)")
    con.executemany("INSERT INTO punkte_buchung (betrag) VALUES (?)", [(i,) for i in range(zeilen)])
    con.commit()
    con.close()
    return pfad


JETZT = datetime(2026, 11, 2, 3, 30)


def test_sichern_und_wiederherstellen(tmp_path):
    quelle = _db(tmp_path / "live.sqlite3")
    datei = backup.sichern(quelle, tmp_path / "bak", jetzt=JETZT)
    assert datei.name == "nestwerk-20261102-033000-taeglich.sqlite3.gz"
    assert not list((tmp_path / "bak").glob(".tmp-*"))  # Temp-Ordner aufgeräumt
    ziel = backup.wiederherstellen(datei, tmp_path / "neu" / "nestwerk.sqlite3")
    assert backup.zeilenzahlen(ziel) == {"punkte_buchung": 3}
    # Eine einzige Datei, kein WAL-Anhang
    assert not (tmp_path / "neu" / "nestwerk.sqlite3-wal").exists()


def test_sichern_waehrend_offener_schreibverbindung_ist_konsistent(tmp_path):
    quelle = _db(tmp_path / "live.sqlite3")
    offen = sqlite3.connect(str(quelle))  # zweiter Prozess (WAL), Daten noch im -wal
    offen.execute("INSERT INTO punkte_buchung (betrag) VALUES (99)")
    offen.commit()
    datei = backup.sichern(quelle, tmp_path / "bak", jetzt=JETZT)
    offen.close()
    ziel = backup.wiederherstellen(datei, tmp_path / "r.sqlite3")
    assert backup.zeilenzahlen(ziel)["punkte_buchung"] == 4


def test_taeglich_ist_idempotent_update_nicht(tmp_path):
    quelle = _db(tmp_path / "live.sqlite3")
    assert backup.sichern(quelle, tmp_path / "bak", jetzt=JETZT) is not None
    assert backup.sichern(quelle, tmp_path / "bak", jetzt=JETZT + timedelta(hours=10)) is None
    update = backup.sichern(quelle, tmp_path / "bak", jetzt=JETZT, grund="update")
    assert update is not None and update.name.endswith("-update.sqlite3.gz")


def test_fehlende_oder_defekte_db(tmp_path):
    with pytest.raises(backup.BackupFehler, match="nicht gefunden"):
        backup.sichern(tmp_path / "gibt-es-nicht", tmp_path / "bak", jetzt=JETZT)
    kaputt = tmp_path / "kaputt.sqlite3"
    kaputt.write_bytes(b"das ist keine datenbank" * 500)
    with pytest.raises(backup.BackupFehler):
        backup.sichern(kaputt, tmp_path / "bak", jetzt=JETZT)
    assert backup.auflisten(tmp_path / "bak") == []


def test_wiederherstellen_lehnt_defektes_backup_ab(tmp_path):
    bak = tmp_path / "nestwerk-20261102-033000-taeglich.sqlite3.gz"
    with gzip.open(bak, "wb") as f:
        f.write(b"Muell" * 1000)
    ziel = tmp_path / "r.sqlite3"
    with pytest.raises(backup.BackupFehler):
        backup.wiederherstellen(bak, ziel)
    assert not ziel.exists()


def _dummy_backups(ordner, zeiten, grund="taeglich"):
    ordner.mkdir(exist_ok=True)
    for z in zeiten:
        (ordner / backup.dateiname(z, grund)).write_bytes(b"x")


def test_rotation_taeglich_woechentlich_monatlich(tmp_path):
    start = datetime(2026, 1, 1, 3, 30)
    _dummy_backups(tmp_path, [start + timedelta(days=i) for i in range(200)])
    ende = start + timedelta(days=199)  # 2026-07-19
    geloescht = backup.rotieren(tmp_path, backup.Rotation(14, 8, 12, 5))
    rest = backup.auflisten(tmp_path)
    tage = {b.zeit.date() for b in rest}
    # die letzten 14 Tage sind vollständig da
    assert all((ende - timedelta(days=i)).date() in tage for i in range(14))
    # darüber hinaus höchstens 1 je ISO-Woche (8 Wochen) und 1 je Monat (12)
    assert len(rest) <= 14 + 8 + 12
    assert len(rest) > 14
    assert len(geloescht) == 200 - len(rest)
    # jüngstes Backup bleibt, ältestes (Januar, Wochen/Monats-Anker) nur wenn Monatsanker
    assert rest[0].zeit == ende
    # Idempotent
    assert backup.rotieren(tmp_path, backup.Rotation(14, 8, 12, 5)) == []


def test_rotation_update_backups_getrennt(tmp_path):
    start = datetime(2026, 3, 1, 12, 0)
    _dummy_backups(tmp_path, [start + timedelta(hours=i) for i in range(8)], grund="update")
    _dummy_backups(tmp_path, [start], grund="taeglich")
    backup.rotieren(tmp_path, backup.Rotation(14, 8, 12, update_behalten=3))
    rest = backup.auflisten(tmp_path)
    assert sorted(b.grund for b in rest) == ["taeglich", "update", "update", "update"]
    # die neuesten drei Update-Backups bleiben
    assert [b.zeit.hour for b in rest if b.grund == "update"] == [19, 18, 17]


def test_fremde_dateien_werden_ignoriert(tmp_path):
    (tmp_path / "notiz.txt").write_text("hi")
    (tmp_path / "nestwerk-kaputt.sqlite3.gz").write_text("hi")
    assert backup.auflisten(tmp_path) == []
    backup.rotieren(tmp_path)
    assert (tmp_path / "notiz.txt").exists()


def test_pruefen_ok_und_ledger_vergleich(tmp_path):
    live = _db(tmp_path / "live.sqlite3", zeilen=3)
    backup.sichern(live, tmp_path / "bak", jetzt=JETZT)
    # Live wächst nach dem Backup: ok
    con = sqlite3.connect(str(live))
    con.execute("INSERT INTO punkte_buchung (betrag) VALUES (1)")
    con.commit()
    con.close()
    info = backup.pruefen(
        tmp_path / "bak",
        jetzt=JETZT + timedelta(hours=1),
        live_db=live,
        ledger_tabellen=("punkte_buchung",),
    )
    assert info["integrity"] == "ok" and info["ledger"] == {"punkte_buchung": 3}
    assert info["alter_stunden"] == 1.0


def test_pruefen_fehler(tmp_path):
    with pytest.raises(backup.BackupFehler, match="Kein Backup"):
        backup.pruefen(tmp_path / "leer", jetzt=JETZT)
    live = _db(tmp_path / "live.sqlite3", zeilen=3)
    backup.sichern(live, tmp_path / "bak", jetzt=JETZT)
    # zu alt
    with pytest.raises(backup.BackupFehler, match="alt"):
        backup.pruefen(tmp_path / "bak", jetzt=JETZT + timedelta(days=3))
    # Backup hat mehr Ledger-Zeilen als Live (Live-DB zurückgesetzt/verloren)
    kleiner = _db(tmp_path / "kleiner.sqlite3", zeilen=1)
    with pytest.raises(backup.BackupFehler, match="nur 1"):
        backup.pruefen(
            tmp_path / "bak", jetzt=JETZT, live_db=kleiner, ledger_tabellen=("punkte_buchung",)
        )
    # Ledger-Tabelle fehlt im Backup
    with pytest.raises(backup.BackupFehler, match="fehlt"):
        backup.pruefen(tmp_path / "bak", jetzt=JETZT, ledger_tabellen=("gibt_es_nicht",))


def test_live_wiederherstellen_behaelt_alte_db(tmp_path):
    live = _db(tmp_path / "live.sqlite3", zeilen=3)
    datei = backup.sichern(live, tmp_path / "bak", jetzt=JETZT)
    con = sqlite3.connect(str(live))
    con.execute("DELETE FROM punkte_buchung")  # Katastrophe
    con.commit()
    con.close()
    (tmp_path / "live.sqlite3-wal").write_bytes(b"stale")
    beiseite = backup.live_wiederherstellen(datei, live, jetzt=JETZT)
    assert beiseite.exists() and backup.zeilenzahlen(live) == {"punkte_buchung": 3}
    assert not (tmp_path / "live.sqlite3-wal").exists()


def test_alte_famko_backups_werden_erkannt(tmp_path):
    """Backups bestehender Installationen (frühere Bezeichnung FamKo) bleiben sichtbar."""
    (tmp_path / "famko-20261102-033000-update.sqlite3.gz").write_text("x")
    (tmp_path / "nestwerk-20261103-033000-taeglich.sqlite3.gz").write_text("x")
    namen = [b.pfad.name for b in backup.auflisten(tmp_path)]
    assert namen == [
        "nestwerk-20261103-033000-taeglich.sqlite3.gz",
        "famko-20261102-033000-update.sqlite3.gz",
    ]
