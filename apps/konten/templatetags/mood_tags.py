from django import template

from apps.konten import moods
from apps.konten.models import WappenRolle

register = template.Library()


@register.simple_tag
def eltern_mood_katalog():
    return moods.KATALOG_ELTERN


@register.filter
def mood_kurz(benutzer):
    """``🐉 Hausdrache`` für Eltern mit Mood, sonst leer (kurz, für Kinder-Texte)."""
    m = getattr(benutzer, "mood_info", None)
    return m.anzeige if m else ""


@register.simple_tag
def mood_rollen():
    return WappenRolle.choices


@register.simple_tag
def eltern_mood_auswahl(benutzer):
    """Auswahl für die Eltern-Einstellungen: gruppierte Moods, aktuelle Wahl, Spruch."""
    from apps.konten import selectors

    gruppen = selectors.mood_gruppen(moods.ELTERN)
    gueltig = {s for g in gruppen for s, _t in g["moods"]}
    aktuell = benutzer.mood if benutzer.mood in gueltig else ""
    info = benutzer.mood_info if aktuell else None
    return {"gruppen": gruppen, "aktuell": aktuell, "spruch": info.spruch if info else ""}
