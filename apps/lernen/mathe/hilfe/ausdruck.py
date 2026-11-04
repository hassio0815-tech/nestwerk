"""Rechenausdrücke (Zahlen, + − · :, Klammern, Hochzahlen) lesen und Schritt für Schritt auswerten.

Für Punkt vor Strich, Klammern, Potenzen und negative Zahlen. Die Reihenfolge ist die der Schule:
Klammern zuerst (von innen), dann Potenzen, dann Punkt (links nach rechts), dann Strich. Jeder
Schritt ist eine einzelne Rechnung ``a op b = r``; Zwischenergebnisse tragen den Schlüssel ``ra``,
``rb`` (Operand ist ein früheres Ergebnis) und ``r`` und werden so im offenen Gerüst verdeckt.
"""

import re
from dataclasses import dataclass
from fractions import Fraction

from django.utils.translation import gettext as _

from .bau import Schritt, z, zk

_HOCH = {c: str(i) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}
_TOKEN = re.compile(r"\s*(\d+(?:,\d+)?|[+−\-·:*()]|[⁰¹²³⁴⁵⁶⁷⁸⁹]+)")
_HOCH_TEXT = "⁰¹²³⁴⁵⁶⁷⁸⁹"


class AusdruckFehler(ValueError):
    """Der Text ist kein Ausdruck, den wir lesen können."""


@dataclass
class _Zelle:
    wert: Fraction
    gegeben: bool = True  # False: Ergebnis eines früheren Schritts


@dataclass
class _Potenz:
    basis: object  # _Zelle oder _Gruppe
    hoch: int


@dataclass
class _Gruppe:
    teile: list  # abwechselnd Atom und Operator-Zeichen


def hoch_text(n):
    return "".join(_HOCH_TEXT[int(c)] for c in str(n))


def _lesen(text):
    tokens, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise AusdruckFehler(text)
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


def _parsen(tokens):
    stapel = [[]]
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "(":
            stapel.append([])
        elif t == ")":
            if len(stapel) < 2:
                raise AusdruckFehler(")")
            gruppe = _Gruppe(stapel.pop())
            stapel[-1].append(gruppe)
        elif t[0] in _HOCH:
            if not stapel[-1] or isinstance(stapel[-1][-1], str):
                raise AusdruckFehler(t)
            hoch = int("".join(_HOCH[c] for c in t))
            stapel[-1][-1] = _Potenz(stapel[-1][-1], hoch)
        elif t in "+−-·:*":
            teile = stapel[-1]
            vorzeichen_moeglich = t in "−-" and (not teile or isinstance(teile[-1], str))
            if vorzeichen_moeglich:
                if i + 1 >= len(tokens) or not re.fullmatch(r"\d+(?:,\d+)?", tokens[i + 1]):
                    raise AusdruckFehler("Vorzeichen")
                zahl = Fraction(tokens[i + 1].replace(",", "."))
                teile.append(_Zelle(-zahl))
                i += 1
            else:
                teile.append("·" if t == "*" else ("−" if t == "-" else t))
        else:
            teile = stapel[-1]
            teile.append(_Zelle(Fraction(t.replace(",", "."))))
        i += 1
    if len(stapel) != 1:
        raise AusdruckFehler("(")
    return _Gruppe(stapel[0])


def lesen(text):
    """Text -> Baum. Löst ``AusdruckFehler`` bei Unlesbarem."""
    text = re.sub(r"\s*=\s*\?\s*$", "", str(text))
    return _parsen(_lesen(text))


# --- Auswerten in Schritten -----------------------------------------------------------------------


def _rechnen(a, op, b):
    if op == "+":
        return a + b
    if op == "−":
        return a - b
    if op == "·":
        return a * b
    if b == 0:
        raise AusdruckFehler("durch null")
    return a / b


def _tauschen(zelle_a, zelle_b, ergebnis, op):
    """Der Schritt als (Vorlage, Werte) mit Schlüsseln nach Konvention (``r…`` = Ergebnis)."""
    werte = {}
    ka = "a" if zelle_a.gegeben else "ra"
    kb = "b" if zelle_b.gegeben else "rb"
    werte[ka] = zk(zelle_a.wert)
    werte[kb] = zk(zelle_b.wert)
    werte["r"] = z(ergebnis)
    return f"%({ka})s {op} %({kb})s = %(r)s", werte


class _Lauf:
    def __init__(self):
        self.schritte = []  # (art, vorlage, werte)

    def zelle(self, atom, tiefe):
        if isinstance(atom, _Zelle):
            return atom
        if isinstance(atom, _Potenz):
            basis = self.zelle(atom.basis, tiefe)
            wert = basis.wert**atom.hoch
            werte = {("a" if basis.gegeben else "ra"): zk(basis.wert), "r": z(wert)}
            ka = "a" if basis.gegeben else "ra"
            vorlage = f"%({ka})s{hoch_text(atom.hoch)} = %(r)s"
            self.schritte.append(("potenz", vorlage, werte))
            return _Zelle(wert, False)
        return self.gruppe(atom, tiefe + 1)

    def gruppe(self, gruppe, tiefe):
        teile = [t if isinstance(t, str) else self.zelle(t, tiefe) for t in gruppe.teile]
        art_klammer = tiefe > 0
        for ops, art in (("·:", "punkt"), ("+−", "strich")):
            i = 1
            while i < len(teile):
                op = teile[i]
                if not isinstance(op, str) or i + 1 >= len(teile):
                    raise AusdruckFehler("Ausdruck")
                if op in ops:
                    a, b = teile[i - 1], teile[i + 1]
                    wert = _rechnen(a.wert, op, b.wert)
                    vorlage, werte = _tauschen(a, b, wert, op)
                    self.schritte.append(("klammer" if art_klammer else art, vorlage, werte))
                    teile[i - 1 : i + 2] = [_Zelle(wert, False)]
                else:
                    i += 2
        if len(teile) != 1 or isinstance(teile[0], str):
            raise AusdruckFehler("Ausdruck")
        return teile[0]


def auswerten(text):
    """``(wert, [(art, vorlage, werte)])`` mit art in klammer | potenz | punkt | strich."""
    baum = lesen(text)
    lauf = _Lauf()
    ergebnis = lauf.gruppe(baum, 0)
    return ergebnis.wert, lauf.schritte


def _etikett(art):
    return {
        "klammer": _("Zuerst die Klammer: %(rechnung)s"),
        "potenz": _("Potenz: %(rechnung)s"),
        "punkt": _("Malnehmen und Teilen vor Plus und Minus: %(rechnung)s"),
        "strich": _("Plus und Minus von links nach rechts: %(rechnung)s"),
    }[art]


def schritte_fuer(text):
    """Die Rechenschritte als ``Schritt``-Liste für das Gerüst und das Beispiel."""
    _wert, roh = auswerten(text)
    ergebnis = []
    for art, vorlage, werte in roh:
        et = _etikett(art) % {"rechnung": vorlage}
        ergebnis.append(Schritt(et, {k: str(v) for k, v in werte.items()}))
    return ergebnis


def arten(text):
    """Welche Schritt-Arten kommen vor (für den Denkanstoß)?"""
    _wert, roh = auswerten(text)
    return {a for a, _v, _w in roh}


# --- Typische Fehlrechnungen (für die Fehleranalyse): Wert eines Ausdrucks mit einer Regel verletzt


def _flach(teile):
    ergebnis = []
    for t in teile:
        if isinstance(t, _Gruppe):
            ergebnis.extend(_flach(t.teile))
        else:
            ergebnis.append(t)
    return ergebnis


def _atomwert(atom, opt):
    if isinstance(atom, _Zelle):
        return atom.wert
    if isinstance(atom, _Potenz):
        basis = _atomwert(atom.basis, opt)
        return basis * atom.hoch if opt["potenz_mal"] else basis**atom.hoch
    return _gruppenwert(atom, opt)


def _gruppenwert(gruppe, opt):
    teile = _flach(gruppe.teile) if opt["ohne_klammern"] else gruppe.teile
    teile = [t if isinstance(t, str) else _atomwert(t, opt) for t in teile]
    if opt["links_nach_rechts"]:
        gruppen = (("·:+−"),)
    else:
        gruppen = ("·:", "+−")
    for ops in gruppen:
        i = 1
        while i < len(teile):
            if teile[i] in ops:
                teile[i - 1 : i + 2] = [_rechnen(teile[i - 1], teile[i], teile[i + 1])]
            else:
                i += 2
    return teile[0]


def variante(text, *, potenz_mal=False, links_nach_rechts=False, ohne_klammern=False):
    """Wert des Ausdrucks, wenn eine Regel verletzt wird: Hochzahl als Malnehmen, Rechnen strikt von
    links nach rechts (ohne Punkt vor Strich) oder Klammern ignoriert. ``None``: nicht lesbar."""
    try:
        opt = {
            "potenz_mal": potenz_mal,
            "links_nach_rechts": links_nach_rechts,
            "ohne_klammern": ohne_klammern,
        }
        return _gruppenwert(lesen(text), opt)
    except (AusdruckFehler, IndexError, ZeroDivisionError, TypeError):
        return None
