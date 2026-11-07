"""Anzeige von Rechnungen: kein Zeilenumbruch mitten in einer Rechnung."""

import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()

NBSP = " "
# Mal und Geteilt (mit Leerzeichen auf beiden Seiten) kleben die Zahlen links und rechts fest;
# vor "=", "+" und "−" steht ein festes Leerzeichen (kein Zeichen allein am Zeilenanfang).
_MAL_GETEILT = re.compile(r"(?<=\S) ([·:×]) (?=\S)")
_VOR_ZEICHEN = re.compile(r"(?<=\S) (?=[=+−]\s)")


@register.filter
def rechnung(text):
    """Setzt feste Leerzeichen in Rechnungen wie ``2 · 4 + 3 = 11`` (Satzzeichen bleiben)."""
    text = str(text)
    text = _MAL_GETEILT.sub(NBSP + r"\1" + NBSP, text)
    return _VOR_ZEICHEN.sub(NBSP, text)


# Brüche wie ``20/24`` oder ``1 3/4`` stehen untereinander wie in der Schule (Zähler blau, Nenner
# rot, wenn der Rahmen ``lernen-rechenweg`` sie einfärbt); Screenreader lesen ``20/24``.
_BRUCH = re.compile(r"(?<![\d/])(\d+)/(\d+)(?![\d/])")


def _bruch_html(treffer):
    zaehler, nenner = treffer.group(1), treffer.group(2)
    return (
        f'<span class="bruch" role="math" aria-label="{zaehler}/{nenner}">'
        f'<span class="bruch__z" aria-hidden="true">{zaehler}</span>'
        f'<span class="bruch__n" aria-hidden="true">{nenner}</span></span>'
    )


@register.filter
def schulrechnung(text):
    """Wie ``rechnung``, aber Brüche gestapelt. Der Text wird zuerst maskiert (kein HTML aus
    Aufgabentexten); eingesetzt wird nur das feste Bruch-Gerüst mit Ziffern."""
    return mark_safe(_BRUCH.sub(_bruch_html, str(conditional_escape(rechnung(text)))))  # noqa: S308
