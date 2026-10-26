"""Bibliothek (JSON-Dateien) -> Datenbank: Slots, Themen und Beispiel-Baupläne anlegen.

Die Dateien unter ``daten/`` sind die Vorlage (Seed). In der Datenbank können Eltern/Entwickler
später einzelne Zeilen anpassen; ein erneutes Laden überschreibt sie nur mit ``ueberschreiben``.
"""

import logging

from .generator import bauplaene, bibliothek
from .models import ModDefinition, Slot, Thema

logger = logging.getLogger(__name__)


def _thema_felder(t):
    return {
        "name": t["name"],
        "beschreibung": t.get("beschreibung", ""),
        "palette": t["palette"],
        "figur_varianten": list(bibliothek.figur()["frisuren"]),
        "bau_inszenierung": t["bau_inszenierung"],
        "nur_eltern": t["nur_eltern"],
        "aktiv": True,
        "reihenfolge": t["reihenfolge"],
        "daten": {k: t[k] for k in ("kleidung", "grundausstattung", "formen") if k in t},
    }


def bibliothek_laden(*, ueberschreiben=False):
    """Idempotent. Gibt ``{"slots": n, "themen": n, "mods": n}`` der neu angelegten/aktualisierten
    Zeilen zurück."""
    stand = {"slots": 0, "themen": 0, "mods": 0}
    for s in bibliothek.slots():
        _, neu = Slot.objects.update_or_create(
            schluessel=s["schluessel"], defaults={"name": s["name"], "ebene": s["ebene"]}
        )
        stand["slots"] += neu
    for t in bibliothek.themen().values():
        felder = _thema_felder(t)
        if ueberschreiben:
            _, geaendert = Thema.objects.update_or_create(
                schluessel=t["schluessel"], defaults=felder
            )
            stand["themen"] += 1
        else:
            _, geaendert = Thema.objects.get_or_create(schluessel=t["schluessel"], defaults=felder)
            stand["themen"] += geaendert
    themen = {t.schluessel: t for t in Thema.objects.all()}
    slots = {s.schluessel: s for s in Slot.objects.all()}
    for plan in bibliothek.bauplaene_aus_dateien():
        fehler = bauplaene.bauplan_pruefen(plan)
        if fehler:
            logger.warning("Bauplan %s übersprungen: %s", plan.get("schluessel"), "; ".join(fehler))
            continue
        felder = {
            "thema": themen[plan["thema"]],
            "slot": slots[plan["slot"]],
            "seltenheit": plan["seltenheit"],
            "name": plan["name"],
            "beschreibung": plan.get("beschreibung") or "",
            "preis": plan.get("preis"),
            "bauzeit_stunden": plan.get("bauzeit_stunden"),
            "bauplan": {"teile": plan["teile"]},
            "svg_override": plan.get("svg_override") or "",
        }
        if ueberschreiben:
            ModDefinition.objects.update_or_create(schluessel=plan["schluessel"], defaults=felder)
            stand["mods"] += 1
        else:
            _, neu = ModDefinition.objects.get_or_create(
                schluessel=plan["schluessel"], defaults=felder
            )
            stand["mods"] += neu
    from . import services

    services.hashes_aktualisieren()
    return stand
