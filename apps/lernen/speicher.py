"""Speicher-Backend der Lernmappe (SPEC 21.5): Ordner ``inbox``, ``archiv`` und ``tests`` je Kind.

Der Basispfad kommt aus ``settings.LERNEN_SPEICHER_DIR`` (Standard: Docker-Volume unter
``DATA_DIR/lernen``) und lässt sich auf einen gemounteten Pfad (z. B. NAS) umstellen. Ordner
heißen nach der Kind-ID (``kind_<id>``, Konten-ID als UUID), nie nach dem Namen. Jeder Pfad
wird aufgelöst und muss unter dem Ordner des Kindes liegen; Dateinamen sind reine Namen
(kein ``/``, kein ``..``).
Noch ohne Upload-Oberfläche und ohne Verarbeitung (Etappe 1).
"""

import shutil
from pathlib import Path
from uuid import UUID

from django.conf import settings

BEREICHE = ("inbox", "archiv", "tests")


class SpeicherFehler(Exception):
    """Unzulässiger Pfad, Dateiname oder Bereich."""


class SpeicherVoll(SpeicherFehler):
    """Das Speicherlimit des Kindes wäre überschritten."""


class Speicher:
    def __init__(self, basis=None):
        self.basis = Path(basis if basis is not None else settings.LERNEN_SPEICHER_DIR).resolve()

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
