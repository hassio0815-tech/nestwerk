"""SQLite-Backups: konsistente Kopie, Rotation, Wiederherstellung, Prüfung (ARCHITECTURE 3.4).

Reine Standardbibliothek, keine Django-Modelle (Schicht 0). Die Commands ``db_sichern`` und
``backup_pruefen`` (apps/ereignisse) verdrahten Einstellungen, JobLauf und Ereignis.

- Kopie über die SQLite-Online-Backup-API (nie Dateikopie im Betrieb), danach
  ``journal_mode=DELETE`` (eine einzige Datei ohne -wal/-shm), ``integrity_check``, gzip.
- Dateiname: ``nestwerk-JJJJMMTT-HHMMSS-<grund>.sqlite3.gz`` (lokale Zeit).
- Rotation nur für ``taeglich``: je Tag/ISO-Woche/Monat bleibt das neueste Backup erhalten
  (N Tage, M Wochen, K Monate). Backups mit anderem Grund (``update``, ``manuell``) werden
  separat auf die neuesten ``update_behalten`` begrenzt – sie sind die Rollback-Punkte.
- Nachweis-Fotos und Secrets sind NICHT Teil des Backups (Datenschutz bzw. getrennte Sicherung).
"""

import gzip
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

GRUENDE = ("taeglich", "update", "manuell")
_NAME = re.compile(r"^(?:nestwerk|famko)-(\d{8})-(\d{6})-([a-z]+)\.sqlite3\.gz$")


class BackupFehler(Exception):
    """Backup/Wiederherstellung/Prüfung fehlgeschlagen."""


@dataclass(frozen=True)
class Rotation:
    taeglich: int = 14
    woechentlich: int = 8
    monatlich: int = 12
    update_behalten: int = 5


@dataclass(frozen=True)
class BackupDatei:
    pfad: Path
    zeit: datetime  # naiv, lokale Zeit aus dem Dateinamen
    grund: str


def dateiname(zeit, grund):
    return f"nestwerk-{zeit:%Y%m%d-%H%M%S}-{grund}.sqlite3.gz"


def auflisten(ordner):
    """Alle Backups im Ordner, neueste zuerst."""
    ergebnis = []
    # "famko-*": Backups bestehender Installationen (frühere Projektbezeichnung FamKo)
    pfade = [*Path(ordner).glob("nestwerk-*.sqlite3.gz"), *Path(ordner).glob("famko-*.sqlite3.gz")]
    for pfad in pfade:
        m = _NAME.match(pfad.name)
        if not m:
            continue
        zeit = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        ergebnis.append(BackupDatei(pfad, zeit, m.group(3)))
    return sorted(ergebnis, key=lambda b: b.zeit, reverse=True)


def integritaet_pruefen(db_pfad):
    """``PRAGMA integrity_check`` und ``foreign_key_check``; wirft ``BackupFehler``."""
    con = sqlite3.connect(str(db_pfad))
    try:
        ergebnis = [z[0] for z in con.execute("PRAGMA integrity_check")]
        if ergebnis != ["ok"]:
            raise BackupFehler(f"integrity_check: {'; '.join(ergebnis)[:300]}")
        verletzt = con.execute("PRAGMA foreign_key_check").fetchall()
        if verletzt:
            raise BackupFehler(f"foreign_key_check: {len(verletzt)} Verstöße")
    except sqlite3.DatabaseError as exc:
        raise BackupFehler(f"Datenbank nicht lesbar: {exc}") from exc
    finally:
        con.close()


def sichern(db_pfad, ordner, *, jetzt, grund="taeglich"):
    """Sichert ``db_pfad`` nach ``ordner``. Gibt die Backup-Datei zurück oder ``None``,
    wenn für diesen Tag bereits ein ``taeglich``-Backup existiert (idempotent)."""
    if grund not in GRUENDE:
        raise ValueError(f"Unbekannter Grund '{grund}'")
    db_pfad, ordner = Path(db_pfad), Path(ordner)
    if not db_pfad.is_file():
        raise BackupFehler(f"Datenbank nicht gefunden: {db_pfad}")
    ordner.mkdir(parents=True, exist_ok=True)
    if grund == "taeglich" and any(
        b.grund == "taeglich" and b.zeit.date() == jetzt.date() for b in auflisten(ordner)
    ):
        return None
    ziel = ordner / dateiname(jetzt, grund)
    with tempfile.TemporaryDirectory(dir=ordner, prefix=".tmp-") as tmp:
        kopie = Path(tmp) / "kopie.sqlite3"
        quelle = sqlite3.connect(str(db_pfad), timeout=30)
        try:
            quelle.execute("PRAGMA query_only=ON")
            ziel_con = sqlite3.connect(str(kopie))
            try:
                quelle.backup(ziel_con)
                ziel_con.execute("PRAGMA journal_mode=DELETE")
            finally:
                ziel_con.close()
        except sqlite3.DatabaseError as exc:
            raise BackupFehler(f"Sicherung fehlgeschlagen: {exc}") from exc
        finally:
            quelle.close()
        integritaet_pruefen(kopie)
        fertig = Path(tmp) / "fertig.gz"
        with kopie.open("rb") as src, gzip.open(fertig, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        fertig.chmod(0o600)
        fertig.replace(ziel)  # atomar im selben Dateisystem
    return ziel


def rotieren(ordner, regeln=None):
    """Löscht Backups außerhalb der Aufbewahrung. Gibt die gelöschten Dateinamen zurück."""
    regeln = regeln or Rotation()
    alle = auflisten(ordner)
    behalten = set()

    taeglich = [b for b in alle if b.grund == "taeglich"]  # neueste zuerst
    for schluessel, anzahl in (
        (lambda b: b.zeit.date(), regeln.taeglich),
        (lambda b: tuple(b.zeit.isocalendar())[:2], regeln.woechentlich),
        (lambda b: (b.zeit.year, b.zeit.month), regeln.monatlich),
    ):
        gesehen = []
        for b in taeglich:  # erstes je Schlüssel = neuestes
            k = schluessel(b)
            if k in gesehen:
                continue
            if len(gesehen) >= anzahl:
                break
            gesehen.append(k)
            behalten.add(b.pfad)

    andere = [b for b in alle if b.grund != "taeglich"]
    for grund in {b.grund for b in andere}:
        behalten.update(
            b.pfad for b in [x for x in andere if x.grund == grund][: regeln.update_behalten]
        )

    geloescht = []
    for b in alle:
        if b.pfad not in behalten:
            b.pfad.unlink(missing_ok=True)
            geloescht.append(b.pfad.name)
    return geloescht


def wiederherstellen(backup_pfad, ziel_pfad):
    """Entpackt ein Backup nach ``ziel_pfad`` (überschreibt) und prüft es."""
    ziel_pfad = Path(ziel_pfad)
    ziel_pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel_pfad.with_name(ziel_pfad.name + ".tmp")
    try:
        with gzip.open(backup_pfad, "rb") as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    except (OSError, EOFError) as exc:
        tmp.unlink(missing_ok=True)
        raise BackupFehler(f"Entpacken fehlgeschlagen: {exc}") from exc
    try:
        integritaet_pruefen(tmp)
    except BackupFehler:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(ziel_pfad)
    return ziel_pfad


def zeilenzahlen(db_pfad, tabellen=None):
    """Zeilenzahl je Tabelle (alle Nutzertabellen oder die angegebenen)."""
    con = sqlite3.connect(str(db_pfad))
    try:
        if tabellen is None:
            tabellen = [
                z[0]
                for z in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    " ORDER BY name"
                )
            ]
        zahlen = {}
        for t in tabellen:
            try:
                zahlen[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]  # noqa: S608
            except sqlite3.OperationalError:
                zahlen[t] = None  # Tabelle fehlt (z. B. sehr altes Backup)
        return zahlen
    finally:
        con.close()


def pruefen(ordner, *, jetzt, live_db=None, ledger_tabellen=(), max_alter_stunden=36):
    """Wiederherstellungstest: neuestes Backup in Temp-DB entpacken, prüfen, zählen.

    Wirft ``BackupFehler`` bei fehlendem/zu altem/defektem Backup oder wenn eine
    Insert-only-Tabelle (``ledger_tabellen``) im Backup MEHR Zeilen hat als die Live-DB.
    Gibt ein dict für ``JobLauf.info`` zurück.
    """
    liste = auflisten(ordner)
    if not liste:
        raise BackupFehler(f"Kein Backup in {ordner}")
    neuestes = liste[0]
    alter = (jetzt.replace(tzinfo=None) - neuestes.zeit).total_seconds() / 3600
    with tempfile.TemporaryDirectory(prefix="nestwerk-restore-") as tmp:
        wiederhergestellt = wiederherstellen(neuestes.pfad, Path(tmp) / "restore.sqlite3")
        gesamt = zeilenzahlen(wiederhergestellt)
        ledger = {t: gesamt.get(t) for t in ledger_tabellen}
    if any(v is None for v in ledger.values()):
        raise BackupFehler(f"Ledger-Tabelle fehlt im Backup: {ledger}")
    if live_db is not None and Path(live_db).is_file():
        live = zeilenzahlen(live_db, list(ledger_tabellen))
        for t, n in ledger.items():
            if live[t] is not None and n > live[t]:
                raise BackupFehler(f"{t}: Backup hat {n} Zeilen, Live-DB nur {live[t]}")
    if alter > max_alter_stunden:
        raise BackupFehler(f"Neuestes Backup ist {alter:.0f} h alt (Grenze {max_alter_stunden} h)")
    return {
        "datei": neuestes.pfad.name,
        "alter_stunden": round(alter, 1),
        "integrity": "ok",
        "tabellen": len(gesamt),
        "zeilen_gesamt": sum(v or 0 for v in gesamt.values()),
        "ledger": ledger,
    }


def live_wiederherstellen(backup_pfad, db_pfad, *, jetzt):
    """Spielt ein Backup als Live-DB ein (Dienste müssen gestoppt sein).

    Die bisherige DB samt -wal/-shm wird nach ``<db>.vor-restore-<zeit>`` verschoben, nie gelöscht.
    Gibt den Pfad der verschobenen Alt-DB zurück (oder ``None``, wenn es keine gab).
    """
    db_pfad = Path(db_pfad)
    neu = wiederherstellen(backup_pfad, db_pfad.with_name(db_pfad.name + ".neu"))
    beiseite = None
    if db_pfad.exists():
        beiseite = db_pfad.with_name(f"{db_pfad.name}.vor-restore-{jetzt:%Y%m%d-%H%M%S}")
        db_pfad.replace(beiseite)
    for anhang in ("-wal", "-shm"):  # veraltete WAL-Reste würden die neue DB zerstören
        alt = db_pfad.with_name(db_pfad.name + anhang)
        if alt.exists():
            alt.replace(
                beiseite.with_name(beiseite.name + anhang) if beiseite else alt.with_suffix(".alt")
            )
    neu.replace(db_pfad)
    return beiseite
