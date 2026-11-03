"""Technische Absicherung des Tutors (SPEC 21.3): rein rechnend, ohne Datenbank.

Drei Dinge, die nicht vom Prompt abhängen:

1. **Vorprüfung** der Nachricht des Kindes: Lösungsbitte ("bitte lösen") und Rollenwechsel-Versuch
   werden erkannt, bevor die KI etwas sieht.
2. **Leak-Prüfung** der Antwort: Heuristik gegen Endergebnisse, Lösungssätze, Vokabel-Antwortsätze
   und bekannte Antworten. Sie ist ehrlich begrenzt (siehe ``leck_verdacht``): keine Garantie.
3. **Strikte Bewertung**: die strukturierte Ausgabe des Aufrufs ``bewerten`` wird als Daten
   validiert; was nicht passt, ergibt den sicheren Standard ("unklar"). Der Kurzhinweis geht nur
   nach derselben Leak-Prüfung weiter.
"""

import re
from dataclasses import dataclass

from .pruefung import alternativen, normalisieren

# --- Vorprüfung ---------------------------------------------------------------------------------

_FLAGS = re.IGNORECASE | re.UNICODE

# "bitte lösen", "mach meine Hausaufgaben", "gib mir die Lösung", "solve this" ...
_LOESUNGSBITTE = [
    re.compile(p, _FLAGS)
    for p in (
        r"\b(?:l[öo]e?se|l[öo]st|rechne|berechne|erledige|beantworte|übersetze|uebersetze|"
        r"vervollständige|vervollstaendige|fülle|fuelle)\w*\s+(?:mir\s+|doch\s+|bitte\s+|"
        r"einfach\s+|jetzt\s+|mal\s+|schnell\s+)*(?:die|das|den|diese|dieses|meine|alle|alles|"
        r"es|sie|ihn|folgende|mir)\b",
        r"\bl[öo]se?\b.{0,30}\b(?:für mich|fuer mich)\b",
        r"\b(?:für mich|fuer mich)\b.{0,40}\b(?:l[öo]s\w*|rechn\w*|erledig\w*|mach\w*|"
        r"schreib\w*)\b",
        r"(?:^|[.!?]\s+|\bbitte\s+|\bdu\s+|\bdoch\s+)(?:mach|mache|erledige|schreib|schreibe)\s+"
        r"(?:mir\s+|meine\s+|die\s+|bitte\s+|einfach\s+)*(?:hausaufgabe\w*|hausi\w*|aufgabe\w*|"
        r"hausarbeit\w*)\b",
        r"\b(?:gib|gibst|sag|sage|nenn|nenne|zeig|zeige|verrat|verrate)\s+mir\s+(?:bitte\s+|"
        r"doch\s+|einfach\s+|mal\s+)*(?:die|das|den|eine)?\s*(?:l[öo]sung|antwort|ergebnis|"
        r"resultat)\b",
        r"\b(?:was|wie)\s+(?:ist|lautet|wäre|waere)\s+(?:denn\s+)?(?:die|das)\s+"
        r"(?:l[öo]sung|richtige\s+antwort|ergebnis)\b",
        r"\bwie\s+lautet\s+(?:die|das)\s+(?:l[öo]sung|antwort|ergebnis)\b",
        r"\b(?:solve|do)\s+(?:this|my|the)\b.{0,30}\b(?:homework|exercise|task|problem|question)\b",
        r"\b(?:give|tell)\s+me\s+(?:the\s+)?(?:answer|solution|result)\b",
    )
]

# Höfliche Form ("Kannst du das lösen?"): zählt nicht, wenn das Kind um Erklärung oder Hilfe bittet
_LOESUNGSBITTE_HOEFLICH = re.compile(
    r"\b(?:kannst|könntest|koenntest|würdest|wuerdest|willst)\s+du\b.{0,60}\b(?:l[öo]sen|"
    r"erledigen|machen|rechnen|ausfüllen|ausfuellen)\b",
    _FLAGS,
)
_ERKLAERUNG = re.compile(
    r"\b(?:erkl[äa]r\w*|helf\w*|hilf\w*|zeig\w*\s+(?:mir\s+)?wie|wie\s+(?:kann|muss|soll|geht|"
    r"macht|mache)\b|tipp\w*|hinweis\w*)",
    _FLAGS,
)

# Rollenwechsel / Prompt-Injection in der Nachricht des Kindes
_ROLLENWECHSEL = [
    re.compile(p, _FLAGS)
    for p in (
        r"\bignorier\w*\b.{0,30}\b(?:regel\w*|anweisung\w*|instruktion\w*|vorgabe\w*|befehl\w*)",
        r"\bvergiss\b.{0,30}\b(?:alles|regel\w*|anweisung\w*|instruktion\w*|vorgabe\w*)",
        r"\büberschreib\w*\b.{0,30}\b(?:regel\w*|anweisung\w*|prompt\w*)",
        r"\bdu\s+bist\s+(?:jetzt|nun|ab\s+jetzt|ab\s+sofort)\s+(?:ein|eine|einer|der|die|das|mein|"
        r"kein|keine|nicht|ohne|frei|böse|boese)\b",
        r"\bdu\s+bist\s+nicht\s+mehr\s+(?:der|ein|eine|mein|dein)\b",
        r"\bsei\s+(?:jetzt|ab\s+jetzt|nun)\s+(?:ein|eine|mein|der|die)\b",
        r"\bab\s+(?:jetzt|sofort)\s+(?:bist|antwortest|sagst|nennst|ignorierst)\s+du\b",
        r"\b(?:tu|tue)\b.{0,10}\bals\s+(?:ob|wärst|waerst|wenn)\b",
        r"\b(?:spiel|spiele)\s+(?:jetzt\s+|bitte\s+)?die\s+rolle\b",
        r"\bsystem\s*-?\s*prompt\b",
        r"\b(?:neue|geheime)\s+(?:anweisung\w*|regel\w*)\b",
        r"\b(?:entwickler|developer|admin\w*)[-\s]?modus\b|\bdeveloper\s+mode\b|\bjailbreak\b",
        r"\bdan\s+mode\b|\bdo\s+anything\s+now\b",
        r"\bignore\b.{0,30}\b(?:instructions|rules|previous|above|system)\b",
        r"\b(?:you\s+are\s+now|pretend\s+(?:to\s+be|you)|act\s+as|from\s+now\s+on\s+you)\b",
        r"\b(?:reveal|show|print|repeat)\b.{0,25}\b(?:system\s+prompt|instructions)\b",
        r"\bzeig\w*\b.{0,25}\b(?:deine|dein)\s+(?:anweisung\w*|regel\w*|prompt\w*)",
        r"^\s*(?:system|assistant|tutor)\s*:",
    )
]


def ist_loesungsbitte(text):
    """Bittet das Kind darum, dass der Tutor die Aufgabe löst? (Einfache Vorprüfung; der Prompt
    deckt den Rest ab.)"""
    text = " ".join(str(text or "").split())
    if any(muster.search(text) for muster in _LOESUNGSBITTE):
        return True
    return bool(_LOESUNGSBITTE_HOEFLICH.search(text) and not _ERKLAERUNG.search(text))


def ist_rollenwechsel(text):
    """Versucht die Nachricht, die Regeln oder die Rolle des Tutors zu ändern?"""
    text = " ".join(str(text or "").split())
    return any(muster.search(text) for muster in _ROLLENWECHSEL)


# --- Leak-Prüfung -------------------------------------------------------------------------------

_ZAHL = re.compile(r"\d+(?:[.,]\d+)?")
_GLEICH = re.compile(r"=\s*[−-]?\s*\d")
# Wörter direkt vor "=", die ein Ergebnis ankündigen
_ERGEBNISWORT = re.compile(
    r"(?:ergebnis|l[öo]sung|antwort|summe|produkt|differenz|quotient|wert|x|y|z|n)\s*$", _FLAGS
)
_RECHTS = re.compile(r"[\d\s+\-−*/×÷:.,xX·()]*")

_LOESUNGSSATZ = [
    re.compile(p, _FLAGS)
    for p in (
        r"\bl[öo]sung\s*(?::|=|ist|lautet|wäre|waere)",
        r"\b(?:das\s+)?ergebnis\s*(?::|=|ist|lautet|wäre|waere)",
        r"\b(?:die\s+)?(?:richtige|korrekte)\s+(?:antwort|l[öo]sung|ergebnis|schreibweise)\b",
        r"\bantwort\s*(?::|ist|lautet)",
        r"\bdas\s+ergibt\b",
        r"\bkommt\b.{0,25}\braus\b",
        r"\brichtig\s+(?:wäre|waere|ist|lautet|heißt|heisst)\b",
        r"\bmuss\b.{0,30}\bheißen\b",
        r"\b(?:solution|answer|result)\s*(?::|is|would\s+be)\b",
    )
]

# Antwort-Sätze bei Vokabelabfragen ("Auf Englisch heißt Hund dog.")
_VOKABELSATZ = [
    re.compile(p, _FLAGS)
    for p in (
        r"\b(?:auf|in)\s+(?:englisch|französisch|franzoesisch|spanisch|lateinisch|latein|"
        r"italienisch|deutsch|türkisch|tuerkisch|russisch|polnisch)\s+(?:heißt|heisst|lautet|sagt\s+"
        r"man|schreibt\s+man|ist\s+das)\b",
        r"\b(?:das|dieses)\s+(?:wort|vokabel)\b.{0,30}\b(?:heißt|heisst|lautet)\b",
        r"\bheißt\s+(?:auf|in)\s+\w+\s*[:„\"»'“]",
        r"\bdie\s+übersetzung\s+(?:ist|lautet)\b",
        r"\bübersetzt\s+(?:man|heißt|lautet)\b",
        r"\btranslation\s+(?:is|:)\b",
        r"\bin\s+(?:english|french|spanish|german)\s*(?:is|:)\b",
    )
]

_LINK = re.compile(r"https?://|www\.|\bftp://|\S+@\S+\.\S+", _FLAGS)


def _zahlen(text):
    return {z.replace(",", ".") for z in _ZAHL.findall(str(text or ""))}


def _passt(text, phrase):
    """Kommt ``phrase`` (normalisiert) als ganze Wortfolge in ``text`` (normalisiert) vor?"""
    return f" {phrase} " in f" {text} "


def _gleichung_verdaechtig(antwort, aufgabe_zahlen):
    for treffer in _GLEICH.finditer(antwort):
        links = antwort[max(0, treffer.start() - 40) : treffer.start()]
        rechts = _RECHTS.match(antwort, treffer.start() + 1).group(0)
        links_zahlen, rechts_zahlen = _zahlen(links), _zahlen(rechts)
        # "12 + 5 = 17": Zahlen der Aufgabe auf der linken Seite, dann ein Ergebnis
        if links_zahlen and links_zahlen <= aufgabe_zahlen:
            return True
        # "17 = 12 + 5": Zahlen der Aufgabe auf der rechten Seite
        if links_zahlen and len(rechts_zahlen) >= 2 and rechts_zahlen <= aufgabe_zahlen:
            return True
        # "Ergebnis = 17", "x = 4": ein Ergebniswort ohne eigene Zahlen
        if not links_zahlen and _ERGEBNISWORT.search(links):
            return True
    return False


def leck_verdacht(antwort, *, stufe=1, aufgabe_text="", bekannte=(), eigene_texte=""):
    """Wirkt die Antwort wie eine verratene Lösung? Gibt den Grund zurück, leer = unauffällig.

    Gründe: ``link``, ``ergebnis`` (Gleichung mit Ergebnis), ``loesungssatz`` ("Lösung:", "die
    richtige Antwort ist"), ``vokabelsatz`` ("Auf Englisch heißt ..."), ``bekannte_antwort``.

    Parameter: ``stufe`` (Hilfestufe; nur Stufe 3 darf ein vorgerechnetes Beispiel mit *anderen*
    Zahlen zeigen, in allen anderen Stufen ist jede Gleichung mit Ergebnis verdächtig),
    ``aufgabe_text`` (Nachrichten des Kindes und Material: daraus stammen die Zahlen der Aufgabe),
    ``bekannte`` (Antworten aus Fragen des Materials oder Themas, auch Vokabeln),
    ``eigene_texte`` (was das Kind selbst geschrieben hat: Wiederholen schadet dann nicht).

    Grenzen (ehrlich): Zahlwörter ("siebzehn"), umschriebene oder in Teilen genannte Lösungen,
    Ergebnisse ohne Gleichheitszeichen ("Das sind 17") und Antworten in Bildern, Rätseln oder
    anderen Sprachen erkennt die Heuristik nicht sicher. Sehr kurze bekannte Antworten (unter drei
    Zeichen, Zahlen unter zwei Ziffern) werden nicht verglichen, um harmlose Wörter nicht zu
    sperren. Es ist ein Netz, keine Garantie.
    """
    antwort = str(antwort or "")
    if _LINK.search(antwort):
        return "link"
    aufgabe_zahlen = _zahlen(aufgabe_text)
    if _GLEICH.search(antwort):
        if stufe != 3 or _gleichung_verdaechtig(antwort, aufgabe_zahlen):
            return "ergebnis"
    if any(muster.search(antwort) for muster in _LOESUNGSSATZ):
        return "loesungssatz"
    if any(muster.search(antwort) for muster in _VOKABELSATZ):
        return "vokabelsatz"
    text_n = normalisieren(antwort)
    eigene_n = normalisieren(eigene_texte)
    for bekannt in bekannte:
        for variante in alternativen(bekannt):
            form = normalisieren(variante)
            minimum = 2 if form.isdigit() else 3
            if len(form) < minimum or (eigene_n and _passt(eigene_n, form)):
                continue
            if _passt(text_n, form):
                return "bekannte_antwort"
    return ""


# --- Strikte Bewertung --------------------------------------------------------------------------

URTEILE = ("richtig", "teilweise", "noch_nicht")
HINWEIS_MAX = 160


@dataclass(frozen=True)
class Bewertung:
    urteil: str  # richtig, teilweise, noch_nicht oder unklar (sicherer Standard)
    hinweis: str = ""  # nur, wenn er geprüft ist; sonst leer
    empfohlene_stufe: int = 1
    gueltig: bool = True


UNKLAR = Bewertung("unklar", "", 1, gueltig=False)


def hinweis_pruefen(hinweis, *, aufgabe_text="", versuch="", bekannte=()):
    """Kurzhinweis des Bewertungs-Aufrufs: gibt den bereinigten Text zurück oder ``""``.

    Erlaubt ist nur ein kurzer Satz ohne Link, Formatierung, Gleichung mit Ergebnis,
    Lösungssatz, bekannte Antwort oder Zahl, die weder in der Aufgabe noch im Versuch vorkommt
    (so eine Zahl wäre vermutlich das Ergebnis)."""
    if not isinstance(hinweis, str):
        return ""
    text = " ".join(hinweis.split())
    if not 3 <= len(text) <= HINWEIS_MAX or re.search(r"[<>`*#\[\]{}|\\]", text):
        return ""
    bekannt_zahlen = _zahlen(aufgabe_text) | _zahlen(versuch)
    if not _zahlen(text) <= bekannt_zahlen:
        return ""
    # Hinweise werden wie Stufe 1 geprüft: nie Gleichung mit Ergebnis, nie Lösungssatz
    if leck_verdacht(text, stufe=1, aufgabe_text=aufgabe_text, bekannte=bekannte):
        return ""
    return text


def bewertung_lesen(daten, *, aufgabe_text="", versuch="", bekannte=()):
    """Liest die strukturierte Ausgabe des Aufrufs ``bewerten`` streng.

    Muss ein Objekt mit genau den Feldern ``urteil``, ``hinweis``, ``empfohlene_stufe`` sein.
    Ungültiges Urteil oder falsche Form ergibt ``UNKLAR``. Ein ungültiger Hinweis entfällt
    (das Urteil bleibt), eine ungültige Stufe wird 1. Die Struktur selbst geht nie an das Kind."""
    if not isinstance(daten, dict) or set(daten) != {"urteil", "hinweis", "empfohlene_stufe"}:
        return UNKLAR
    urteil = daten["urteil"]
    if not isinstance(urteil, str) or urteil not in URTEILE:
        return UNKLAR
    stufe = daten["empfohlene_stufe"]
    if isinstance(stufe, bool) or not isinstance(stufe, int) or not 1 <= stufe <= 5:
        stufe = 1
    hinweis = ""
    if urteil != "richtig":
        hinweis = hinweis_pruefen(
            daten["hinweis"], aufgabe_text=aufgabe_text, versuch=versuch, bekannte=bekannte
        )
    return Bewertung(urteil, hinweis, stufe)


def antwort_kuerzen(text, maximum):
    """Antwort auf ``maximum`` Zeichen kürzen, möglichst am Satzende; Leerraum bereinigen."""
    text = "\n".join(zeile.rstrip() for zeile in str(text or "").strip().splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= maximum:
        return text
    kurz = text[:maximum]
    ende = max(kurz.rfind(". "), kurz.rfind("! "), kurz.rfind("? "), kurz.rfind("\n"))
    if ende >= maximum // 2:
        return kurz[: ende + 1].rstrip()
    return kurz.rstrip() + "…"
