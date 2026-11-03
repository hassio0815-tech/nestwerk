"""Speicher-Backend der Lernmappe (SPEC 21.5): Ordner ``inbox``, ``archiv`` und ``tests`` je Kind.

Der Basispfad kommt aus ``settings.LERNEN_SPEICHER_DIR`` (Standard: Docker-Volume unter
``DATA_DIR/lernen``) und lässt sich auf einen gemounteten Pfad (z. B. NAS) umstellen. Ordner
heißen nach der Kind-ID (``kind_<id>``, Konten-ID als UUID), nie nach dem Namen. Jeder Pfad
wird aufgelöst und muss unter dem Ordner des Kindes liegen; Dateinamen sind reine Namen
(kein ``/``, kein ``..``).
Etappe 4 ergänzt ``lesen``, den Blick auf fremde Dateien im Ordner ``inbox`` (``inbox_dateien``,
zweiter Eingang z. B. über ein NAS) und deren sicheres Übernehmen (``uebernehmen``).
"""

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.utils.translation import gettext as _

from apps.kern.einstellungen import EinstellungFehlt, wert

BEREICHE = ("inbox", "archiv", "tests")


class SpeicherFehler(Exception):
    """Unzulässiger Pfad, Dateiname oder Bereich."""


class PfadFehler(SpeicherFehler, ValueError):
    """Der gewählte Speicherort ist unzulässig (Meldung für die Eltern, ohne Systemdetails)."""


class SpeicherVoll(SpeicherFehler):
    """Das Speicherlimit des Kindes wäre überschritten."""


@dataclass(frozen=True)
class InboxDatei:
    """Eine von außen abgelegte Datei im ``inbox``. ``hinweis`` = Name des Unterordners (Fach)."""

    pfad: Path
    hinweis: str
    name: str
    groesse: int
    geaendert: float


# Systemordner, die nie als Speicherort taugen (Prüfung nach dem Auflösen von Verknüpfungen)
GESPERRTE_WURZELN = (
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib32",
    "/lib64",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/sys",
    "/usr",
)
PFAD_MAX = 300


def pfad_pruefen(text, *, schreibtest=True):
    """Prüft einen gemounteten Speicherort und gibt den aufgelösten Pfad (``Path``) zurück.

    Verlangt: absoluter Pfad ohne ``..``, kein Systemordner und nicht der Programmordner, ein
    vorhandener Ordner (er wird nie angelegt, er muss eingebunden sein) und, wenn ``schreibtest``,
    eine kurze Testdatei, die sofort wieder verschwindet. Fehler sind ``PfadFehler`` mit einer
    Meldung ohne technische Details."""
    text = (text or "").strip()
    if not text:
        raise PfadFehler(_("Bitte einen Pfad eintragen."))
    if len(text) > PFAD_MAX or "\x00" in text or any(ord(z) < 32 for z in text):
        raise PfadFehler(_("Der Pfad ist ungültig."))
    if not os.path.isabs(text) or ".." in Path(text).parts:
        raise PfadFehler(_("Bitte einen vollständigen Pfad ohne „..“ eintragen (beginnt mit /)."))
    ziel = Path(text).resolve()
    gesperrt = [Path(p) for p in GESPERRTE_WURZELN] + [Path(settings.BASE_DIR).resolve()]
    if ziel == Path(ziel.anchor) or any(ziel == p or p in ziel.parents for p in gesperrt):
        raise PfadFehler(
            _("Dieser Ordner darf nicht verwendet werden. Bitte einen eigenen Ordner wählen.")
        )
    if not ziel.is_dir():
        raise PfadFehler(
            _(
                "Diesen Ordner gibt es nicht. "
                "Bitte zuerst den Ordner bzw. das NAS in den Container einbinden."
            )
        )
    if schreibtest:
        try:
            with tempfile.NamedTemporaryFile(dir=ziel, prefix=".nestwerk-test-"):
                pass
        except OSError:
            raise PfadFehler(
                _("In diesen Ordner kann Nestwerk nicht schreiben. Rechte des Ordners prüfen.")
            ) from None
    return ziel


def konfigurierter_pfad():
    """Der in der Einrichtung gewählte Speicherort oder ``""`` (= Docker-Volume)."""
    try:
        return wert("lernen.speicher_pfad")
    except EinstellungFehlt:
        return ""


class Speicher:
    def __init__(self, basis=None):
        if basis is None:
            basis = konfigurierter_pfad() or settings.LERNEN_SPEICHER_DIR
        self.basis = Path(basis).resolve()

    def kind_ordner(self, kind_id):
        # Konten haben UUID-Schlüssel; Ganzzahlen sind für Tests und andere Schlüsselarten erlaubt
        gueltig_int = isinstance(kind_id, int) and not isinstance(kind_id, bool) and kind_id >= 1
        if not (gueltig_int or isinstance(kind_id, UUID)):
            raise SpeicherFehler("Ungültige Kind-ID.")
        return self._innerhalb(self.basis, self.basis / f"kind_{kind_id}")

    def ordner(self, kind_id, bereich):
        if bereich not in BEREICHE:
            raise SpeicherFehler(f"Unbekannter Bereich: {bereich!r}")
        kind = self.kind_ordner(kind_id)
        return self._innerhalb(kind, kind / bereich)

    def pfad(self, kind_id, bereich, name):
        """Pfad einer Datei im Bereich. ``name`` ist ein reiner Dateiname."""
        if (
            not isinstance(name, str)
            or not name
            or name in (".", "..")
            or name.startswith(".")
            or "/" in name
            or "\\" in name
            or "\x00" in name
        ):
            raise SpeicherFehler("Ungültiger Dateiname.")
        ordner = self.ordner(kind_id, bereich)
        return self._innerhalb(ordner, ordner / name)

    def ordner_anlegen(self, kind_id):
        """Legt ``inbox``, ``archiv`` und ``tests`` des Kindes an (idempotent)."""
        for bereich in BEREICHE:
            self.ordner(kind_id, bereich).mkdir(parents=True, exist_ok=True)

    def belegt_bytes(self, kind_id):
        kind = self.kind_ordner(kind_id)
        if not kind.exists():
            return 0
        return sum(p.stat().st_size for p in kind.rglob("*") if p.is_file() and not p.is_symlink())

    def speichern(self, kind_id, bereich, name, daten, *, limit_bytes=None):
        """Schreibt ``daten`` (bytes). Überschreibt nie: gleicher Name -> ``FileExistsError``."""
        ziel = self.pfad(kind_id, bereich, name)
        if limit_bytes is not None and self.belegt_bytes(kind_id) + len(daten) > limit_bytes:
            raise SpeicherVoll("Das Speicherlimit ist erreicht.")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with open(ziel, "xb") as f:
            f.write(daten)
        return ziel

    def verschieben(self, kind_id, name, von, nach):
        """Verschiebt eine Datei zwischen Bereichen, z. B. ``inbox`` -> ``archiv``."""
        quelle = self.pfad(kind_id, von, name)
        ziel = self.pfad(kind_id, nach, name)
        if not quelle.is_file():
            raise FileNotFoundError(name)
        if ziel.exists():
            raise FileExistsError(name)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(quelle, ziel)
        return ziel

    def lesen(self, kind_id, bereich, name, *, max_bytes=None):
        """Inhalt einer Datei; ``FileNotFoundError``, wenn es sie nicht (als echte Datei) gibt."""
        ziel = self.pfad(kind_id, bereich, name)
        if not ziel.is_file():
            raise FileNotFoundError(name)
        with open(ziel, "rb") as f:
            return f.read() if max_bytes is None else f.read(max_bytes + 1)

    def inbox_dateien(self, kind_id):
        """Dateien, die direkt in ``inbox`` oder in einem Unterordner (Tiefe 1) liegen.

        Symlinks (Dateien wie Ordner), versteckte Namen und alles, was nach dem Auflösen nicht
        unter ``inbox`` liegt, werden übersprungen. Reihenfolge stabil (nach Pfad)."""
        inbox = self.ordner(kind_id, "inbox")
        if not inbox.is_dir():
            return []
        ergebnis = []

        def dateien(ordner, hinweis):
            for eintrag in sorted(ordner.iterdir(), key=lambda p: p.name):
                if eintrag.name.startswith("."):
                    continue
                if eintrag.is_symlink() or not eintrag.is_file():
                    continue
                try:
                    pfad = self._innerhalb(inbox, eintrag)
                    info = pfad.stat()
                except (SpeicherFehler, OSError):
                    continue
                ergebnis.append(
                    InboxDatei(pfad, hinweis, eintrag.name, info.st_size, info.st_mtime)
                )

        dateien(inbox, "")
        for unter in sorted(inbox.iterdir(), key=lambda p: p.name):
            if unter.is_dir() and not unter.is_symlink() and not unter.name.startswith("."):
                dateien(unter, unter.name)
        return ergebnis

    def uebernehmen(self, kind_id, quelle, bereich, name):
        """Verschiebt eine Datei aus ``inbox`` (``InboxDatei.pfad``) unter einem neuen, neutralen
        Namen in ``bereich``. Die Quelle muss eine echte Datei unter ``inbox`` sein."""
        inbox = self.ordner(kind_id, "inbox")
        quelle = Path(quelle)
        if quelle.is_symlink() or not quelle.is_file():
            raise FileNotFoundError(quelle.name)
        self._innerhalb(inbox, quelle)
        ziel = self.pfad(kind_id, bereich, name)
        if ziel.exists():
            raise FileExistsError(name)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(quelle, ziel)
        return ziel

    def loeschen(self, kind_id, bereich, name):
        """Löscht eine Datei; ``True``, wenn sie existierte."""
        ziel = self.pfad(kind_id, bereich, name)
        if ziel.is_file() or ziel.is_symlink():
            ziel.unlink()
            return True
        return False

    @staticmethod
    def _innerhalb(wurzel, pfad):
        """Löst Symlinks auf und verlangt, dass ``pfad`` unter ``wurzel`` liegt."""
        aufgeloest = pfad.resolve()
        if aufgeloest != wurzel and wurzel not in aufgeloest.parents:
            raise SpeicherFehler("Pfad liegt außerhalb des Kind-Ordners.")
        return aufgeloest
