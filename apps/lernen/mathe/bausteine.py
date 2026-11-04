"""Gemeinsame Bausteine der Generatoren: Zahlen schreiben, Lösungen bauen, Zahlen wählen.

Rechnen mit ``Fraction``, damit jede Lösung exakt ist (keine Gleitkommafehler).
"""

from fractions import Fraction
from math import gcd

from . import term
from .aufgabe import BRUCH, DEZIMAL, GANZ, GEMISCHT, GLEICHUNG, REST, TERM, ZAHL, Loesung

MINUS = "−"


def ist_endlich(q):
    """Hat ``q`` eine endliche Dezimaldarstellung? (Nenner nur mit 2 und 5)"""
    n = Fraction(q).denominator
    for p in (2, 5):
        while n % p == 0:
            n //= p
    return n == 1


def dezimal_text(q, stellen=None):
    """Dezimalschreibweise mit Komma (``3,5``), ohne überflüssige Nullen; mit ``stellen``
    genau so viele Nachkommastellen. ``q`` muss endlich sein."""
    q = Fraction(q)
    if not ist_endlich(q):
        raise ValueError("nicht endlich")
    neg = q < 0
    q = abs(q)
    if stellen is None:
        stellen = 0
        while (q * 10**stellen).denominator != 1:
            stellen += 1
    ganzzahl = q * 10**stellen
    if ganzzahl.denominator != 1:
        raise ValueError("zu wenige Stellen")
    s = str(ganzzahl.numerator).rjust(stellen + 1, "0")
    text = s if stellen == 0 else f"{s[:-stellen]},{s[-stellen:]}"
    return (MINUS if neg else "") + text


def zahl_text(q, stellen=None):
    """Zahl für den Aufgabentext: ganz oder Dezimalzahl mit Komma, negativ mit Minuszeichen."""
    q = Fraction(q)
    if q.denominator == 1 and stellen is None:
        return (MINUS if q < 0 else "") + str(abs(q.numerator))
    return dezimal_text(q, stellen)


def bruch_text(q):
    """``3/4``; ganze Zahlen ohne Nenner."""
    q = Fraction(q)
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def gemischt_text(q):
    """``1 3/4`` (echte Brüche und ganze Zahlen unverändert)."""
    q = Fraction(q)
    if q.denominator == 1 or abs(q) < 1:
        return bruch_text(q)
    g, z = divmod(q.numerator, q.denominator)
    return f"{g} {z}/{q.denominator}"


def klammer_neg(q):
    """Negative Zahlen im Term in Klammern: ``(−3)``."""
    q = Fraction(q)
    return f"({zahl_text(q)})" if q < 0 else zahl_text(q)


# --- Lösungen -------------------------------------------------------------------------------------


def lsg_zahl(wert, *, einheit="", stellen=None, erlaubt=(GANZ, DEZIMAL), prozent=False):
    """Ganze Zahl oder endliche Dezimalzahl, optional mit Einheit oder Prozentzeichen."""
    wert = Fraction(wert)
    text = dezimal_text(wert, stellen) if (wert.denominator != 1 or stellen) else str(wert)
    text = text.replace("-", MINUS)
    anzeige = f"{text} %" if prozent else f"{text} {einheit}".strip()
    return Loesung(ZAHL, anzeige, str(wert), erlaubt=erlaubt, prozent=prozent, einheit=einheit)


def lsg_bruch(wert, *, kuerzen=True):
    """Bruch (oder ganze Zahl); als ``3/4``, ``1 3/4`` oder Zahl erlaubt, vollständig gekürzt."""
    wert = Fraction(wert)
    return Loesung(
        ZAHL,
        bruch_text(wert),
        str(wert),
        erlaubt=(GANZ, BRUCH, GEMISCHT),
        kuerzen=kuerzen,
    )


def lsg_rest(quotient, rest):
    return Loesung(REST, f"{quotient} R {rest}", str(quotient), rest=rest, erlaubt=(GANZ,))


def lsg_gleichung(wert, var="x"):
    wert = Fraction(wert)
    return Loesung(
        GLEICHUNG,
        f"{var} = {zahl_text(wert)}",
        str(wert),
        erlaubt=(GANZ, DEZIMAL, BRUCH),
        variable=var,
    )


def lsg_term(polynom):
    return Loesung(
        TERM,
        term.format_term(polynom),
        term=term.format_term(polynom, anzeige=False),
        vereinfacht=True,
    )


# --- Zahlen wählen --------------------------------------------------------------------------------


def waehle(rng, erzeuge, bedingung, fallback, versuche=400):
    """Zieht Kandidaten, bis die Bedingung gilt. Garantiert ein Ergebnis (``fallback``)."""
    for _ in range(versuche):
        kandidat = erzeuge()
        if bedingung(kandidat):
            return kandidat
    return fallback


def stellen(n):
    return len(str(abs(int(n))))


def uebertraege_add(a, b):
    """Anzahl der Überträge beim schriftlichen Addieren."""
    n = 0
    uebertrag = 0
    while a or b or uebertrag:
        s = a % 10 + b % 10 + uebertrag
        uebertrag = 1 if s >= 10 else 0
        n += uebertrag
        a //= 10
        b //= 10
    return n


def entbuendelungen_sub(a, b):
    """Anzahl der Entbündelungen ("Borgen") beim schriftlichen Subtrahieren ``a - b``."""
    n = 0
    borgen = 0
    while a or b:
        z = a % 10 - borgen - b % 10
        borgen = 1 if z < 0 else 0
        n += borgen
        a //= 10
        b //= 10
    return n


def kgv(a, b):
    return a * b // gcd(a, b)


def runden(q, stellen_):
    """Kaufmännisch runden (ab 5 auf) auf ``stellen_`` Nachkommastellen (negativ: Zehner ...)."""
    q = Fraction(q)
    faktor = Fraction(10) ** stellen_
    scaled = abs(q) * faktor
    r = int(scaled + Fraction(1, 2))
    return (1 if q >= 0 else -1) * Fraction(r) / faktor
