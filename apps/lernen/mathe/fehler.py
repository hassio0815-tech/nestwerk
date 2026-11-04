"""Fehleranalyse für Mathe-Antworten (SPEC 21.13, Etappe 10b): regelbasiert, ohne KI.

Zu jeder Rechenart gibt es kleine *Fehlermodelle*: Sie rechnen aus den Zahlen der Aufgabe aus, was
bei einem typischen Fehler herauskäme (Übertrag vergessen, Nenner mitgerechnet, Klammer
ignoriert ...).
Stimmt die falsche Antwort des Kindes mit so einem Wert überein, ist das der ``fehlertyp``. Dazu
kommen allgemeine Regeln (Vorzeichen, um eins oder zehn daneben, Komma verrutscht, Zahlendreher).

Der Hinweis nennt nie die Lösung: Er steht als fester Text je Fehlertyp (ohne Zahlen) da und läuft
trotzdem noch einmal durch ``leckt``. Das ist eine Heuristik: Mehrere Fehler können denselben Wert
ergeben, dann gewinnt die erste Regel; ein unbekannter Fehler bekommt einen neutralen Hinweis.
"""

import re
from fractions import Fraction
from math import floor, gcd

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from . import antwort, term
from .aufgabe import GLEICHUNG, REST, TERM
from .bausteine import kgv, runden
from .hilfe import ausdruck
from .hilfe.bau import leckt

NEUTRAL = gettext_noop(
    "Das stimmt noch nicht. Rechne noch einmal Schritt für Schritt nach. Du schaffst das."
)

HINWEISE = {
    # Fehler, die schon die Antwortprüfung erkennt
    "unlesbar": gettext_noop(
        "Ich konnte deine Antwort nicht als Zahl lesen. Schreibe nur die Zahl, wenn nötig mit "
        "Komma."
    ),
    "einheit": gettext_noop("Prüfe die Einheit in deiner Antwort. Passt sie zur Frage?"),
    "variable": gettext_noop(
        "Prüfe den Buchstaben in deiner Antwort. Welche Unbekannte wird gesucht?"
    ),
    # schriftlich Rechnen
    "uebertrag_vergessen": gettext_noop(
        "Schau noch einmal auf den Übertrag: Wird eine Stelle zweistellig, gehört die Zehnerziffer "
        "zur nächsten Stelle."
    ),
    "uebertrag_doppelt": gettext_noop(
        "Prüfe deine Überträge. Hast du einen Übertrag zu oft oder an der falschen Stelle "
        "gerechnet?"
    ),
    "entbuendeln_vergessen": gettext_noop(
        "Wenn du bei einer Stelle einen Zehner geholt hast, ist die Nachbarstelle um eins kleiner. "
        "Hast du daran gedacht?"
    ),
    "kleinere_von_groesserer": gettext_noop(
        "Beim Minus steht die obere Zahl vorne. Rechne bei jeder Stelle oben minus unten. Ist oben "
        "die kleinere Ziffer, holst du dir einen Zehner von links."
    ),
    "reihe_verrutscht": gettext_noop(
        "Du bist in der Reihe eine Aufgabe danebengerutscht. Zähle noch einmal in der Reihe oder "
        "nutze die Tauschaufgabe."
    ),
    "andere_rechenart": gettext_noop(
        "Prüfe die Rechenart. Soll es plus, minus, mal oder geteilt sein?"
    ),
    "richtung_vertauscht": gettext_noop(
        "Prüfe die Richtung. Von der großen zur kleinen Einheit rechnest du mal, von der kleinen "
        "zur großen geteilt."
    ),
    "umrechnung_vergessen": gettext_noop(
        "Hast du alles in dieselbe Einheit umgerechnet, bevor du weiterrechnest?"
    ),
    "nullen_vergessen": gettext_noop(
        "Bei den Zehnern, Hundertern und so weiter muss hinten eine Null (oder mehr) dazukommen. "
        "Hast du die Teilergebnisse richtig verschoben?"
    ),
    "null_vergessen": gettext_noop(
        "Prüfe, ob irgendwo im Ergebnis eine Stelle nur Null ist. Auch dann schreibst du eine Null "
        "hin."
    ),
    "rest_zu_gross": gettext_noop(
        "Der Rest muss immer kleiner sein als der Teiler. Passt der Teiler noch einmal in deinen "
        "Rest?"
    ),
    "rest_falsch": gettext_noop(
        "Prüfe den Rest: Rechne Teiler mal Ergebnis und schau, wie viel dann bis zur ersten Zahl "
        "fehlt."
    ),
    # Brüche und Dezimalzahlen
    "falsch_gekuerzt": gettext_noop(
        "Beim Kürzen teilst du Zähler und Nenner durch dieselbe Zahl, nicht nur einen von beiden."
    ),
    "addiert_statt_multipliziert": gettext_noop(
        "Beim Erweitern wird malgenommen, nicht addiert. Zähler und Nenner mit derselben Zahl "
        "malnehmen."
    ),
    "nenner_mitgerechnet": gettext_noop(
        "Beim Plus und Minus von Brüchen mit gleichem Nenner bleibt der Nenner gleich. Du rechnest "
        "nur mit den Zählern."
    ),
    "zaehler_nicht_erweitert": gettext_noop(
        "Hast du beide Brüche auf den gemeinsamen Nenner gebracht? Dann musst du auch die Zähler "
        "mit erweitern."
    ),
    "auf_ab_verwechselt": gettext_noop(
        "Schau auf die Ziffer gleich rechts von der Zielstelle. Ist sie groß (obere Hälfte der "
        "Ziffern), rundest du auf, ist sie klein, rundest du ab."
    ),
    "falsche_stelle": gettext_noop(
        "Prüfe die Zielstelle. Auf welche Stelle sollst du genau runden?"
    ),
    "kommas_nicht_untereinander": gettext_noop(
        "Schreibe die Zahlen so untereinander, dass Komma unter Komma steht. Fehlende Stellen "
        "füllst du mit Nullen."
    ),
    # Prozent und Zinsen
    "hundert_vergessen": gettext_noop(
        "Denke an Prozent: Es geht um Hundertstel. Musst du irgendwo durch hundert teilen oder mit "
        "hundert malnehmen?"
    ),
    "prozent_umgedreht": gettext_noop(
        "Prüfe, was der Grundwert und was der Prozentwert ist. Welcher Teil gehört zu welchem "
        "Ganzen?"
    ),
    "prozentwert_statt_grundwert": gettext_noop(
        "Du hast eine Größe berechnet, die nicht gesucht ist. Gesucht ist das Ganze, der Grundwert."
    ),
    "rabatt_nicht_abgezogen": gettext_noop(
        "Du hast den Rabatt berechnet. Was bezahlst du am Ende?"
    ),
    "rabatt_addiert": gettext_noop(
        "Ein Rabatt macht den Preis kleiner. Wird er abgezogen oder dazugerechnet?"
    ),
    "steuer_nicht_addiert": gettext_noop(
        "Du hast die Steuer berechnet. Gesucht ist der Preis mit Steuer."
    ),
    "steuer_abgezogen": gettext_noop("Die Steuer kommt zum Preis dazu, sie wird nicht abgezogen."),
    "unterschied_nicht_in_prozent": gettext_noop(
        "Du hast den Unterschied in Euro. Gefragt sind aber Prozent. Welcher Teil vom alten Preis "
        "ist das?"
    ),
    "falscher_grundwert": gettext_noop(
        "Auf welchen Preis beziehen sich die Prozent, auf den alten oder den neuen? Meist ist es "
        "der alte."
    ),
    "monate_vergessen": gettext_noop(
        "Die Zinsen für ein ganzes Jahr sind erst der erste Schritt. Welcher Teil vom Jahr sind "
        "die Monate?"
    ),
    "zinseszins_vergessen": gettext_noop(
        "Im zweiten Jahr gibt es Zinsen auf das neue Guthaben, nicht nur auf das Startkapital."
    ),
    "zinsen_statt_guthaben": gettext_noop(
        "Du hast nur die Zinsen berechnet. Gesucht ist das ganze Guthaben mit dem Startbetrag."
    ),
    # Reihenfolge, Potenzen, Wurzeln, Vorzeichen
    "punkt_vor_strich_ignoriert": gettext_noop(
        "Denke an Punkt vor Strich: Mal und Geteilt kommen vor Plus und Minus."
    ),
    "klammer_ignoriert": gettext_noop("Was in der Klammer steht, rechnest du zuerst."),
    "mal_statt_hoch": gettext_noop(
        "Eine Potenz ist ein mehrfaches Malnehmen derselben Zahl, nicht die Basis mal die Hochzahl."
    ),
    "wurzel_vergessen": gettext_noop(
        "Hast du die Wurzel gezogen? Gesucht ist die Zahl, die mit sich selbst malgenommen die "
        "Zahl unter der Wurzel ergibt."
    ),
    "wurzel_einzeln": gettext_noop(
        "Aus einer Summe unter der Wurzel darfst du nicht einzeln die Wurzel ziehen. Rechne zuerst "
        "unter der Wurzel."
    ),
    "halbiert_statt_wurzel": gettext_noop(
        "Die Wurzel ist nicht die Hälfte. Welche Zahl mit sich selbst malgenommen passt?"
    ),
    "vorzeichen": gettext_noop(
        "Prüfe das Vorzeichen deines Ergebnisses. Soll es plus oder minus sein?"
    ),
    "minus_in_klammer_vergessen": gettext_noop(
        "Schau auf die Vorzeichen in der Aufgabe. Minus und Minus hintereinander ergibt Plus."
    ),
    "vorzeichen_vorne_vergessen": gettext_noop("Das Minus ganz vorne gehört zur ersten Zahl."),
    # Gleichungen und Terme
    "gl_vorzeichen": gettext_noop(
        "Beim Umformen rechnest du auf beiden Seiten das Gegenteil. Aus Plus wird Minus und aus "
        "Minus wird Plus."
    ),
    "gl_nicht_geteilt": gettext_noop("Hast du am Ende noch durch die Zahl vor x geteilt?"),
    "gl_mal_statt_geteilt": gettext_noop(
        "Die Zahl vor x wirst du los, indem du durch sie teilst, nicht indem du malnimmst."
    ),
    "gl_klammer": gettext_noop(
        "Bei einer Klammer kannst du zuerst durch die Zahl vor der Klammer teilen und dann die "
        "Zahl in der Klammer wegschaffen."
    ),
    "ungleichartig": gettext_noop(
        "Fasse nur gleichartige Terme zusammen: x mit x und Zahlen mit Zahlen."
    ),
    "mittelterme_vergessen": gettext_noop(
        "Bei zwei Klammern gibt es vier Produkte. Hast du alle gebildet?"
    ),
    "nur_erstes_multipliziert": gettext_noop(
        "Die Zahl vor der Klammer wird mit jedem Teil in der Klammer malgenommen, nicht nur mit "
        "dem ersten."
    ),
    # Dreisatz
    "falsche_richtung": gettext_noop(
        "Prüfe, ob es mit der neuen Menge mehr oder weniger wird. Dreht sich dein Rechenweg in die "
        "richtige Richtung?"
    ),
    "nur_einheit": gettext_noop(
        "Du hast den Wert für eine Einheit. Gesucht ist aber der Wert für die neue Menge."
    ),
    "nur_gesamtaufwand": gettext_noop(
        "Das ist der Gesamtaufwand. Wie verteilt er sich auf die neue Anzahl?"
    ),
    # allgemeine Regeln
    "um_eins": gettext_noop(
        "Du bist ganz nah dran. Rechne noch einmal nach, vielleicht hast du dich bei einer Stelle "
        "um eins vertan."
    ),
    "um_zehn": gettext_noop("Fast: Schau noch einmal auf die Zehnerstelle."),
    "komma": gettext_noop(
        "Prüfe, wo das Komma steht und wie viele Nullen dazugehören. Ist dein Ergebnis viel zu "
        "groß oder viel zu klein?"
    ),
    "zahlendreher": gettext_noop(
        "Prüfe noch einmal, ob du beim Aufschreiben die Ziffern in der richtigen Reihenfolge "
        "hingeschrieben hast."
    ),
}

# Fehlertypen aus ``antwort.pruefen`` und ``prueferin``, die schon einen eigenen Hinweis mitbringen
VORHANDENE_TYPEN = frozenset({"nicht_gekuerzt", "form", "rest_fehlt", "nicht_vereinfacht"})


# Erkannte Rechenfehler geben dem Kind einen zweiten Versuch mit Hinweis. Antworten, die nur nicht
# lesbar sind oder die falsche Einheit oder Variable haben, bleiben wie bisher "noch nicht" (mit
# Hinweis).
ZWEITE_CHANCE = frozenset(HINWEISE) - {"unlesbar", "einheit", "variable"}


def typen():
    return tuple(HINWEISE)


def hinweis_text(fehlertyp, aufgabe=None):
    """Der freundliche Hinweis zum Fehlertyp (übersetzt). Unbekannt oder verräterisch: neutral."""
    msgid = HINWEISE.get(fehlertyp)
    if msgid is None:
        return _(NEUTRAL) if fehlertyp else ""
    text = _(msgid)
    if aufgabe is not None and leckt(text, aufgabe):
        return _(NEUTRAL)
    return text


# --- Registry der Fehlermodelle -------------------------------------------------------------------

_MODELLE = {}


def modell(*generatoren):
    def anmelden(funktion):
        for g in generatoren:
            _MODELLE.setdefault(g, []).append(funktion)
        return funktion

    return anmelden


def generatoren_mit_modell():
    return frozenset(_MODELLE)


def _F(x, y=1):
    return Fraction(x) / Fraction(y)


def _ziffern(n):
    return [int(c) for c in str(abs(int(n)))]


# --- Plus und Minus -------------------------------------------------------------------------------


def _teilmengen(positionen):
    ergebnis = []
    for maske in range(1, 1 << len(positionen)):
        ergebnis.append([p for i, p in enumerate(positionen) if maske >> i & 1])
    return ergebnis


@modell("add_sub_100", "add_sub_1000")
def _add_sub(a):
    A, B, plus = a.parameter["a"], a.parameter["b"], a.parameter["op"] == "+"
    ergebnis = []
    if plus:
        wert, uebertrag, pos, i, ohne = A + B, 0, [], 0, 0
        x, y = A, B
        while x or y or uebertrag:
            s = x % 10 + y % 10 + uebertrag
            if s >= 10:
                pos.append(i)
            ohne += ((x % 10 + y % 10) % 10) * 10**i
            uebertrag = s // 10
            x, y, i = x // 10, y // 10, i + 1
        ergebnis.append(("uebertrag_vergessen", ohne))
        for teil in _teilmengen(pos):
            ergebnis.append(("uebertrag_vergessen", wert - sum(10 ** (p + 1) for p in teil)))
        for p in pos:
            ergebnis.append(("uebertrag_doppelt", wert + 10 ** (p + 1)))
    else:
        wert, geliehen, pos, i, diff = A - B, 0, [], 0, 0
        x, y = A, B
        while x or y:
            da, db = x % 10 - geliehen, y % 10
            geliehen = 1 if da < db else 0
            if geliehen:
                pos.append(i)
            diff += abs(x % 10 - y % 10) * 10**i
            x, y, i = x // 10, y // 10, i + 1
        ergebnis.append(("kleinere_von_groesserer", diff))
        for teil in _teilmengen(pos):
            ergebnis.append(("entbuendeln_vergessen", wert + sum(10 ** (p + 1) for p in teil)))
    return ergebnis


@modell("einmaleins")
def _einmaleins(a):
    x, y = a.parameter["a"], a.parameter["b"]
    return [("reihe_verrutscht", x * y + d) for d in (x, -x, y, -y)]


@modell("mult_schriftlich")
def _mult(a):
    x, y = a.parameter["a"], a.parameter["b"]
    return [("nullen_vergessen", x * sum(_ziffern(y)))]


@modell("div_schriftlich")
def _div(a):
    d, t = a.parameter["dividend"], a.parameter["teiler"]
    soll = a.loesung
    ergebnis = [("andere_rechenart", _F(t, d))]
    if soll.form != REST:
        q = int(Fraction(soll.wert)) if Fraction(soll.wert).denominator == 1 else None
        if q is not None and "0" in str(q):
            ergebnis.append(("null_vergessen", int(str(q).replace("0", "") or 0)))
    return ergebnis


# --- Brüche und Dezimalzahlen ---------------------------------------------------------------------


@modell("bruch_kuerzen")
def _kuerzen(a):
    z, n = a.parameter["zaehler"], a.parameter["nenner"]
    g = gcd(z, n)
    return [("falsch_gekuerzt", _F(z // g, n)), ("falsch_gekuerzt", _F(z, n // g))]


@modell("bruch_erweitern")
def _erweitern(a):
    p, q, n = (a.parameter[k] for k in ("zaehler", "nenner", "neuer_nenner"))
    return [
        ("addiert_statt_multipliziert", p + n // q),
        ("addiert_statt_multipliziert", p + (n - q)),
        ("addiert_statt_multipliziert", n // q),
    ]


@modell("bruch_addsub")
def _bruch_addsub(a):
    (p1, q1), (p2, q2) = a.parameter["a"], a.parameter["b"]
    plus = a.parameter["op"] == "+"
    zaehler = p1 + p2 if plus else p1 - p2
    ergebnis = [("nenner_mitgerechnet", _F(zaehler, q1 + q2 if plus else abs(q1 - q2) or 1))]
    if q1 != q2:
        ergebnis.append(("zaehler_nicht_erweitert", _F(zaehler, q1 * q2)))
        ergebnis.append(("zaehler_nicht_erweitert", _F(zaehler, kgv(q1, q2))))
        ergebnis.append(("zaehler_nicht_erweitert", _F(zaehler, q1)))
    return ergebnis


@modell("dezimal_runden")
def _runden(a):
    q, stelle = _F(a.parameter["zahl"]), a.parameter["stelle"]
    faktor = Fraction(10) ** stelle
    ab = Fraction(floor(abs(q) * faktor)) / faktor
    auf = ab + 1 / faktor
    ergebnis = [("auf_ab_verwechselt", ab), ("auf_ab_verwechselt", auf)]
    ergebnis += [("falsche_stelle", runden(q, stelle + d)) for d in (1, -1)]
    return ergebnis


def _ohne_komma(q):
    k = 0
    while (q * 10**k).denominator != 1:
        k += 1
    return int(q * 10**k), k


@modell("dezimal_rechnen")
def _dezimal(a):
    p = a.parameter
    x, y = _F(p["a"]), _F(p["b"])
    ergebnis = [("andere_rechenart", w) for w in _paar_werte(x, y)]
    if a.typ in ("dezimal_add", "dezimal_sub"):
        (x0, kx), (y0, ky) = _ohne_komma(x), _ohne_komma(y)
        roh = x0 + y0 if a.typ == "dezimal_add" else x0 - y0
        for k in range(0, max(kx, ky) + 2):
            ergebnis.append(("kommas_nicht_untereinander", _F(roh, 10**k)))
    return ergebnis


# --- Prozent und Zinsen ---------------------------------------------------------------------------


@modell("prozent_anteil")
def _prozent_anteil(a):
    p = a.parameter
    if a.typ == "anteil_von_grundwert":
        x, g = p["anteil"], p["grundwert"]
        return [("hundert_vergessen", _F(x, g)), ("prozent_umgedreht", _F(100 * g, x))]
    return []


@modell("prozent_wert")
def _prozent_wert(a):
    pz, g = a.parameter["prozent"], a.parameter["grundwert"]
    return [("hundert_vergessen", _F(pz * g)), ("hundert_vergessen", _F(g, 100))]


@modell("prozent_rechnen")
def _prozent_rechnen(a):
    p, typ = a.parameter, a.typ
    if typ == "prozentwert":
        g, pz = p["grundwert"], p["prozent"]
        return [("hundert_vergessen", _F(g * pz)), ("hundert_vergessen", _F(g, 100))]
    if typ == "prozentsatz":
        g, pz = p["grundwert"], p["prozent"]
        w = _F(pz * g, 100)
        return [("hundert_vergessen", w / g), ("prozent_umgedreht", g / w * 100)]
    if typ == "grundwert":
        g, pz = p["grundwert"], p["prozent"]
        w = _F(pz * g, 100)
        return [("prozentwert_statt_grundwert", w * pz / 100), ("hundert_vergessen", w / pz)]
    if typ == "rabatt":
        g, pz = p["grundwert"], p["prozent"]
        nach = _F(g * pz, 100)
        return [("rabatt_nicht_abgezogen", nach), ("rabatt_addiert", g + nach)]
    if typ == "mehrwertsteuer":
        n = p["netto"]
        steuer = _F(n * p["prozent"], 100)
        return [("steuer_nicht_addiert", steuer), ("steuer_abgezogen", n - steuer)]
    alt, pz = p["alt"], p["prozent"]  # aenderung_prozent
    plus = _F(alt * pz, 100)
    return [
        ("unterschied_nicht_in_prozent", plus),
        ("falscher_grundwert", plus / (alt + plus) * 100),
        ("hundert_vergessen", plus / alt),
    ]


@modell("zinsen")
def _zinsen(a):
    p, typ = a.parameter, a.typ
    k, pz = p["kapital"], _F(p["prozent"])
    if typ in ("jahreszinsen", "jahreszinsen_dezimal"):
        return [("hundert_vergessen", k * pz)]
    if typ == "monatszinsen":
        jahr = k * pz / 100
        return [("monate_vergessen", jahr), ("monate_vergessen", jahr * p["monate"])]
    if typ == "zinseszins":
        j1 = k * pz / 100
        return [
            ("zinseszins_vergessen", k + 2 * j1),
            ("zinsen_statt_guthaben", j1 + (k + j1) * pz / 100),
        ]
    if typ == "zinssatz":
        z = k * pz / 100
        return [("hundert_vergessen", z / k)]
    z = k * pz / 100  # kapital
    return [("hundert_vergessen", z / pz), ("prozentwert_statt_grundwert", z * pz / 100)]


# --- Größen, Geld, Längen -------------------------------------------------------------------------


@modell("groessen_umrechnen")
def _groessen(a):
    from .generatoren_klasse6 import _FAKTOR

    p = a.parameter
    if a.typ == "mehrteilig":
        gross, klein = p["einheiten"]
        f = _FAKTOR[(gross, klein)]
        return [
            ("umrechnung_vergessen", _F(p["gross"] * f)),
            ("umrechnung_vergessen", _F(p["gross"] + p["klein"])),
        ]
    w, von, nach = _F(p["wert"]), p["von"], p["nach"]
    f = _FAKTOR.get((von, nach)) or _FAKTOR[(nach, von)]
    return [("richtung_vertauscht", w * f), ("richtung_vertauscht", w / f)]


@modell("geld")
def _geld(a):
    p = a.parameter
    if a.typ == "euro_cent_in_cent":
        return [
            ("umrechnung_vergessen", _F(p["euro"] * 100)),
            ("umrechnung_vergessen", _F(p["euro"] + p["cent"])),
        ]
    x, y = _geld_paar(a)
    return [("andere_rechenart", w) for w in _paar_werte(x, y)] if x is not None else []


def _geld_paar(a):
    p = a.parameter
    if a.typ == "summe":
        return _F(p["a"]), _F(p["b"])
    if a.typ == "wechselgeld":
        return _F(p["bezahlt"]), _F(p["kosten"])
    if a.typ == "mehrere_preise":
        return _F(p["n"]), _F(p["preis"])
    return None, None


@modell("laenge")
def _laenge(a):
    p = a.parameter
    if a.typ == "m_cm_in_cm":
        return [
            ("umrechnung_vergessen", _F(p["m"] * 100)),
            ("umrechnung_vergessen", _F(p["m"] + p["cm"])),
        ]
    if a.typ == "laengen_addieren":
        return [
            ("umrechnung_vergessen", _F(p["cm"] + p["cm2"])),
            ("umrechnung_vergessen", _F(p["m"] * 100 + p["cm"])),
            ("umrechnung_vergessen", _F(p["m"] + p["cm"] + p["cm2"])),
        ]
    return []


def _paar_werte(x, y):
    """Ergebnisse der anderen Rechenarten mit denselben zwei Zahlen."""
    x, y = _F(x), _F(y)
    werte = [x + y, x - y, y - x, x * y]
    if y:
        werte.append(x / y)
    if x:
        werte.append(y / x)
    return werte


@modell("umkehr", "division_ohne_rest")
def _paar_modelle(a):
    p = a.parameter
    if "ziel" in p:
        x, y = p["a"], p["ziel"]
    elif "faktor" in p:
        x, y = p["faktor"], p["produkt"]
    else:
        x, y = p["dividend"], p["teiler"]
    return [("andere_rechenart", w) for w in _paar_werte(x, y)]


@modell("add_sub_100", "add_sub_1000", "einmaleins", "mult_schriftlich")
def _paar_allgemein(a):
    x, y = a.parameter["a"], a.parameter["b"]
    return [("andere_rechenart", w) for w in _paar_werte(x, y)]


# --- Reihenfolge, Potenzen, Wurzeln, Vorzeichen ---------------------------------------------------


@modell("punkt_vor_strich", "klammern")
def _reihenfolge(a):
    text = _term_text(a)
    ergebnis = []
    for typ, optionen in (
        ("klammer_ignoriert", {"ohne_klammern": True}),
        ("punkt_vor_strich_ignoriert", {"links_nach_rechts": True}),
        ("punkt_vor_strich_ignoriert", {"links_nach_rechts": True, "ohne_klammern": True}),
    ):
        w = ausdruck.variante(text, **optionen)
        if w is not None:
            ergebnis.append((typ, w))
    return ergebnis


def _term_text(a):
    """Der Rechenausdruck der Aufgabe (ohne Aufgabentext davor)."""
    t = a.parameter.get("term")
    if t:
        return t
    return a.text


@modell("potenzen")
def _potenzen(a):
    text = a.text
    ergebnis = []
    w = ausdruck.variante(text, potenz_mal=True)
    if w is not None:
        ergebnis.append(("mal_statt_hoch", w))
    w = ausdruck.variante(text, links_nach_rechts=True)
    if w is not None:
        ergebnis.append(("punkt_vor_strich_ignoriert", w))
    return ergebnis


@modell("wurzeln")
def _wurzeln(a):
    p, typ = a.parameter, a.typ
    if typ in ("wurzel", "quadrat_umkehren"):
        rad = _F(p.get("radikand", p.get("quadrat")))
        return [("wurzel_vergessen", rad), ("halbiert_statt_wurzel", rad / 2)]
    if typ == "wurzel_dezimal":
        rad = _F(p["radikand"])
        return [("wurzel_vergessen", rad), ("halbiert_statt_wurzel", rad / 2)]
    x, y = _F(p["a"]), _F(p["b"])
    if typ == "wurzel_pythagoras":
        return [("wurzel_vergessen", x + y), ("wurzel_einzeln", _wurzel_summe(x, y))]
    return [("wurzel_vergessen", x + y), ("wurzel_vergessen", x - y)]


def _wurzel_summe(x, y):
    """√x + √y für Quadratzahlen (``None`` sonst, dann gibt es keinen Treffer)."""
    rx, ry = round(float(x) ** 0.5), round(float(y) ** 0.5)
    return _F(rx + ry) if rx * rx == x and ry * ry == y else None


@modell("negative_zahlen")
def _negative(a):
    text = a.parameter["term"]
    ergebnis = []
    ohne_klammer_minus = re.sub(r"\(−", "(", text)
    if ohne_klammer_minus != text:
        w = ausdruck.variante(ohne_klammer_minus)
        if w is not None:
            ergebnis.append(("minus_in_klammer_vergessen", w))
    if text.startswith("−"):
        w = ausdruck.variante(text[1:])
        if w is not None:
            ergebnis.append(("vorzeichen_vorne_vergessen", w))
    w = ausdruck.variante(text, links_nach_rechts=True)
    if w is not None:
        ergebnis.append(("punkt_vor_strich_ignoriert", w))
    return ergebnis


# --- Gleichungen und Terme ------------------------------------------------------------------------

_NUM = r"(−?\d+)"


def _zahl(text):
    return int(text.replace("−", "-"))


@modell("gleichung_linear")
def _gleichung(a):
    text = a.parameter["gleichung"].replace("-", "−")
    typ = a.typ
    try:
        if typ in ("plus", "minus"):
            x, c = re.fullmatch(rf"x [+−] {_NUM} = {_NUM}", text).groups()
            x, c = int(x), _zahl(c)
            return [("gl_vorzeichen", c + x if typ == "plus" else c - x)]
        if typ == "mal":
            x, c = (int(v) for v in re.fullmatch(rf"{_NUM}x = {_NUM}", text).groups())
            return [("gl_mal_statt_geteilt", c * x)]
        if typ in ("mal_plus", "mal_minus"):
            x, vz, b, c = re.fullmatch(rf"{_NUM}x ([+−]) {_NUM} = {_NUM}", text).groups()
            x, b, c = int(x), int(b), _zahl(c)
            plus = vz == "+"
            return [
                ("gl_vorzeichen", _F(c + b if plus else c - b, x)),
                ("gl_nicht_geteilt", _F(c - b if plus else c + b)),
            ]
        if typ == "klammer":
            x, b, c = re.fullmatch(rf"{_NUM}\(x \+ {_NUM}\) = {_NUM}", text).groups()
            x, b, c = int(x), int(b), _zahl(c)
            return [
                ("gl_vorzeichen", _F(c, x) + b),
                ("gl_klammer", _F(c - b)),
                ("gl_klammer", _F(c, x)),
            ]
        if typ == "klammer_plus":
            x, b, e, c = re.fullmatch(rf"{_NUM}\(x − {_NUM}\) \+ {_NUM} = {_NUM}", text).groups()
            x, b, e, c = int(x), int(b), int(e), _zahl(c)
            return [
                ("gl_vorzeichen", _F(c - e, x) - b),
                ("gl_vorzeichen", _F(c + e, x) + b),
                ("gl_klammer", _F(c, x) + b),
            ]
    except (AttributeError, ValueError):
        return []
    return []


def _poly(text):
    try:
        return term.lesen(text.replace("−", "-"))
    except term.TermFehler:
        return None


@modell("term_zusammenfassen")
def _zusammenfassen(a):
    from .hilfe.klasse8 import _summanden, _summe_text

    ergebnis = []
    summanden = _summanden(a.parameter["term"])
    gruppen = {}
    for c, m in summanden:
        gruppen.setdefault(m, 0)
        gruppen[m] += c
    ersterm = summanden[0][1] if summanden else ""
    gesamt = sum(c for c, _m in summanden)
    kandidaten = [
        ("ungleichartig", _summe_text([(gesamt, ersterm)])),
        ("ungleichartig", _summe_text([(gesamt, "x")])),
    ]
    absolut = {}
    for c, m in summanden:
        absolut[m] = absolut.get(m, 0) + abs(c)
    kandidaten.append(("vorzeichen", _summe_text([(v, m) for m, v in absolut.items()])))
    for typ, text in kandidaten:
        p = _poly(text)
        if p is not None:
            ergebnis.append((typ, p))
    return ergebnis


@modell("term_ausmultiplizieren")
def _ausmultiplizieren(a):
    from .hilfe.klasse8 import _faktoren, _produkte, _summanden, _summe_text

    text = a.parameter["term"]
    ergebnis = []
    produkte = _produkte(text)
    erster = []
    mittel = []
    for produkt in produkte:
        f = _faktoren(produkt)
        if len(f) == 2 and not f[0].startswith("("):
            c = f[0].replace("−", "-")
            teile = _summanden(f[1][1:-1])
            erster.append(
                f"({c})*({_summe_text(teile[:1])})"
                + "".join(f"+({_summe_text([t])})" for t in teile[1:])
            )
        elif len(f) == 2:
            links, rechts = _summanden(f[0][1:-1]), _summanden(f[1][1:-1])
            mittel.append(
                f"({_summe_text(links[:1])})*({_summe_text(rechts[:1])})"
                f"+({_summe_text(links[-1:])})*({_summe_text(rechts[-1:])})"
            )
        else:
            erster.append(produkt)
            mittel.append(produkt)
    for typ, teile in (("nur_erstes_multipliziert", erster), ("mittelterme_vergessen", mittel)):
        if teile and len(teile) == len(produkte):
            p = _poly("+".join(teile))
            if p is not None:
                ergebnis.append((typ, p))
    return ergebnis


# --- Dreisatz -------------------------------------------------------------------------------------


@modell("dreisatz_proportional")
def _prop(a):
    p = a.parameter
    n1, n2, e = p["n1"], p["n2"], _F(p["einheitswert"])
    return [("falsche_richtung", e * n1 * n1 / n2), ("nur_einheit", e)]


@modell("dreisatz_antiproportional")
def _anti(a):
    p = a.parameter
    return [
        ("falsche_richtung", _F(p["t1"] * p["n2"], p["n1"])),
        ("nur_gesamtaufwand", _F(p["gesamt"])),
    ]


# --- Auswerten ------------------------------------------------------------------------------------


def _eingabe_wert(aufgabe, eingabe):
    """Die Eingabe als Menge von Zahlenwerten (oder Polynom bei Termen); ``None`` wenn unlesbar."""
    soll = aufgabe.loesung
    s = str(eingabe).strip()
    if soll.form == TERM:
        try:
            return term.lesen(s)
        except term.TermFehler:
            return None
    if soll.form == GLEICHUNG:
        s = re.sub(r"^\s*[A-Za-z]\s*=\s*", "", s)
        s = re.sub(r"\s*=\s*[A-Za-z]\s*$", "", s)
    if soll.form == REST:
        m = re.match(r"^\s*(\d+)\s*(?:r|rest)\s*(\d+)\s*$", s, re.IGNORECASE)
        if m:
            return {Fraction(int(m.group(1)))}
    gelesen = antwort.lesen(s)
    if gelesen is None:
        return None
    return {w for w, _f in gelesen.kandidaten}


def _gleich(werte, kandidat, form):
    if kandidat is None:
        return False
    if form == TERM:
        return term.gleich(werte, kandidat)
    return Fraction(kandidat) in werte


def _soll_wert(aufgabe):
    s = aufgabe.loesung
    return None if s.form == TERM else Fraction(s.wert)


def _allgemein(aufgabe, werte):
    soll = Fraction(aufgabe.loesung.wert)
    ist = werte
    if soll != 0 and -soll in ist:
        return "vorzeichen"
    if soll != 0:
        for k in (1, 2, 3):
            if soll * 10**k in ist or soll / 10**k in ist:
                return "komma"
    if soll + 1 in ist or soll - 1 in ist:
        return "um_eins"
    if soll + 10 in ist or soll - 10 in ist:
        return "um_zehn"
    if soll.denominator == 1 and abs(soll) >= 10:
        ziffern = sorted(str(abs(int(soll))))
        for w in ist:
            if w.denominator == 1 and w != soll and sorted(str(abs(int(w)))) == ziffern:
                return "zahlendreher"
    return ""


def _rest_fehler(aufgabe, eingabe):
    m = re.match(r"^\s*(\d+)\s*(?:r|rest)\s*(\d+)\s*$", str(eingabe), re.IGNORECASE)
    if not m:
        return ""
    q, r = int(m.group(1)), int(m.group(2))
    t = aufgabe.parameter.get("teiler", 0)
    if t and r >= t:
        return "rest_zu_gross"
    if q == Fraction(aufgabe.loesung.wert) and r != aufgabe.loesung.rest:
        return "rest_falsch"
    return ""


def analysiere(aufgabe, eingabe):
    """Der Fehlertyp (Schlüssel aus ``HINWEISE``) zu einer falschen Eingabe, oder ``""``.

    Nur aufrufen, wenn die Eingabe nicht richtig ist. Heuristik: erste passende Regel gewinnt."""
    try:
        return _analysiere(aufgabe, eingabe)
    except (ArithmeticError, ValueError, TypeError, KeyError, AttributeError):
        return ""


def _analysiere(aufgabe, eingabe):
    soll = aufgabe.loesung
    werte = _eingabe_wert(aufgabe, eingabe)
    if werte is None:
        return ""
    if soll.form == REST:
        fehler = _rest_fehler(aufgabe, eingabe)
        if fehler:
            return fehler
    for funktion in _MODELLE.get(aufgabe.generator, ()):
        for typ, kandidat in funktion(aufgabe):
            if kandidat is None:
                continue
            if soll.form != TERM and Fraction(kandidat) == Fraction(soll.wert):
                continue
            if _gleich(werte, kandidat, soll.form):
                return typ
    if soll.form == TERM:
        return ""
    return _allgemein(aufgabe, werte)
