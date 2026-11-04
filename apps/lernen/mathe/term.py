"""Kleine Terme (Summen aus Zahlen, Buchstaben und Potenzen) lesen, vergleichen und anzeigen.

Reine Funktionen für Aufgaben wie ``3x + 5x`` oder ``(x + 2)(x + 3)`` und für die Prüfung der
Eingabe eines Kindes. Ein Polynom ist ein ``dict``: Monom (Tupel aus ``(Buchstabe, Hochzahl)``,
sortiert) -> Koeffizient (``Fraction``). Kein ``eval``; die Eingabe ist auf wenige Zeichen begrenzt.
"""

import re
from fractions import Fraction

MAX_LAENGE = 80
MAX_HOCHZAHL = 6
_HOCH = str.maketrans("²³⁴⁵⁶", "23456")
_RUNTER = str.maketrans("23456", "²³⁴⁵⁶")
_TOKEN = re.compile(r"\s*(\d+(?:[.,]\d+)?|[a-z]|[-+*()^]|[0-9]?[²³⁴⁵⁶])")


class TermFehler(ValueError):
    """Die Eingabe ist kein Term, den wir lesen können."""


def _tokens(text):
    text = str(text).strip().casefold()
    text = text.replace("−", "-").replace("–", "-").replace("·", "*").replace("×", "*")
    text = text.replace("⋅", "*")
    if not text or len(text) > MAX_LAENGE:
        raise TermFehler("Länge")
    ergebnis, i = [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        m = _TOKEN.match(text, i)
        if m is None or m.end() == i:
            raise TermFehler(f"Zeichen: {text[i]!r}")
        ergebnis.append(m.group(1))
        i = m.end()
    return ergebnis


def _mal(a, b):
    ergebnis = {}
    for ma, ca in a.items():
        for mb, cb in b.items():
            exp = dict(ma)
            for var, e in mb:
                exp[var] = exp.get(var, 0) + e
            if any(e > MAX_HOCHZAHL for e in exp.values()):
                raise TermFehler("Hochzahl")
            monom = tuple(sorted(exp.items()))
            ergebnis[monom] = ergebnis.get(monom, 0) + ca * cb
    return ergebnis


def _plus(a, b, vorzeichen=1):
    ergebnis = dict(a)
    for m, c in b.items():
        ergebnis[m] = ergebnis.get(m, 0) + vorzeichen * c
    return ergebnis


def _bereinigen(p):
    return {m: c for m, c in p.items() if c != 0}


class _Leser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def vor(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def nehmen(self):
        tok = self.vor()
        self.i += 1
        return tok

    def summe(self):
        p = self.produkt()
        while self.vor() in ("+", "-"):
            op = self.nehmen()
            p = _plus(p, self.produkt(), 1 if op == "+" else -1)
        return p

    def produkt(self):
        vorzeichen = 1
        while self.vor() in ("+", "-"):
            vorzeichen *= -1 if self.nehmen() == "-" else 1
        p = {(): Fraction(vorzeichen)}
        p = _mal(p, self.potenz())
        while True:
            tok = self.vor()
            if tok == "*":
                self.nehmen()
                p = _mal(p, self.potenz())
            elif tok is not None and (tok == "(" or tok[0].isalpha()):
                # unmittelbar hintereinander: 3x, ab, 2(x+1), (x+1)(x-1), x(x+1)
                p = _mal(p, self.potenz())
            else:
                return p

    def potenz(self):
        basis, mit_zahl = self.atom()
        tok = self.vor()
        if tok == "^":
            self.nehmen()
            exp = self.nehmen()
            if exp is None or not re.fullmatch(r"[0-9]+", exp):
                raise TermFehler("Hochzahl")
            return self._hoch(basis, int(exp))
        if tok is not None and tok[-1] in "²³⁴⁵⁶" and not mit_zahl:
            self.nehmen()
            return self._hoch(basis, int(tok[-1].translate(_HOCH)))
        return basis

    def _hoch(self, basis, exp):
        if exp > MAX_HOCHZAHL or exp < 0:
            raise TermFehler("Hochzahl")
        ergebnis = {(): Fraction(1)}
        for _ in range(exp):
            ergebnis = _mal(ergebnis, basis)
        return ergebnis

    def atom(self):
        tok = self.nehmen()
        if tok is None:
            raise TermFehler("Ende")
        if tok == "(":
            p = self.summe()
            if self.nehmen() != ")":
                raise TermFehler("Klammer")
            return p, False
        if tok[0] in "0123456789":
            return {(): Fraction(tok.replace(",", "."))}, True
        if tok.isalpha() and len(tok) == 1:
            return {((tok, 1),): Fraction(1)}, False
        raise TermFehler(f"Unerwartet: {tok}")


def lesen(text):
    """Liest einen Term als Polynom; ``TermFehler`` bei allem, was keiner ist."""
    leser = _Leser(_tokens(text))
    p = leser.summe()
    if leser.vor() is not None:
        raise TermFehler("Rest")
    return _bereinigen(p)


def summanden(text):
    """Anzahl der Summanden auf oberster Ebene (``3x + 4x - 2`` hat drei, ``2(x+1)`` einen)."""
    tokens = _tokens(text)
    tiefe, n, vorn = 0, 0, True
    for tok in tokens:
        if tok == "(":
            tiefe += 1
        elif tok == ")":
            tiefe -= 1
        if tiefe == 0 and tok in "+-" and not vorn:
            n += 1
        vorn = tok in ("+", "-", "*", "(", "^")
    return n + 1


def hat_klammern(text):
    return "(" in str(text)


def _monom_text(monom, anzeige):
    teile = []
    for var, e in monom:
        teile.append(
            var + (str(e).translate(_RUNTER) if anzeige and e > 1 else f"^{e}" if e > 1 else "")
        )
    return "".join(teile)


def _sortiert(p):
    return sorted(p.items(), key=lambda kv: (-sum(e for _, e in kv[0]), kv[0]))


def format_term(p, *, anzeige=True):
    """Schreibweise eines Polynoms: höchste Potenz zuerst (``x² + 5x + 6``). Mit
    ``anzeige=False`` ASCII mit ``^`` ohne Leerzeichen (kanonisch, wieder lesbar)."""
    if not p:
        return "0"
    teile = []
    for monom, c in _sortiert(p):
        m = _monom_text(monom, anzeige)
        betrag = abs(c)
        if not m:
            zahl = _zahl_text(betrag)
        elif betrag == 1:
            zahl = ""
        else:
            zahl = _zahl_text(betrag)
        text = zahl + m
        if not teile:
            teile.append(("−" if anzeige else "-") * (c < 0) + text)
        else:
            op = " − " if c < 0 else " + "
            teile.append(op + text if anzeige else ("-" if c < 0 else "+") + text)
    return "".join(teile)


def _zahl_text(q):
    if q.denominator == 1:
        return str(q.numerator)
    return f"{q.numerator}/{q.denominator}"


def gleich(a, b):
    return _bereinigen(a) == _bereinigen(b)
