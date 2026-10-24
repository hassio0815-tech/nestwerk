"""Farbangaben der Teile-Bibliothek.

Eine Farbangabe ist ``#rrggbb`` oder ein Token (``p1``..``p6``, ``haut``, ``haar``,
``a``/``b``/``c``)
mit optionalem Helligkeits-Zusatz (``+``/``++`` heller, ``-``/``--`` dunkler) und optionaler
Deckkraft in Prozent (``@40``). Rechnung nur mit ganzen Zahlen (deterministisch).
"""

import re

FARBE_RE = re.compile(
    r"^(?:#([0-9a-fA-F]{6})|([a-z][a-z0-9]{0,11}))(\+\+|\+|--|-)?(?:@(\d{1,3}))?$"
)
_HELLER = {"+": 22, "++": 45}
_DUNKLER = {"-": 22, "--": 42}


class FarbFehler(ValueError):
    pass


def hex_zu_rgb(text):
    return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def rgb_zu_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


def heller(farbe, prozent):
    r, g, b = hex_zu_rgb(farbe)
    return rgb_zu_hex(*(c + (255 - c) * prozent // 100 for c in (r, g, b)))


def dunkler(farbe, prozent):
    r, g, b = hex_zu_rgb(farbe)
    return rgb_zu_hex(*(c * (100 - prozent) // 100 for c in (r, g, b)))


def aufloesen(angabe, scope):
    """``(hex, deckkraft_prozent)`` zu einer Farbangabe; ``scope``: Token -> ``#rrggbb``."""
    treffer = FARBE_RE.match(angabe) if isinstance(angabe, str) else None
    if not treffer:
        raise FarbFehler(f"Ungültige Farbangabe: {angabe!r}")
    roh, token, zusatz, alpha = treffer.groups()
    if roh:
        farbe = "#" + roh.lower()
    else:
        farbe = scope.get(token)
        if farbe is None:
            raise FarbFehler(f"Unbekanntes Farb-Token: {token!r}")
    if zusatz in _HELLER:
        farbe = heller(farbe, _HELLER[zusatz])
    elif zusatz in _DUNKLER:
        farbe = dunkler(farbe, _DUNKLER[zusatz])
    prozent = 100 if alpha is None else int(alpha)
    if not 1 <= prozent <= 100:
        raise FarbFehler(f"Deckkraft muss 1-100 sein: {angabe!r}")
    return farbe, prozent
