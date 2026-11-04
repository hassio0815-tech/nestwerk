"""Datentypen des Mathe-Generators (SPEC 21.13): reine Daten, ohne Datenbank und ohne KI.

Eine ``Aufgabe`` besteht aus dem Text für das Kind, einer berechneten ``Loesung`` und den
Zahlen (``parameter``), aus denen sie entstanden ist. Mit Generator, Schwierigkeit und Seed ist
sie jederzeit reproduzierbar; Paket 2 (Hilfe) erzeugt damit analoge Beispiele mit anderen Zahlen.
"""

from dataclasses import asdict, dataclass, field
from fractions import Fraction

# Formen, in denen eine Zahl eingegeben werden darf
GANZ, DEZIMAL, BRUCH, GEMISCHT = "ganz", "dezimal", "bruch", "gemischt"
ZAHL, REST, GLEICHUNG, TERM = "zahl", "rest", "gleichung", "term"


@dataclass(frozen=True)
class Loesung:
    """Die berechnete, normierte Lösung samt der Schreibweisen, die als richtig gelten."""

    form: str  # zahl | rest | gleichung | term
    anzeige: str  # so wird die Lösung gezeigt ("3/4", "17 R 2", "x = 5", "5,50 €")
    wert: str = ""  # zahl/gleichung/rest: exakter Wert als Text ("7/2"); bei rest der Quotient
    rest: int = 0  # nur form=rest
    term: str = ""  # nur form=term: kanonische Schreibweise, z. B. "x^2+5x+6"
    erlaubt: tuple = (GANZ, DEZIMAL)  # erlaubte Eingabeformen einer Zahl
    kuerzen: bool = False  # Brüche müssen vollständig gekürzt sein
    vereinfacht: bool = False  # Terme: ohne Klammern und zusammengefasst
    prozent: bool = False  # Antwort in Prozent: "25" und "25 %" gelten
    einheit: str = ""  # normierte Einheit ("€", "cm"); leer = keine
    variable: str = "x"  # nur form=gleichung

    def als_bruch(self):
        return Fraction(self.wert)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, daten):
        daten = dict(daten)
        daten["erlaubt"] = tuple(daten.get("erlaubt", (GANZ, DEZIMAL)))
        return cls(**daten)


@dataclass(frozen=True)
class Aufgabe:
    """Eine erzeugte Aufgabe. ``parameter`` enthält nur JSON-taugliche Werte (Zahlen, Text)."""

    generator: str  # Schlüssel in der Registry
    typ: str  # Aufgabentyp innerhalb des Generators (z. B. "add_mit_uebertrag")
    thema: str  # Schlüssel des Themas (Thema.schluessel)
    klassenstufe: int
    schwierigkeit: int  # 1 bis 5
    seed: int
    text: str
    loesung: Loesung
    parameter: dict = field(default_factory=dict)

    def to_dict(self):
        """Alles außer dem Text (der steht in ``Frage.frage``); genug, um zu prüfen und
        eine analoge Aufgabe zu erzeugen."""
        return {
            "generator": self.generator,
            "typ": self.typ,
            "thema": self.thema,
            "klassenstufe": self.klassenstufe,
            "schwierigkeit": self.schwierigkeit,
            "seed": self.seed,
            "parameter": self.parameter,
            "loesung": self.loesung.to_dict(),
        }


@dataclass(frozen=True)
class Roh:
    """Was ein Generator liefert; die Registry ergänzt Schlüssel, Stufe, Schwierigkeit, Seed."""

    typ: str
    text: str
    loesung: Loesung
    parameter: dict = field(default_factory=dict)
