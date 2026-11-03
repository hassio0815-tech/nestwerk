"""Startdaten von lernen (SPEC 21.11): generisch, ohne Bezug zu einer Familie.

- Fach ``englisch``: Themen und Vokabeln je Klassenstufe (3, 6, 8) aus ``englisch_vokabeln.json``.
- Fach ``mathe``: nur die Themenstruktur je Klassenstufe, keine Fragen.

Namen sind mit ``gettext_noop`` markiert (docs/i18n.md) und werden erst bei der Anzeige
übersetzt (``kern.sprache.uebersetzt``). ``anlegen`` ist idempotent und überschreibt nichts.
"""

import json
from pathlib import Path

from django.utils.translation import gettext_noop as _

DATEI = Path(__file__).with_name("englisch_vokabeln.json")

FAECHER = (
    ("englisch", _("Englisch"), 1),
    ("mathe", _("Mathe"), 2),
)

# Die JSON-Datei nennt die Themen englisch; angezeigt werden deutsche Namen.
ENGLISCH_THEMEN = {
    "Numbers (0-20)": _("Zahlen (0-20)"),
    "Colors": _("Farben"),
    "School": _("Schule"),
    "Family": _("Familie"),
    "Animals": _("Tiere"),
    "Food": _("Essen und Trinken"),
    "Sports": _("Sport"),
    "Weather": _("Wetter und Naturereignisse"),
    "House": _("Haus und Wohnen"),
    "Technology": _("Technik"),
    "Nature": _("Natur"),
    "Travel": _("Reisen und Verkehr"),
    "Hobbies": _("Freizeit und Hobbys"),
}

MATHE_THEMEN = {
    "3": (
        _("Zahlen bis 1000"),
        _("Addition und Subtraktion"),
        _("Einmaleins"),
        _("Geometrische Formen"),
        _("Größen und Messen"),
    ),
    "6": (
        _("Brüche"),
        _("Dezimalzahlen"),
        _("Prozentrechnung"),
        _("Umfang und Flächeninhalt"),
        _("Größen und Einheiten"),
    ),
    "8": (
        _("Terme und Gleichungen"),
        _("Lineare Funktionen"),
        _("Prozent und Zinsen"),
        _("Satz des Pythagoras"),
        _("Wahrscheinlichkeit"),
    ),
}


def anlegen(Fach, Thema, Frage):
    """Legt Fächer, Themen und Vokabeln an. Modelle: historisch (Migration) oder echt."""
    faecher = {}
    for schluessel, name, reihenfolge in FAECHER:
        faecher[schluessel], _neu = Fach.objects.get_or_create(
            schluessel=schluessel, defaults={"name": name, "reihenfolge": reihenfolge}
        )
    daten = json.loads(DATEI.read_text(encoding="utf-8"))
    for klasse, inhalt in daten.items():
        themen = {}
        for nr, thema in enumerate(inhalt["themen"]):
            themen[thema], _neu = Thema.objects.get_or_create(
                fach=faecher["englisch"],
                klassenstufe=int(klasse),
                name=ENGLISCH_THEMEN[thema],
                defaults={"reihenfolge": nr},
            )
        for v in inhalt["vokabeln"]:
            Frage.objects.get_or_create(
                thema=themen[v["thema"]],
                typ="vokabel",
                frage=v["de"],
                antwort=v["en"],
                defaults={"quelle": "system", "freigabe": "freigegeben"},
            )
    for klasse, namen in MATHE_THEMEN.items():
        for nr, name in enumerate(namen):
            Thema.objects.get_or_create(
                fach=faecher["mathe"],
                klassenstufe=int(klasse),
                name=name,
                defaults={"reihenfolge": nr},
            )
