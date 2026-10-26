"""Lesende Schnittstelle von avatar (andere Apps importieren nur selectors/services/tags).

AP26 (Logik in ``mods``): ``ausbaustufe(kind)`` (``.aktuell``, ``.je_seltenheit``,
``.wartend``), ``shop(kind)``, ``bauauftraege(kind)``, ``eigene_fertige(kind)``,
``mod_konditionen(mod, kind)``, ``eltern_uebersicht()``, ``mod_standards()``,
``inszenierung(thema)``, ``mod(schluessel)``.
"""

from .generator import bibliothek
from .models import Avatar, ModDefinition, Thema
from .mods import (  # noqa: F401 (öffentliche Mod-API, AP26)
    ausbaustufe,
    bauauftraege,
    eigene_fertige,
    eltern_uebersicht,
    inszenierung,
    shop,
)
from .mods import konditionen as mod_konditionen  # noqa: F401
from .mods import standards as mod_standards  # noqa: F401
from .ruhmeshalle import (  # noqa: F401 (Ruhmeshalle, P3-A)
    anzahl as ruhmeshalle_anzahl,
)
from .ruhmeshalle import bereitschaft as ruhmeshalle_bereitschaft  # noqa: F401
from .ruhmeshalle import eintraege as ruhmeshalle_eintraege  # noqa: F401
from .ruhmeshalle import je_kind as ruhmeshalle_je_kind  # noqa: F401
from .ruhmeshalle import mit_bild as ruhmeshalle_mit_bild  # noqa: F401


def mod(schluessel):
    return (
        ModDefinition.objects.select_related("slot", "thema").filter(schluessel=schluessel).first()
    )


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
