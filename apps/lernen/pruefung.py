"""Antwortprüfung für Vokabeln und Kurzantworten (SPEC 21.2, Etappe 2, ohne KI).

Rein rechnend, ohne Datenbank. Großzügig bei Äußerlichkeiten (Groß-/Kleinschreibung, Leerzeichen,
Satzzeichen, Akzente wie é oder à, ß = ss), streng bei Umlauten (``schön`` ist nicht ``schon``).
Mehrere akzeptierte Antworten stehen in der Antwort getrennt durch ``/`` oder ``;``
(``to be / be``); Text in Klammern ist optional (``cousin (female)`` darf ``cousin`` heißen).
Ein kleiner Tippfehler ergibt "fast richtig" statt falsch.
"""

import re
import unicodedata
from dataclasses import dataclass

from .mathe import antwort as mathe_antwort
from .mathe import fehler as mathe_fehler

TRENNER = re.compile(r"[/;]")
KLAMMER = re.compile(r"\([^)]*\)")
# Umlaut-Punkte (U+0308) bleiben erhalten, wenn sie auf a, o oder u stehen
_UMLAUT_BASIS = frozenset("aouAOU")


@dataclass(frozen=True)
class Pruefergebnis:
    richtig: bool
    fast: bool = False  # kleiner Tippfehler: noch nicht richtig, aber nah dran
    treffer: str = ""  # die akzeptierte Antwort, die gemeint war (bei richtig oder fast)
    # Mathe (Etappe 10a/10b): Hinweis für das Kind (bei "fast" z. B. "noch nicht gekürzt", bei
    # falschen Antworten ein gezielter Hinweis aus der Fehleranalyse, nie mit der Lösung) und der
    # Fehlertyp (Schlüssel aus ``mathe.fehler``; leer: nicht erkannt)
    hinweis: str = ""
    fehlertyp: str = ""


def normalisieren(text):
    """Vergleichsform: klein, ohne Akzente (außer Umlaute), ohne Satzzeichen, ein Leerzeichen."""
    zerlegt = unicodedata.normalize("NFD", str(text).casefold())
    ohne_akzent = []
    basis = ""
    for zeichen in zerlegt:
        if unicodedata.combining(zeichen):
            if zeichen == "̈" and basis in _UMLAUT_BASIS:
                ohne_akzent.append(zeichen)
            continue
        basis = zeichen
        ohne_akzent.append(zeichen)
    text = unicodedata.normalize("NFC", "".join(ohne_akzent))
    # Apostroph entfällt ("I'm" -> "im"), Bindestrich und übrige Satzzeichen trennen Wörter
    text = re.sub(r"['’`´]", "", text)
    text = re.sub(r"[^\w\s]|_", " ", text)
    return " ".join(text.split())


def alternativen(antwort):
    """Alle akzeptierten Schreibweisen einer Antwort (Originaltext, ohne Dubletten)."""
    ergebnis = []
    for teil in TRENNER.split(str(antwort)):
        for variante in (teil, KLAMMER.sub(" ", teil)):
            variante = " ".join(variante.split())
            if variante and variante not in ergebnis:
                ergebnis.append(variante)
    return ergebnis


def anzeige_antwort(antwort):
    """Die erste Alternative ohne Klammern: kurze Form für die Frage in Gegenrichtung."""
    liste = alternativen(antwort)
    return liste[0] if liste else ""


def _abstand(a, b):
    """Damerau-Levenshtein (optimale Zeichenfolge): Tausch zweier Nachbarn zählt als 1."""
    zeilen = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        zeilen[i][0] = i
    for j in range(len(b) + 1):
        zeilen[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            kosten = 0 if a[i - 1] == b[j - 1] else 1
            zeilen[i][j] = min(
                zeilen[i - 1][j] + 1, zeilen[i][j - 1] + 1, zeilen[i - 1][j - 1] + kosten
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                zeilen[i][j] = min(zeilen[i][j], zeilen[i - 2][j - 2] + 1)
    return zeilen[len(a)][len(b)]


def erlaubter_abstand(laenge):
    """Wie viele Tippfehler noch "fast richtig" sind: kurze Wörter keine (Verwechslungsgefahr)."""
    if laenge < 4:
        return 0
    return 1 if laenge < 10 else 2


def pruefen(gegeben, erwartet):
    """Vergleicht die Eingabe mit allen akzeptierten Antworten.

    ``richtig``: gleich nach dem Normalisieren. ``fast``: höchstens ein kleiner Tippfehler
    (Länge der erwarteten Form entscheidet). Leere Eingabe ist nie richtig und nie "fast".
    """
    eingabe = normalisieren(gegeben)
    if not eingabe:
        return Pruefergebnis(False)
    bester = None
    for variante in alternativen(erwartet):
        form = normalisieren(variante)
        if not form:
            continue
        if eingabe == form:
            return Pruefergebnis(True, treffer=variante)
        abstand = _abstand(eingabe, form)
        if abstand <= erlaubter_abstand(len(form)) and (bester is None or abstand < bester[0]):
            bester = (abstand, variante)
    if bester is not None:
        return Pruefergebnis(False, fast=True, treffer=bester[1])
    return Pruefergebnis(False)


def pruefen_mathe(gegeben, loesung, aufgabe=None):
    """Prüft die Eingabe zu einer erzeugten Mathe-Aufgabe gegen deren berechnete Lösung
    (``Loesung`` oder ihr ``dict``). Zahlen, Brüche, Rest, Gleichungen und Terme: siehe
    ``mathe.antwort``. "Fast" heißt: Der Wert stimmt, die Schreibweise noch nicht.

    Mit ``aufgabe`` (``mathe.aufgabe.Aufgabe``) untersucht die Fehleranalyse falsche Antworten:
    Fehlertyp und ein gezielter Hinweis ohne die Lösung. Nicht erkannt: neutraler Hinweis."""
    befund = mathe_antwort.pruefen(gegeben, loesung)
    fehlertyp, hinweis = befund.fehlertyp, befund.hinweis
    if aufgabe is not None and not befund.richtig and not befund.fast:
        fehlertyp = fehlertyp or mathe_fehler.analysiere(aufgabe, gegeben)
        hinweis = mathe_fehler.hinweis_text(fehlertyp or "neutral", aufgabe)
    return Pruefergebnis(
        befund.richtig,
        fast=befund.fast,
        treffer=loesung["anzeige"] if isinstance(loesung, dict) else loesung.anzeige,
        hinweis=hinweis,
        fehlertyp=fehlertyp,
    )
