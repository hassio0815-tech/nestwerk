"""Teile-Bibliothek: JSON-Daten unter ``apps/avatar/daten`` (Code-Assets, versioniert).

* ``slots.json``: die 6 Slots mit Render-Ebene (Figur liegt dazwischen).
* ``figur.json``: Grundfigur (Blöcke), Hautfarben, Haarfarben, Frisuren, Gesicht.
* ``schablonen/<slot>.json``: Formen je Slot (Ebenen-Schablonen, Farbtokens ``a``/``b``/``c``).
* ``themen.json``: 10 Themen plus Eltern-Figur (Palette, Grundausstattung, Formen-Vorlieben).

Neue Themen oder Formen sind reine Daten. ``VERSION`` (Hash über alle Dateien) fließt in den
Render-Hash ein, damit der Cache nach jeder Änderung der Bibliothek ungültig wird.
"""

import hashlib
import json
from functools import cache
from pathlib import Path

DATEN = Path(__file__).resolve().parent.parent / "daten"
MUSTER = ("keins", "kante", "streifen", "punkte", "karo", "glanz")
STANDARD_FIGUR = {"haut": "haut2", "haar": "haar3", "frisur": "kurz"}
ELTERN_THEMA = "eltern"
ELTERN_HAUT = ("haut1", "haut2", "haut3", "haut4", "haut5", "haut6")
ELTERN_HAAR = ("haar1", "haar2", "haar3", "haar4", "haar5", "haar6")


def _lesen(pfad):
    return json.loads(Path(pfad).read_text(encoding="utf-8"))


@cache
def _alles():
    slots = _lesen(DATEN / "slots.json")
    figur = _lesen(DATEN / "figur.json")
    themen = {t["schluessel"]: t for t in _lesen(DATEN / "themen.json")["themen"]}
    schablonen = {}
    for slot in slots["slots"]:
        daten = _lesen(DATEN / "schablonen" / f"{slot['schluessel']}.json")
        schablonen[slot["schluessel"]] = daten["formen"]
    sha = hashlib.sha256()
    for pfad in sorted(p for p in DATEN.rglob("*.json") if "bauplaene" not in p.parts):
        sha.update(pfad.relative_to(DATEN).as_posix().encode())
        sha.update(pfad.read_bytes())
    return {
        "slots": slots,
        "figur": figur,
        "themen": themen,
        "schablonen": schablonen,
        "version": sha.hexdigest()[:16],
    }


def version():
    return _alles()["version"]


def slots():
    """Slots in Render-Reihenfolge (aufsteigende Ebene)."""
    return sorted(_alles()["slots"]["slots"], key=lambda s: s["ebene"])


def slot_schluessel():
    return tuple(s["schluessel"] for s in slots())


def figur_ebene():
    return _alles()["slots"]["figur_ebene"]


def figur():
    return _alles()["figur"]


def themen():
    return _alles()["themen"]


def thema(schluessel):
    try:
        return _alles()["themen"][schluessel]
    except KeyError:
        raise KeyError(f"Unbekanntes Thema: {schluessel!r}") from None


def kind_themen():
    """Die wählbaren Kinder-Themen in Reihenfolge."""
    return [
        t for t in sorted(themen().values(), key=lambda t: t["reihenfolge"]) if not t["nur_eltern"]
    ]


def formen(slot):
    return _alles()["schablonen"][slot]


def form(slot, schluessel):
    try:
        return formen(slot)[schluessel]
    except KeyError:
        raise KeyError(f"Unbekannte Form {schluessel!r} für Slot {slot!r}") from None


def bauplan_dateien():
    return sorted((DATEN / "bauplaene").glob("*.json"))


def bauplaene_aus_dateien():
    """Alle Baupläne der Dateien als Liste (Reihenfolge: Dateiname, Eintrag)."""
    ergebnis = []
    for pfad in bauplan_dateien():
        ergebnis += _lesen(pfad)["bauplaene"]
    return ergebnis
