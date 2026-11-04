"""Generatoren Klasse 8: Gleichungen, Terme, Prozent, Zinsen, Dreisatz, Potenzen, Negatives.

Gleichungen haben immer genau eine ganzzahlige Lösung; Euro-Ergebnisse haben höchstens zwei
Nachkommastellen; Wurzeln sind exakt.
"""

from fractions import Fraction

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from . import term
from .aufgabe import Roh
from .bausteine import MINUS, klammer_neg, lsg_gleichung, lsg_term, lsg_zahl, waehle, zahl_text
from .registry import generator

TERME = "mathe_8_terme"
PROZENT = "mathe_8_prozent"
DREISATZ = "mathe_8_dreisatz"
POTENZEN = "mathe_8_potenzen"
NEGATIV = "mathe_8_negativ"

_HOCH = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def hoch_text(n):
    return "".join(_HOCH[int(z)] for z in str(n))


def _koeff(c, var, *, erstes=True):
    """``3x``, ``x``, ``−2x`` oder bei leerer Variable die Zahl; mit Vorzeichen-Verbinder."""
    betrag = abs(c)
    teil = (str(betrag) if (betrag != 1 or not var) else "") + var
    if erstes:
        return (MINUS if c < 0 else "") + teil
    return f" {MINUS if c < 0 else '+'} {teil}"


def _summe_text(summanden):
    """``[(3, "x"), (-5, "")]`` -> ``3x − 5``; Summanden mit Koeffizient 0 entfallen."""
    text = ""
    for c, var in summanden:
        if c == 0:
            continue
        text += _koeff(c, var, erstes=not text)
    return text or "0"


# --- Gleichungen ----------------------------------------------------------------------------------


@generator("gleichung_linear", gettext_noop("Lineare Gleichungen"), thema=TERME, klassenstufe=8)
def gleichung_linear(rng, d, ctx):
    x = rng.randint(2, 15)
    if d == 1:
        if rng.random() < 0.5:
            a = rng.randint(1, 30)
            text, typ = f"x + {a} = {x + a}", "plus"
        else:
            a = rng.randint(1, x - 1)
            text, typ = f"x − {a} = {x - a}", "minus"
    elif d == 2:
        a = rng.randint(2, 9)
        text, typ = f"{a}x = {a * x}", "mal"
    elif d == 3:
        a, b = rng.randint(2, 9), rng.randint(1, 20)
        if rng.random() < 0.5:
            text, typ = f"{a}x + {b} = {a * x + b}", "mal_plus"
        else:
            text, typ = f"{a}x − {b} = {a * x - b}", "mal_minus"
    elif d == 4:
        x = rng.choice([v for v in range(-10, 11) if v != 0])
        a, c = waehle(
            rng, lambda: (rng.randint(2, 9), rng.randint(1, 8)), lambda p: p[0] > p[1], (5, 2)
        )
        b = rng.randint(-12, 12)
        e = a * x + b - c * x
        text = f"{_summe_text([(a, 'x'), (b, '')])} = {_summe_text([(c, 'x'), (e, '')])}"
        typ = "x_beidseitig"
    else:
        x = rng.choice([v for v in range(-10, 16) if v != 0])
        a, b = rng.randint(2, 6), rng.randint(1, 9)
        if rng.random() < 0.5:
            text, typ = f"{a}(x + {b}) = {a * (x + b)}", "klammer"
        else:
            e = rng.randint(1, 15)
            text = f"{a}(x − {b}) + {e} = {a * (x - b) + e}"
            typ = "klammer_plus"
    text = text.replace("-", MINUS)
    return Roh(
        typ,
        _("Löse die Gleichung: %(g)s") % {"g": text},
        lsg_gleichung(x),
        {"gleichung": text, "loesung": x},
    )


# --- Terme ----------------------------------------------------------------------------------------


def _koeff_zieher(rng, hoch=9):
    return rng.choice([c for c in range(-hoch, hoch + 1) if c != 0])


@generator("term_zusammenfassen", gettext_noop("Terme zusammenfassen"), thema=TERME, klassenstufe=8)
def term_zusammenfassen(rng, d, ctx):
    monome = {
        1: ["x"],
        2: ["x", ""],
        3: ["x", ""],
        4: ["a", "b"],
        5: ["x²", "x", ""],
    }[d]

    def ziehen():
        summanden = []
        for m in monome:
            n = 2 if m == monome[0] else rng.randint(1, 2)
            summanden += [(_koeff_zieher(rng, 9 if d > 1 else 6), m) for _i in range(n)]
        rng.shuffle(summanden)
        if d == 1:
            summanden = [(abs(c), m) for c, m in summanden[:2]]
        return summanden

    def gut(summanden):
        # jedes Monom kommt vor, keiner der Koeffizienten hebt sich zu 0 auf
        sums = {}
        for c, m in summanden:
            sums[m] = sums.get(m, 0) + c
        return len(sums) == len(monome) and all(v != 0 for v in sums.values())

    summanden = waehle(rng, ziehen, gut, [(2, monome[0]), (3, monome[0])])
    text = _summe_text(summanden)
    p = term.lesen(text)
    return Roh(
        f"zusammenfassen_{len(monome)}",
        _("Fasse zusammen: %(t)s") % {"t": text},
        lsg_term(p),
        {"term": text},
    )


def _klammer_text(b, var="x", koeff=1):
    return "(" + _summe_text([(koeff, var), (b, "")]) + ")"


@generator(
    "term_ausmultiplizieren", gettext_noop("Terme ausmultiplizieren"), thema=TERME, klassenstufe=8
)
def term_ausmultiplizieren(rng, d, ctx):
    if d == 1:
        a, b = rng.randint(2, 9), rng.randint(1, 9)
        text, typ = f"{a}{_klammer_text(b)}", "faktor_klammer"
    elif d == 2:
        a, k, b = rng.randint(2, 6), rng.randint(2, 5), _koeff_zieher(rng, 9)
        text, typ = f"{a}{_klammer_text(b, koeff=k)}", "faktor_klammer_koeff"
    elif d == 3:
        a, k, b = rng.randint(2, 7), rng.choice((1, 2, 3)), _koeff_zieher(rng, 9)
        text, typ = f"{MINUS}{a}{_klammer_text(b, koeff=k)}", "minus_klammer"
    elif d == 4:
        a, b = _koeff_zieher(rng, 9), _koeff_zieher(rng, 9)
        text, typ = f"{_klammer_text(a)}{_klammer_text(b)}", "zwei_klammern"
    else:
        if rng.random() < 0.5:
            k, a, b = rng.randint(2, 4), _koeff_zieher(rng, 7), _koeff_zieher(rng, 7)
            text = f"{_klammer_text(a, koeff=k)}{_klammer_text(b)}"
            typ = "zwei_klammern_koeff"
        else:
            a, b = rng.randint(2, 5), _koeff_zieher(rng, 6)
            c, e = rng.randint(2, 5), _koeff_zieher(rng, 6)
            text = f"{a}{_klammer_text(b)} + {c}{_klammer_text(e)}"
            typ = "zwei_produkte"
    p = term.lesen(text)
    return Roh(
        typ,
        _("Multipliziere aus und fasse zusammen: %(t)s") % {"t": text},
        lsg_term(p),
        {"term": text},
    )


# --- Prozent und Zinsen ---------------------------------------------------------------------------


def _euro(q):
    return zahl_text(q, 2)


@generator("prozent_rechnen", gettext_noop("Prozentrechnung"), thema=PROZENT, klassenstufe=8)
def prozent_rechnen(rng, d, ctx):
    oben = ctx.lim(800)
    prozente = (5, 10, 12, 15, 20, 25, 30, 40, 60, 75, 80)
    p = rng.choice(prozente)
    g = waehle(
        rng,
        lambda: 20 * rng.randint(1, max(1, oben // 20)),
        lambda x: (p * x) % 100 == 0,
        100,
    )
    w = Fraction(p * g, 100)
    param = {"grundwert": g, "prozent": p}
    if d == 1:
        return Roh(
            "prozentwert",
            _("Berechne %(p)s %% von %(g)s.") % {"p": p, "g": g},
            lsg_zahl(w),
            param,
        )
    if d == 2:
        return Roh(
            "prozentsatz",
            _("Wie viel Prozent sind %(w)s von %(g)s?") % {"w": w, "g": g},
            lsg_zahl(p, prozent=True),
            param,
        )
    if d == 3:
        return Roh(
            "grundwert",
            _("%(w)s sind %(p)s %% des Grundwerts. Wie groß ist der Grundwert?") % {"w": w, "p": p},
            lsg_zahl(g),
            param,
        )
    if d == 4:
        preis = 5 * rng.randint(4, max(4, oben // 10))
        rabatt = rng.choice((5, 10, 15, 20, 25, 30))
        return Roh(
            "rabatt",
            _(
                "Ein Pullover kostet %(g)s €. Im Angebot gibt es %(p)s %% Rabatt. "
                "Wie viel kostet er jetzt?"
            )
            % {"g": preis, "p": rabatt},
            lsg_zahl(Fraction(preis * (100 - rabatt), 100), einheit="€", stellen=2),
            {"grundwert": preis, "prozent": rabatt},
        )
    if rng.random() < 0.5:
        netto = 10 * rng.randint(2, max(2, oben // 10))
        return Roh(
            "mehrwertsteuer",
            _(
                "Eine Ware kostet netto %(n)s €. Dazu kommen 19 %% Mehrwertsteuer. Wie hoch ist "
                "der Bruttopreis?"
            )
            % {"n": netto},
            lsg_zahl(Fraction(netto * 119, 100), einheit="€", stellen=2),
            {"netto": netto, "prozent": 19},
        )
    alt = 20 * rng.randint(2, max(2, oben // 20))
    plus = rng.choice((5, 10, 15, 20, 25, 30, 50))
    plus_wert = Fraction(alt * plus, 100)
    return Roh(
        "aenderung_prozent",
        _("Ein Preis steigt von %(a)s € auf %(b)s €. Um wie viel Prozent ist er gestiegen?")
        % {"a": alt, "b": zahl_text(alt + plus_wert)},
        lsg_zahl(plus, prozent=True),
        {"alt": alt, "prozent": plus},
    )


@generator("zinsen", gettext_noop("Zinsrechnung"), thema=PROZENT, klassenstufe=8)
def zinsen(rng, d, ctx):
    oben = ctx.lim(5000)
    k = 100 * rng.randint(1, max(1, oben // 100))
    p = rng.randint(1, 5)
    param = {"kapital": k, "prozent": p}
    if d == 1:
        return Roh(
            "jahreszinsen",
            _(
                "Ein Guthaben von %(k)s € wird ein Jahr lang mit %(p)s %% verzinst. Wie hoch "
                "sind die Zinsen?"
            )
            % {"k": k, "p": p},
            lsg_zahl(Fraction(k * p, 100), einheit="€", stellen=2),
            param,
        )
    if d == 2:
        p2 = Fraction(rng.choice((5, 15, 25, 35, 45)), 10)
        k = 200 * rng.randint(1, max(1, oben // 200))
        return Roh(
            "jahreszinsen_dezimal",
            _(
                "Ein Guthaben von %(k)s € wird ein Jahr lang mit %(p)s %% verzinst. Wie hoch "
                "sind die Zinsen?"
            )
            % {"k": k, "p": zahl_text(p2)},
            lsg_zahl(k * p2 / 100, einheit="€", stellen=2),
            {"kapital": k, "prozent": str(p2)},
        )
    if d == 3:
        z = Fraction(k * p, 100)
        return Roh(
            "zinssatz",
            _("Auf %(k)s € gibt es in einem Jahr %(z)s € Zinsen. Wie hoch ist der Zinssatz?")
            % {"k": k, "z": zahl_text(z)},
            lsg_zahl(p, prozent=True),
            param,
        )
    if d == 4:
        z = Fraction(k * p, 100)
        return Roh(
            "kapital",
            _(
                "Bei einem Zinssatz von %(p)s %% gibt es in einem Jahr %(z)s € Zinsen. Wie hoch "
                "ist das Kapital?"
            )
            % {"p": p, "z": zahl_text(z)},
            lsg_zahl(k, einheit="€"),
            param,
        )
    if rng.random() < 0.5:
        k = 1200 * rng.randint(1, max(1, oben // 1200))
        m = rng.choice((3, 6, 9))
        return Roh(
            "monatszinsen",
            _(
                "%(k)s € werden %(m)s Monate lang mit %(p)s %% pro Jahr verzinst. Wie hoch sind "
                "die Zinsen?"
            )
            % {"k": k, "m": m, "p": p},
            lsg_zahl(Fraction(k * p * m, 1200), einheit="€", stellen=2),
            {"kapital": k, "prozent": p, "monate": m},
        )
    p = rng.choice((2, 4, 5, 10))
    k = 100 * rng.randint(1, max(1, oben // 500))
    return Roh(
        "zinseszins",
        _(
            "%(k)s € werden 2 Jahre lang mit %(p)s %% pro Jahr verzinst (Zinseszins). Wie viel "
            "Geld ist es danach?"
        )
        % {"k": k, "p": p},
        lsg_zahl(Fraction(k * (100 + p) ** 2, 10000), einheit="€", stellen=2),
        {"kapital": k, "prozent": p, "jahre": 2},
    )


# --- Dreisatz -------------------------------------------------------------------------------------


@generator(
    "dreisatz_proportional", gettext_noop("Dreisatz (proportional)"), thema=DREISATZ, klassenstufe=8
)
def dreisatz_proportional(rng, d, ctx):
    stueck = Fraction(rng.randint(10, 300), 100)  # Preis je Stück/kg, höchstens 2 Stellen
    if d == 1:
        n1 = rng.randint(2, 5)
        n2 = n1 * rng.randint(2, 3)
    elif d == 2:
        n1, n2 = rng.randint(2, 10), rng.randint(11, 20)
    elif d == 3:
        n1 = rng.choice((4, 6, 8, 10, 12))
        n2 = rng.choice([n for n in (1, 2, 3, 5, 15, 20) if n != n1])
    else:
        n1, n2 = waehle(
            rng,
            lambda: (rng.randint(3, 40), rng.randint(2, 40)),
            lambda x: x[0] != x[1],
            (5, 8),
        )
    k = rng.randrange(3)
    if k == 0:
        text = _("%(a)s Hefte kosten %(p)s €. Wie viel kosten %(b)s Hefte?") % {
            "a": n1,
            "p": _euro(n1 * stueck),
            "b": n2,
        }
        einheit, stellen_ = "€", 2
    elif k == 1:
        text = _("%(a)s kg Äpfel kosten %(p)s €. Wie viel kosten %(b)s kg?") % {
            "a": n1,
            "p": _euro(n1 * stueck),
            "b": n2,
        }
        einheit, stellen_ = "€", 2
    else:
        n1, n2 = 10 * n1, 10 * n2
        verbrauch = Fraction(rng.randint(4, 9), 100)
        text = _(
            "Ein Auto verbraucht auf %(a)s km %(v)s Liter. Wie viele Liter braucht es auf %(b)s km?"
        ) % {
            "a": n1,
            "v": zahl_text(n1 * verbrauch),
            "b": n2,
        }
        einheit, stellen_ = "l", None
        stueck = verbrauch
    return Roh(
        "dreisatz_prop",
        text,
        lsg_zahl(n2 * stueck, einheit=einheit, stellen=stellen_),
        {"n1": n1, "n2": n2, "einheitswert": str(stueck), "szenario": k},
    )


@generator(
    "dreisatz_antiproportional",
    gettext_noop("Dreisatz (antiproportional)"),
    thema=DREISATZ,
    klassenstufe=8,
)
def dreisatz_antiproportional(rng, d, ctx):
    gesamt = rng.choice(
        {1: (12, 24), 2: (24, 36, 48), 3: (36, 48, 60), 4: (60, 72, 120)}.get(d, (120, 180, 240))
    )
    teiler = [n for n in range(2, 31) if gesamt % n == 0 and gesamt // n >= 2]
    n1, n2 = waehle(
        rng,
        lambda: (rng.choice(teiler), rng.choice(teiler)),
        lambda x: x[0] != x[1],
        (teiler[0], teiler[1]),
    )
    t1, t2 = gesamt // n1, gesamt // n2
    k = rng.randrange(3)
    if k == 0:
        text = _(
            "%(a)s Arbeiter brauchen für eine Arbeit %(t)s Tage. Wie viele Tage brauchen %(b)s "
            "Arbeiter?"
        ) % {"a": n1, "t": t1, "b": n2}
        einheit = "Tage"
    elif k == 1:
        text = _(
            "Ein Vorrat reicht für %(a)s Personen %(t)s Tage. Wie lange reicht er für %(b)s "
            "Personen?"
        ) % {
            "a": n1,
            "t": t1,
            "b": n2,
        }
        einheit = "Tage"
    else:
        text = _(
            "%(a)s Pumpen leeren ein Becken in %(t)s Stunden. Wie lange brauchen %(b)s Pumpen?"
        ) % {
            "a": n1,
            "t": t1,
            "b": n2,
        }
        einheit = "h"
    return Roh(
        "dreisatz_anti",
        text,
        lsg_zahl(t2, einheit=einheit),
        {"n1": n1, "n2": n2, "t1": t1, "gesamt": gesamt, "szenario": k},
    )


# --- Potenzen und Wurzeln -------------------------------------------------------------------------


def _pot_text(basis, exp):
    return f"{klammer_neg(basis)}{hoch_text(exp)}"


@generator("potenzen", gettext_noop("Potenzen"), thema=POTENZEN, klassenstufe=8)
def potenzen(rng, d, ctx):
    if d == 1:
        b, e = rng.randint(2, 12), 2
        text, wert, typ = _pot_text(b, e), b**e, "quadrat"
    elif d == 2:
        b, e = rng.choice(((rng.randint(2, 6), 3), (10, rng.randint(2, 5)), (2, rng.randint(4, 8))))
        text, wert, typ = _pot_text(b, e), b**e, "potenz"
    elif d == 3:
        b, e = -rng.randint(2, 6), rng.choice((2, 3))
        text, wert, typ = _pot_text(b, e), b**e, "negative_basis"
    elif d == 4:
        b1, e1, b2, e2 = rng.randint(2, 5), 3, rng.randint(2, 9), 2
        op = rng.choice("+-")
        wert = b1**e1 + b2**e2 if op == "+" else b1**e1 - b2**e2
        text, typ = f"{_pot_text(b1, e1)} {op.replace('-', MINUS)} {_pot_text(b2, e2)}", "summe"
        b, e = b1, e1
    else:
        b1, e1, b2, e2 = -rng.randint(2, 4), rng.choice((2, 3)), rng.randint(2, 5), 2
        k = rng.randint(2, 4)
        text = f"{_pot_text(b1, e1)} · {k} {MINUS} {_pot_text(b2, e2)}"
        wert, typ = b1**e1 * k - b2**e2, "gemischt"
        b, e = b1, e1
    return Roh(typ, f"{text} = ?", lsg_zahl(wert), {"basis": b, "hochzahl": e})


@generator("wurzeln", gettext_noop("Wurzeln"), thema=POTENZEN, klassenstufe=8)
def wurzeln(rng, d, ctx):
    if d == 1:
        a = rng.randint(1, 12)
        return Roh("wurzel", f"√{a * a} = ?", lsg_zahl(a), {"radikand": a * a})
    if d == 2:
        a = rng.randint(11, 25)
        return Roh("wurzel", f"√{a * a} = ?", lsg_zahl(a), {"radikand": a * a})
    if d == 3:
        k = rng.randint(2, 19)
        q = Fraction(k * k, 100)
        return Roh(
            "wurzel_dezimal",
            f"√{zahl_text(q)} = ?",
            lsg_zahl(Fraction(k, 10)),
            {"radikand": str(q)},
        )
    if d == 4:
        a, b = rng.randint(2, 12), rng.randint(2, 12)
        op = rng.choice("+-")
        if op == "-" and a <= b:
            a, b = b + 1, a
        wert = a + b if op == "+" else a - b
        return Roh(
            "wurzel_summe",
            f"√{a * a} {op.replace('-', MINUS)} √{b * b} = ?",
            lsg_zahl(wert),
            {"a": a * a, "b": b * b},
        )
    if rng.random() < 0.5:
        a, b, c = rng.choice(((3, 4, 5), (6, 8, 10), (5, 12, 13), (8, 15, 17), (9, 12, 15)))
        return Roh(
            "wurzel_pythagoras",
            f"√({a * a} + {b * b}) = ?",
            lsg_zahl(c),
            {"a": a * a, "b": b * b},
        )
    a = rng.randint(11, 25)
    return Roh(
        "quadrat_umkehren",
        _("Welche positive Zahl hat das Quadrat %(q)s?") % {"q": a * a},
        lsg_zahl(a),
        {"quadrat": a * a},
    )


# --- Negative Zahlen ------------------------------------------------------------------------------


@generator(
    "negative_zahlen", gettext_noop("Rechnen mit negativen Zahlen"), thema=NEGATIV, klassenstufe=8
)
def negative_zahlen(rng, d, ctx):
    if d == 1:
        a, b = rng.randint(2, 15), rng.randint(2, 30)
        a, b = min(a, b - 1), max(a + 1, b)
        text, wert, typ = f"{MINUS}{a} + {b}", b - a, "neg_plus_pos"
    elif d == 2:
        a = rng.randint(1, 15)
        b = a + rng.randint(1, 15)
        text, wert, typ = f"{a} {MINUS} {b}", a - b, "pos_minus_gross"
    elif d == 3:
        a, b = rng.randint(2, 15), rng.randint(2, 15)
        art = rng.randrange(4)
        text, wert, typ = [
            (f"{MINUS}{a} {MINUS} {b}", -a - b, "neg_minus_pos"),
            (f"{a} + ({MINUS}{b})", a - b, "plus_klammer_neg"),
            (f"{MINUS}{a} + ({MINUS}{b})", -a - b, "neg_plus_klammer_neg"),
            (f"{a} {MINUS} ({MINUS}{b})", a + b, "minus_klammer_neg"),
        ][art]
    elif d == 4:
        a, b = rng.randint(2, 12), rng.randint(2, 9)
        sa, sb = rng.choice((1, -1)), rng.choice((1, -1))
        if sa == sb == 1:
            sa = -1
        if rng.random() < 0.5:
            text = f"{klammer_neg(sa * a)} · {klammer_neg(sb * b)}"
            wert, typ = sa * a * sb * b, "malnehmen"
        else:
            text = f"{klammer_neg(sa * a * b)} : {klammer_neg(sb * b)}"
            wert, typ = sa * sb * a, "teilen"
    else:
        a, b, c = rng.randint(2, 9), rng.randint(2, 9), rng.randint(1, 20)
        art = rng.randrange(3)
        if art == 0:
            text, wert, typ = (
                f"{klammer_neg(-a)} · {klammer_neg(-b)} + {c}",
                a * b + c,
                "produkt_plus",
            )
        elif art == 1:
            text, wert, typ = (
                f"{klammer_neg(-a)} · {b} {MINUS} {c}",
                -a * b - c,
                "produkt_minus",
            )
        else:
            text, wert, typ = (
                f"{c} {MINUS} ({MINUS}{a}) · {b}",
                c + a * b,
                "punkt_vor_strich",
            )
    return Roh(typ, f"{text} = ?", lsg_zahl(wert), {"term": text})
