"""Registry der Generatoren (SPEC 21.13): je Rechenart eine reine Funktion ``(rng, d, ctx) -> Roh``.

Kein globaler Zustand beim Erzeugen: derselbe Seed liefert dieselbe Aufgabe. Die Registry selbst
wird nur beim Import befüllt (Decorator ``@generator``).
"""

import random
from dataclasses import dataclass

from .aufgabe import Aufgabe

SEED_BITS = 48
MIN_STUFE, MAX_STUFE = 1, 5
MIN_GRENZE = 20  # kleinere Obergrenzen für Zahlenräume würden Aufgaben unmöglich machen
BANDEN = (3, 6, 8)  # Klassenstufen der Startdaten


def band(klassenstufe):
    """Ordnet eine Klassenstufe einem Inhaltsband zu (3: bis 4, 6: 5 bis 7, 8: ab 8).
    Unbekannt (``None``) zählt wie Klasse 6, wie bei den Sprachstufen."""
    if klassenstufe is None:
        return 6
    if klassenstufe <= 4:
        return 3
    return 6 if klassenstufe <= 7 else 8


def niveau(stufe_text):
    """``erweitert`` oder ``grund`` aus der frei eingetragenen Leistungsstufe (z. B. "Erweiterungs-
    niveau", "E-Kurs"). Alles andere, auch leer, gilt als Grundniveau."""
    t = (stufe_text or "").casefold()
    if "erweit" in t or "e-kurs" in t or "ekurs" in t or t.strip() in {"e", "gymnasial"}:
        return "erweitert"
    return "grund"


@dataclass(frozen=True)
class Kontext:
    """Einstellungen der Eltern, die das Erzeugen berühren (heute: Obergrenze der Zahlenräume)."""

    grenze: int | None = None

    def lim(self, n):
        """``n`` begrenzt auf die Obergrenze der Eltern (nie unter ``MIN_GRENZE``)."""
        if not self.grenze:
            return n
        return max(min(n, self.grenze), min(n, MIN_GRENZE))


@dataclass(frozen=True)
class Generator:
    schluessel: str
    name: str  # gettext_noop-Text; übersetzt wird bei der Anzeige
    thema: str  # Thema.schluessel
    klassenstufe: int
    funktion: object


_REGISTRY = {}


def generator(schluessel, name, *, thema, klassenstufe):
    """Decorator: meldet eine Generatorfunktion an."""

    def anmelden(funktion):
        if schluessel in _REGISTRY:
            raise ValueError(f"Generator doppelt: {schluessel}")
        _REGISTRY[schluessel] = Generator(schluessel, name, thema, klassenstufe, funktion)
        return funktion

    return anmelden


def alle():
    return dict(_REGISTRY)


def schluessel_alle():
    return tuple(_REGISTRY)


def holen(schluessel):
    try:
        return _REGISTRY[schluessel]
    except KeyError:
        raise KeyError(f"Unbekannter Generator: {schluessel}") from None


def generatoren_fuer(thema=None, klassenstufe=None):
    """Generatoren eines Themas und/oder einer Klassenstufe, in Registrierungsreihenfolge."""
    return [
        g
        for g in _REGISTRY.values()
        if (thema is None or g.thema == thema)
        and (klassenstufe is None or g.klassenstufe == klassenstufe)
    ]


def themen_schluessel():
    return tuple(dict.fromkeys(g.thema for g in _REGISTRY.values()))


def erzeugen(schluessel, schwierigkeit, seed, kontext=None):
    """Erzeugt eine Aufgabe. Gleiche Eingabe, gleiche Aufgabe (keine Uhr, kein globaler Zufall)."""
    kontext = kontext or Kontext()
    g = holen(schluessel)
    stufe = max(MIN_STUFE, min(MAX_STUFE, int(schwierigkeit)))
    seed = int(seed) % (1 << SEED_BITS)
    roh = g.funktion(random.Random(seed), stufe, kontext)
    parameter = dict(roh.parameter)
    if kontext.grenze:
        parameter["grenze"] = kontext.grenze
    return Aufgabe(
        generator=g.schluessel,
        typ=roh.typ,
        thema=g.thema,
        klassenstufe=g.klassenstufe,
        schwierigkeit=stufe,
        seed=seed,
        text=roh.text,
        loesung=roh.loesung,
        parameter=parameter,
    )


def analog(aufgabe, seed=None, versuche=50):
    """Eine gleichartige Aufgabe mit ANDEREN Zahlen (Erweiterungspunkt für Paket 2: analoges
    Beispiel, Wiederholung). Gleicher Generator, gleiche Schwierigkeit, anderer Seed."""
    kontext = Kontext(aufgabe.parameter.get("grenze"))
    start = (aufgabe.seed + 1 if seed is None else seed) % (1 << SEED_BITS)
    kern = {k: v for k, v in aufgabe.parameter.items() if k != "grenze"}
    neu = None
    for i in range(versuche):
        neu = erzeugen(aufgabe.generator, aufgabe.schwierigkeit, start + i, kontext)
        if {k: v for k, v in neu.parameter.items() if k != "grenze"} != kern:
            return neu
    return neu
