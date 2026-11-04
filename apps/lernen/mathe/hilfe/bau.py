"""Bausteine der Mathe-Hilfe (SPEC 21.13, Etappe 10b): Datentypen, Zahlen schreiben, Leck-Prüfung.

Reine Funktionen ohne Datenbank und ohne KI. Eine ``Hilfe`` beschreibt EINE Aufgabe aus ihren
gespeicherten Zahlen: was gegeben und gesucht ist, einen Denkanstoß und ein Schrittgerüst. Ein
``Schritt`` kennt seine Zwischenergebnisse; bei der echten Aufgabe werden sie nie gezeigt (``___``),
beim analogen Beispiel mit anderen Zahlen schon.

Namenskonvention in den Vorlagen: Platzhalter, die mit ``r`` beginnen (``%(r)s``, ``%(r1)s``,
``%(rest)s``), sind Ergebnisse, Zwischenergebnisse oder Rechenkonstanten, die sich daraus ergeben;
sie werden im offenen Gerüst durch ``___`` ersetzt. Alle anderen sind Zahlen der Aufgabe.
"""

import re
from dataclasses import dataclass, field
from fractions import Fraction

from ..aufgabe import GLEICHUNG, REST, TERM, ZAHL
from ..bausteine import bruch_text, ist_endlich, zahl_text

LUECKE = "___"


def z(q, stellen=None):
    """Zahl für einen Hilfetext: ganz oder Dezimalzahl mit Komma, sonst als Bruch."""
    q = Fraction(q)
    if ist_endlich(q):
        return zahl_text(q, stellen)
    return bruch_text(q)


def zk(q):
    """Wie ``z``, negative Zahlen in Klammern."""
    q = Fraction(q)
    return f"({z(q)})" if q < 0 else z(q)


def euro(q):
    return zahl_text(Fraction(q), 2)


@dataclass(frozen=True)
class Schritt:
    """Eine Zeile des Rechenwegs; ``vorlage`` ist übersetzt und hat ``%(name)s``-Platzhalter."""

    vorlage: str
    werte: dict = field(default_factory=dict)

    def zeile(self, offen, sichtbar=None):
        """``offen=True``: Ergebnisse durch ``___`` ersetzt (echte Aufgabe). Mit ``sichtbar`` (Menge
        von Beträgen) bleiben dann nur noch Zahlen stehen, die die Aufgabe selbst nennt."""
        werte = {}
        for k, v in self.werte.items():
            verdeckt = offen and (
                k.startswith("r") or (sichtbar is not None and not zahlen_in(v) <= sichtbar)
            )
            werte[k] = LUECKE if verdeckt else v
        return self.vorlage % werte


def S(vorlage, **werte):
    return Schritt(vorlage, {k: str(v) for k, v in werte.items()})


@dataclass(frozen=True)
class Hilfe:
    """Alles, was die Hilfeleiter zu einer Aufgabe braucht (ohne Sprachstufen der Erklärkarte)."""

    gegeben: tuple  # Zahlen der Aufgabe als Text ("35", "7 m")
    gesucht: str  # übersetzt
    denk: str  # Denkanstoß, übersetzt, ohne Zahlwörter
    schritte: tuple  # Schritt
    ergebnis_vorlage: str = ""  # optional: letzte Zeile, sonst nur "Ergebnis: ___"


# --- Zahlen im Text finden (Leck-Prüfung) ---------------------------------------------------------

_HOCH = str.maketrans({h: f" {i}" for i, h in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")})
_GEMISCHT = re.compile(r"(\d+)\s+(\d+)\s*/\s*(\d+)")
_BRUCH = re.compile(r"(\d+)\s*/\s*(\d+)")
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
_WORT = re.compile(r"[a-zäöüß]+")

_WOERTER = {
    "null": 0, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8,
    "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "zwanzig": 20, "dreißig": 30, "vierzig": 40,
    "fünfzig": 50, "hundert": 100, "tausend": 1000,
    "zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "hundred": 100, "thousand": 1000,
}  # fmt: skip


def _token_werte(token):
    """Mögliche Werte eines Zahl-Tokens (``1.000`` kann Tausend oder eins sein)."""
    werte = set()
    t = token
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
        werte.add(Fraction(re.sub(r"[.,]", "", t)))
        t = t.replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        werte.add(Fraction(t))
    except (ValueError, ZeroDivisionError):
        pass
    return werte


def zahlen_in(text):
    """Alle Beträge im Text (Zahlen, Brüche, gemischte Zahlen, Zahlwörter, Hochzahlen).
    Verglichen wird ohne Vorzeichen: ``-5`` und ``5`` zählen gleich."""
    text = str(text).translate(_HOCH)
    werte = set()
    for m in _GEMISCHT.finditer(text):
        g, p, q = (int(x) for x in m.groups())
        if q:
            werte.add(Fraction(g * q + p, q))
    for m in _BRUCH.finditer(text):
        p, q = (int(x) for x in m.groups())
        if q:
            werte.add(Fraction(p, q))
    for m in _TOKEN.finditer(text):
        werte |= _token_werte(m.group())
    for wort in _WORT.findall(text.casefold()):
        if wort in _WOERTER:
            werte.add(Fraction(_WOERTER[wort]))
    return werte


def _norm_term(text):
    t = str(text).casefold().replace("−", "-").replace("·", "*").replace("⋅", "*")
    t = t.translate(str.maketrans("²³", "23")).replace("^", "")
    return re.sub(r"[\s*]", "", t)


def loesungswerte(loesung):
    """Die Beträge, die die Lösung verraten würden (ohne die Zahlen, die in der Aufgabe stehen)."""
    if loesung.form in (ZAHL, GLEICHUNG, REST):
        return {abs(Fraction(loesung.wert))}
    if loesung.form == TERM:
        return {Fraction(m) for m in re.findall(r"\d+", loesung.term)}
    return set()


def leckt(text, aufgabe):
    """Verrät der Text die Lösung der echten Aufgabe? Zahlen, die die Aufgabe selbst nennt, zählen
    nicht. Erkennt jede Schreibweise (Bruch, Dezimal, Prozent, Zahlwort) und bei Termen die
    Schreibweise des Ergebnisses."""
    gegeben = zahlen_in(aufgabe.text)
    verraeterisch = loesungswerte(aufgabe.loesung) - gegeben
    if verraeterisch & zahlen_in(text):
        return True
    if aufgabe.loesung.form == TERM and aufgabe.loesung.term:
        soll = _norm_term(aufgabe.loesung.term)
        if soll and soll in _norm_term(text):
            return True
    return False
