"""Akzentfarben der Kinder. Die Palette spiegelt ``static/css/tokens.css`` (``data-akzent``):
Das Layout setzt den Namen am ``<body>``, das CSS liefert ``--akzent``. Farben außerhalb der
Palette werden nicht als Inline-Style ausgegeben (CSP ohne Inline-Styles), sondern fallen auf
den Standard zurück."""

STANDARD = "blau"

PALETTE = {
    "blau": "#2563eb",
    "rot": "#e5364a",
    "orange": "#ff8a2b",
    "gelb": "#ffd23f",
    "gruen": "#22c55e",
    "tuerkis": "#20d1c4",
    "lila": "#8b4dff",
    "pink": "#ff4fa0",
}

_NAMEN = {hex_: name for name, hex_ in PALETTE.items()}


def name_zu_hex(name):
    return PALETTE[name]


def hex_zu_name(farbe):
    return _NAMEN.get(str(farbe).lower())


def akzent_name(benutzer):
    """Name der ersten gewählten Akzentfarbe (für ``data-akzent``) oder der Standard."""
    for farbe in getattr(benutzer, "akzentfarben", None) or []:
        name = hex_zu_name(farbe)
        if name:
            return name
    return STANDARD
