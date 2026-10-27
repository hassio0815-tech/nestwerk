"""Template-Tags: ``{% load avatar_tags %}``.

``{% avatar_bild benutzer "mittel" %}``: Figur inline als SVG (kein Netzwerkzugriff, CSP-konform).
``{% avatar_url benutzer %}``: URL des Bildes (für ``<img>``).
Größen: klein, mittel, gross, riesig.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from apps.kern import sprache

from .. import services

register = template.Library()


KOPF_AUSSCHNITT = 'viewBox="4 2 24 24"'


def _ausschnitt(svg, groesse):
    """Inline-Variante: ohne ``xmlns`` (im HTML überflüssig, und die Seite bleibt frei von
    URLs). Kleine Ansichten zeigen nur Kopf und Schultern (ganze Figur wäre unleserlich)."""
    svg = svg.replace(' xmlns="http://www.w3.org/2000/svg"', "", 1)
    if groesse == "klein":
        return svg.replace('viewBox="0 0 32 48"', KOPF_AUSSCHNITT, 1)
    return svg


@register.simple_tag
def avatar_bild(benutzer, groesse="mittel"):
    _, svg = services.svg_fuer(benutzer)
    svg = _ausschnitt(svg, groesse)
    return format_html(
        '<span class="avatar-bild avatar-bild--{}" role="img" aria-label="{}">{}</span>',
        groesse,
        gettext("Avatar von %(name)s") % {"name": benutzer.anzeigename},
        mark_safe(svg),  # noqa: S308  (eigener, deterministischer Renderer-Output)
    )


@register.simple_tag
def avatar_url(benutzer):
    return services.bild_url(benutzer)


@register.simple_tag
def svg_roh(svg, groesse="mittel", beschriftung=""):
    """Schon gerendertes SVG (Vorschau/Galerie) im selben Rahmen wie ``avatar_bild``."""
    return format_html(
        '<span class="avatar-bild avatar-bild--{}" role="img" aria-label="{}">{}</span>',
        groesse,
        beschriftung,
        mark_safe(_ausschnitt(svg, groesse)),  # noqa: S308
    )


@register.filter
def avatar_name(benutzer):
    """``{{ kind|avatar_name }}``: Figurenname, sonst Name des Kindes."""
    return services.avatar_name(benutzer)


@register.filter
def uebersetzt(text):
    """``{{ mod.name|uebersetzt }}``: Namen aus den Avatar-Daten (JSON/DB) in der Sprache des
    Benutzers. Unbekannte Texte (z. B. von Eltern geänderte Namen) bleiben unverändert."""
    return sprache.uebersetzt(text)
