"""Lesende Schnittstelle von avatar (andere Apps importieren nur selectors/services/tags)."""

from .generator import bibliothek
from .models import Avatar, ModDefinition, Thema


def avatar_von(benutzer):
    return Avatar.objects.select_related("thema").filter(pk=benutzer.pk).first()


def hat_avatar(benutzer):
    return Avatar.objects.filter(pk=benutzer.pk).exists()


def waehlbare_themen():
    """Aktive Kinder-Themen in Reihenfolge."""
    return list(Thema.objects.filter(aktiv=True, nur_eltern=False))


def figur_optionen():
    """Wählbare Hautfarben, Haarfarben und Frisuren für die Auswahl."""
    lib = bibliothek.figur()
    return {
        "haut": [(k, v["name"], v["farbe"]) for k, v in lib["hautfarben"].items()],
        "haar": [(k, v["name"], v["farbe"]) for k, v in lib["haarfarben"].items()],
        "frisur": [(k, v["name"]) for k, v in lib["frisuren"].items()],
    }


def angelegte_mods(avatar):
    """``{slot: ModDefinition}`` der angelegten Mods eines Avatars."""
    if not avatar.angelegt:
        return {}
    mods = ModDefinition.objects.filter(schluessel__in=avatar.angelegt.values()).select_related(
        "slot"
    )
    nach_schluessel = {m.schluessel: m for m in mods}
    return {
        slot: nach_schluessel[schluessel]
        for slot, schluessel in avatar.angelegt.items()
        if schluessel in nach_schluessel
    }
