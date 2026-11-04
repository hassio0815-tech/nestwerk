"""Anzeige von Rechnungen: kein Zeilenumbruch mitten in einer Rechnung."""

import re

from django import template

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
