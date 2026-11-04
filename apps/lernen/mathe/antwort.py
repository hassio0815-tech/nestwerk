"""Eingaben zu Mathe-Aufgaben lesen und prüfen (SPEC 21.13). Rein rechnend, ohne Datenbank.

Gelesen werden: ganze Zahlen und Dezimalzahlen (Komma oder Punkt, Tausendertrennung, führende und
abschließende Nullen), Brüche ``3/4``, gemischte Zahlen ``1 1/2``, Rest-Schreibweise ``17 R 2``,
Gleichungsergebnisse ``x = 5``, Prozent ``25 %``, optionale Einheiten und kleine Terme.
Das Ergebnis ist richtig, "fast" (Wert stimmt, Schreibweise noch nicht: z. B. nicht gekürzt) oder
falsch, dazu ein optionaler Fehlertyp (Platzhalter für die Fehleranalyse in Paket 2).
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from math import gcd

from django.utils.translation import gettext as _

from . import term
from .aufgabe import BRUCH, DEZIMAL, GANZ, GEMISCHT, GLEICHUNG, REST, TERM, Loesung

MAX_EINGABE = 80

# Fehlertypen (Platzhalter; die Auswertung folgt in Paket 2)
NICHT_GEKUERZT = "nicht_gekuerzt"
FALSCHE_FORM = "form"
EINHEIT = "einheit"
REST_FEHLT = "rest_fehlt"
UNLESBAR = "unlesbar"
VARIABLE = "variable"
NICHT_VEREINFACHT = "nicht_vereinfacht"

EINHEITEN = {
    "€": "€",
    "eur": "€",
    "euro": "€",
    "ct": "ct",
    "cent": "ct",
    "mm": "mm",
    "cm": "cm",
    "zentimeter": "cm",
    "millimeter": "mm",
    "kilometer": "km",
    "m": "m",
    "km": "km",
    "meter": "m",
    "g": "g",
    "kg": "kg",
    "t": "t",
    "gramm": "g",
    "kilogramm": "kg",
    "ml": "ml",
    "l": "l",
    "liter": "l",
    "min": "min",
    "minuten": "min",
    "minute": "min",
    "h": "h",
    "std": "h",
    "stunden": "h",
    "stunde": "h",
    "tage": "Tage",
    "tag": "Tage",
    "m²": "m²",
    "cm²": "cm²",
    "m2": "m²",
    "cm2": "cm²",
}


@dataclass(frozen=True)
class Befund:
    richtig: bool
    fast: bool = False
    hinweis: str = ""  # Text für das Kind bei "fast" (und bei klaren Formfehlern)
    fehlertyp: str = ""


FALSCH = Befund(False)
RICHTIG = Befund(True)


@dataclass(frozen=True)
class Gelesen:
    """Eine gelesene Zahl: mögliche Werte (mit Form), Einheit, Prozentzeichen, Kürzung."""

    kandidaten: tuple  # Paare (Fraction, Form)
    einheit: str = ""
    prozent: bool = False
    gekuerzt: bool = True


# --- Zahlen lesen --------------------------------------------------------------------------------

_GRUPPEN_LEER = re.compile(r"^\d{1,3}(?: \d{3})+(?:,\d+)?$")
_GANZ = re.compile(r"^\d+$")
_DEZ = re.compile(r"^\d+[.,]\d+$")
_PUNKT_TAUSEND = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_KOMMA_TAUSEND = re.compile(r"^\d{1,3}(?:,\d{3})+$")
_PUNKT_TAUSEND_KOMMA = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d+$")
_KOMMA_TAUSEND_PUNKT = re.compile(r"^\d{1,3}(?:,\d{3})+\.\d+$")


def zahl_kandidaten(text):
    """Alle sinnvollen Lesarten einer vorzeichenlosen Zahl als Liste ``(Fraction, Form)``.
    ``1.000`` kann Tausend oder eins sein (die Prüfung nimmt, was zur Aufgabe passt)."""
    s = text.strip().replace("'", " ").replace("’", " ")
    s = re.sub(r"\s+", " ", s)
    if _GRUPPEN_LEER.match(s):
        s = s.replace(" ", "")
    if " " in s:
        return []
    if _GANZ.match(s):
        return [(Fraction(int(s)), GANZ)]
    if _PUNKT_TAUSEND_KOMMA.match(s):
        return [(Fraction(s.replace(".", "").replace(",", ".")), DEZIMAL)]
    if _KOMMA_TAUSEND_PUNKT.match(s):
        return [(Fraction(s.replace(",", "")), DEZIMAL)]
    ergebnis = []
    if _PUNKT_TAUSEND.match(s) and not s.startswith("0"):
        ergebnis.append((Fraction(int(s.replace(".", ""))), GANZ))
    if _KOMMA_TAUSEND.match(s) and not s.startswith("0"):
        ergebnis.append((Fraction(int(s.replace(",", ""))), GANZ))
    if _DEZ.match(s):
        ergebnis.append((Fraction(s.replace(",", ".")), DEZIMAL))
    return ergebnis


_GEMISCHT = re.compile(r"^(\d+)\s+(\d+)\s*[/⁄]\s*(\d+)$")
_BRUCH = re.compile(r"^(\d+)\s*[/⁄]\s*(\d+)$")
_REST = re.compile(r"^(\d+)\s*(?:r|rest)\s*(\d+)$", re.IGNORECASE)
_GLEICH_VOR = re.compile(r"^([a-z])\s*=\s*(.+)$", re.IGNORECASE)
_GLEICH_NACH = re.compile(r"^(.+?)\s*=\s*([a-z])$", re.IGNORECASE)
_ZAHLTEIL = re.compile(r"^([\d.,/⁄'’ ]*\d(?:\s*[/⁄]\s*\d+)?)\s*([^\d].*)?$")


def _normieren(text):
    s = str(text).strip()[: MAX_EINGABE * 2]
    s = s.replace("−", "-").replace("–", "-").replace(" ", " ").replace(" ", " ")
    return " ".join(s.split())


def _vorzeichen(s):
    """Trennt ein führendes Vorzeichen ab: ``("-", "5")``."""
    if s[:1] in "+-" and s[:1]:
        return (-1 if s[0] == "-" else 1), s[1:].strip()
    return 1, s


def _einheit_lesen(rest):
    """Normierte Einheit aus dem Rest hinter der Zahl; ``None`` wenn unbekannt."""
    schluessel = rest.strip().strip(".").casefold()
    return EINHEITEN.get(schluessel)


def _zahl_lesen(s):
    """Zahl mit optionaler Einheit und optionalem Prozentzeichen; ``None`` wenn unlesbar."""
    vorzeichen, s = _vorzeichen(s)
    prozent = False
    einheit = ""
    if s.endswith("%"):
        prozent, s = True, s[:-1].strip()
    elif s.casefold().endswith("prozent"):
        prozent, s = True, s[: -len("prozent")].strip()
    if not prozent:
        m = _ZAHLTEIL.match(s)
        if m is None:
            return None
        s, rest = m.group(1).strip(), (m.group(2) or "").strip()
        if rest:
            einheit = _einheit_lesen(rest)
            if einheit is None:
                return None
    gemischt = _GEMISCHT.match(s)
    if gemischt:
        g, z, n = (int(x) for x in gemischt.groups())
        if n == 0 or z >= n:
            return None  # Gemischte Zahlen haben einen echten Bruchteil
        gekuerzt = gcd(z, n) == 1
        return Gelesen(
            ((vorzeichen * Fraction(g * n + z, n), GEMISCHT),), einheit, prozent, gekuerzt
        )
    bruch = _BRUCH.match(s)
    if bruch:
        z, n = (int(x) for x in bruch.groups())
        if n == 0:
            return None
        return Gelesen(((vorzeichen * Fraction(z, n), BRUCH),), einheit, prozent, gcd(z, n) == 1)
    kandidaten = zahl_kandidaten(s)
    if not kandidaten:
        return None
    return Gelesen(tuple((vorzeichen * w, f) for w, f in kandidaten), einheit, prozent)


def lesen(text):
    """Liest eine Zahl-Eingabe (ohne Rest/Gleichung/Term); ``None`` wenn unlesbar."""
    return _zahl_lesen(_normieren(text))


# --- Prüfen ---------------------------------------------------------------------------------------


def pruefen(gegeben, loesung):
    """Prüft die Eingabe gegen eine ``Loesung`` (oder deren ``dict``)."""
    if isinstance(loesung, dict):
        loesung = Loesung.from_dict(loesung)
    s = _normieren(gegeben)
    if not s or len(s) > MAX_EINGABE:
        return FALSCH
    if loesung.form == TERM:
        return _pruefen_term(s, loesung)
    if loesung.form == REST:
        return _pruefen_rest(s, loesung)
    if loesung.form == GLEICHUNG:
        return _pruefen_gleichung(s, loesung)
    return _pruefen_zahl(s, loesung)


def _pruefen_zahl(s, loesung):
    gelesen = _zahl_lesen(s)
    if gelesen is None:
        return Befund(False, fehlertyp=UNLESBAR)
    soll = loesung.als_bruch()
    treffer = [(w, f) for w, f in gelesen.kandidaten if w == soll]
    if not treffer:
        return FALSCH
    # der Wert stimmt; jetzt Einheit, Prozentzeichen, Form und Kürzung
    if loesung.einheit and gelesen.einheit and gelesen.einheit != loesung.einheit:
        return Befund(False, fehlertyp=EINHEIT)
    if gelesen.prozent and not loesung.prozent:
        return Befund(False, fehlertyp=EINHEIT)
    formen = [f for _w, f in treffer if f in loesung.erlaubt]
    if not formen:
        text = (
            _("Der Wert stimmt. Schreibe das Ergebnis als Bruch.")
            if BRUCH in loesung.erlaubt or GEMISCHT in loesung.erlaubt
            else _("Der Wert stimmt. Schreibe das Ergebnis als Zahl, z. B. mit Komma.")
        )
        return Befund(False, True, text, FALSCHE_FORM)
    if loesung.kuerzen and not gelesen.gekuerzt:
        return Befund(False, True, _("Fast: Der Bruch lässt sich noch kürzen."), NICHT_GEKUERZT)
    return RICHTIG


def _pruefen_rest(s, loesung):
    m = _REST.match(s)
    if m:
        q, r = int(m.group(1)), int(m.group(2))
        if q == loesung.als_bruch() and r == loesung.rest:
            return RICHTIG
        return FALSCH
    gelesen = _zahl_lesen(s)
    if gelesen is not None and any(w == loesung.als_bruch() for w, _f in gelesen.kandidaten):
        return Befund(False, True, _("Fast: Vergiss den Rest nicht, z. B. 17 R 2."), REST_FEHLT)
    return Befund(False, fehlertyp=UNLESBAR) if gelesen is None else FALSCH


def _pruefen_gleichung(s, loesung):
    var = ""
    m = _GLEICH_VOR.match(s) or _GLEICH_NACH.match(s)
    if m:
        if _GLEICH_VOR.match(s):
            var, s = m.group(1).casefold(), m.group(2)
        else:
            s, var = m.group(1), m.group(2).casefold()
    gelesen = _zahl_lesen(s)
    if gelesen is None:
        return Befund(False, fehlertyp=UNLESBAR)
    if not any(w == loesung.als_bruch() for w, _f in gelesen.kandidaten):
        return FALSCH
    if var and var != loesung.variable:
        return Befund(False, fehlertyp=VARIABLE)
    return RICHTIG


def _pruefen_term(s, loesung):
    try:
        eingabe = term.lesen(s)
    except term.TermFehler:
        return Befund(False, fehlertyp=UNLESBAR)
    if not term.gleich(eingabe, term.lesen(loesung.term)):
        return FALSCH
    if loesung.vereinfacht:
        soll = len(term.lesen(loesung.term))
        if term.hat_klammern(s) or term.summanden(s) > max(soll, 1):
            return Befund(
                False,
                True,
                _("Fast: Der Term stimmt, ist aber noch nicht ganz vereinfacht."),
                NICHT_VEREINFACHT,
            )
    return RICHTIG
