"""Startdaten von lernen (SPEC 21.11): generisch, ohne Bezug zu einer Familie.

- Fach ``englisch``: Themen und Vokabeln je Klassenstufe (3, 6, 8) aus ``englisch_vokabeln.json``.
- Fach ``mathe``: die Themenstruktur je Klassenstufe, keine gespeicherten Fragen. Die Aufgaben
  erzeugt der Generator (``apps/lernen/mathe``, SPEC 21.13); ``mathe_themen_anlegen`` verbindet die
  Themen mit ihm.

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


# Themen, die zu Mathe-Generatoren gehören (SPEC 21.13): Schlüssel -> (Klassenstufe, Name, Platz).
# Bestehende Themen (gleicher Name und Stufe) bekommen nur den Schlüssel; Neues kommt dazu.
MATHE_GENERATOR_THEMEN = {
    "mathe_3_plusminus": (3, _("Addition und Subtraktion"), 1),
    "mathe_3_einmaleins": (3, _("Einmaleins"), 2),
    "mathe_3_groessen": (3, _("Größen und Messen"), 4),
    "mathe_6_schriftlich": (6, _("Schriftliches Rechnen"), 5),
    "mathe_6_brueche": (6, _("Brüche"), 0),
    "mathe_6_dezimal": (6, _("Dezimalzahlen"), 1),
    "mathe_6_prozent": (6, _("Prozentrechnung"), 2),
    "mathe_6_groessen": (6, _("Größen und Einheiten"), 4),
    "mathe_6_rechengesetze": (6, _("Rechengesetze und Klammern"), 6),
    "mathe_8_terme": (8, _("Terme und Gleichungen"), 0),
    "mathe_8_prozent": (8, _("Prozent und Zinsen"), 2),
    "mathe_8_dreisatz": (8, _("Dreisatz"), 5),
    "mathe_8_potenzen": (8, _("Potenzen und Wurzeln"), 6),
    "mathe_8_negativ": (8, _("Rechnen mit negativen Zahlen"), 7),
}


def mathe_themen_anlegen(Fach, Thema):
    """Verbindet die Mathe-Themen mit den Generatoren. Idempotent und rein additiv: Vorhandenes
    behält Name und Fragen, bekommt nur den Schlüssel; fehlende Themen werden angelegt."""
    fach, _neu = Fach.objects.get_or_create(
        schluessel="mathe", defaults={"name": _("Mathe"), "reihenfolge": 2}
    )
    for schluessel, (klasse, name, platz) in MATHE_GENERATOR_THEMEN.items():
        if Thema.objects.filter(fach=fach, schluessel=schluessel).exists():
            continue
        thema = Thema.objects.filter(fach=fach, klassenstufe=klasse, name=name).first()
        if thema is None:
            thema = Thema(fach=fach, klassenstufe=klasse, name=name, reihenfolge=platz)
        thema.schluessel = schluessel
        thema.save()
