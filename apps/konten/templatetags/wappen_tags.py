from django import template

from apps.konten import wappen
from apps.konten.models import WappenRolle

register = template.Library()


@register.simple_tag
def wappen_katalog():
    return wappen.KATALOG


@register.filter
def wappen_kurz(benutzer):
    """``🐉 Hausdrache`` für Eltern mit Wappen, sonst leer (kurz, für Kinder-Texte)."""
    w = getattr(benutzer, "wappen_info", None)
    return f"{w.emoji} {w.titel}" if w else ""


@register.simple_tag
def wappen_rollen():
    return WappenRolle.choices
