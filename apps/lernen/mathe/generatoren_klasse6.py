"""Generatoren Klasse 6: schriftlich Rechnen, Brüche, Dezimalzahlen, Prozent, Größen, Klammern.

Brüche werden am Ende gekürzt verlangt; Dezimalergebnisse sind immer endlich.
"""

from fractions import Fraction
from math import gcd

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from .aufgabe import Roh
from .bausteine import (
    kgv,
    lsg_bruch,
    lsg_rest,
    lsg_zahl,
    runden,
    waehle,
    zahl_text,
)
from .registry import generator

SCHRIFTLICH = "mathe_6_schriftlich"
BRUECHE = "mathe_6_brueche"
DEZIMAL = "mathe_6_dezimal"
PROZENT = "mathe_6_prozent"
GROESSEN = "mathe_6_groessen"
GESETZE = "mathe_6_rechengesetze"


# --- Schriftliches Rechnen ------------------------------------------------------------------------


def _zahl_mit_stellen(rng, stellen, ctx):
    unten, oben = 10 ** (stellen - 1), 10**stellen - 1
    return rng.randint(min(unten, ctx.lim(unten)), ctx.lim(oben))


@generator(
    "mult_schriftlich", gettext_noop("Schriftlich malnehmen"), thema=SCHRIFTLICH, klassenstufe=6
)
def mult_schriftlich(rng, d, ctx):
    sa, sb = {1: (2, 1), 2: (3, 1), 3: (2, 2), 4: (3, 2), 5: (3, 3)}[d]
    a, b = _zahl_mit_stellen(rng, sa, ctx), _zahl_mit_stellen(rng, sb, ctx)
    if sb == 1:
        b = max(2, b)
    return Roh(
        f"mult_{sa}x{sb}",
        _("Rechne schriftlich: %(a)s · %(b)s = ?") % {"a": a, "b": b},
        lsg_zahl(a * b),
        {"a": a, "b": b},
    )


def _div_ohne_rest(rng, teiler, quotient):
    a = teiler * quotient
    return Roh(
        "div_ohne_rest",
        _("Rechne schriftlich: %(a)s : %(b)s = ?") % {"a": a, "b": teiler},
        lsg_zahl(quotient),
        {"dividend": a, "teiler": teiler},
    )


def _div_rest(rng, teiler, quotient):
    rest = rng.randint(1, teiler - 1)
    a = teiler * quotient + rest
    return Roh(
        "div_mit_rest",
        _("Rechne schriftlich mit Rest: %(a)s : %(b)s = ?") % {"a": a, "b": teiler},
        lsg_rest(quotient, rest),
        {"dividend": a, "teiler": teiler},
    )


def _div_dezimal(rng, teiler, hoechst):
    a = waehle(rng, lambda: rng.randint(3, hoechst), lambda x: x % teiler != 0, teiler + 1)
    return Roh(
        "div_dezimal",
        _("Teile und gib das Ergebnis als Dezimalzahl an: %(a)s : %(b)s = ?")
        % {"a": a, "b": teiler},
        lsg_zahl(Fraction(a, teiler)),
        {"dividend": a, "teiler": teiler},
    )


@generator("div_schriftlich", gettext_noop("Schriftlich teilen"), thema=SCHRIFTLICH, klassenstufe=6)
def div_schriftlich(rng, d, ctx):
    if d == 1:
        return _div_ohne_rest(rng, rng.randint(2, 9), rng.randint(5, 20))
    if d == 2:
        return _div_ohne_rest(rng, rng.randint(2, 9), rng.randint(20, 150))
    if d == 3:
        return _div_rest(rng, rng.randint(2, 9), rng.randint(10, 99))
    if d == 4:
        if rng.random() < 0.5:
            return _div_ohne_rest(rng, rng.randint(11, 25), rng.randint(12, 80))
        return _div_dezimal(rng, rng.choice((2, 4, 5)), 50)
    if rng.random() < 0.5:
        return _div_dezimal(rng, rng.choice((2, 4, 5, 8, 20, 25)), ctx.lim(200))
    return _div_rest(rng, rng.randint(11, 19), rng.randint(12, 60))


# --- Brüche ---------------------------------------------------------------------------------------


def _teilerfremd(p, q):
    return q >= 2 and p >= 1 and gcd(p, q) == 1


@generator("bruch_kuerzen", gettext_noop("Brüche kürzen"), thema=BRUECHE, klassenstufe=6)
def bruch_kuerzen(rng, d, ctx):
    q_bereich, k_bereich, unecht = {
        1: ((2, 6), (2, 3), False),
        2: ((3, 9), (2, 6), False),
        3: ((5, 12), (3, 9), False),
        4: ((3, 12), (3, 12), True),
        5: ((7, 20), (4, 12), True),
    }[d]

    def ziehen():
        q = rng.randint(*q_bereich)
        p = rng.randint(1, q * 2 - 1 if unecht else q - 1)
        return p, q

    p, q = waehle(rng, ziehen, lambda x: _teilerfremd(*x) and x[0] != x[1], (1, 2))
    k = rng.randint(*k_bereich)
    return Roh(
        "kuerzen",
        _("Kürze vollständig: %(b)s") % {"b": f"{p * k}/{q * k}"},
        lsg_bruch(Fraction(p, q)),
        {"zaehler": p * k, "nenner": q * k},
    )


@generator("bruch_erweitern", gettext_noop("Brüche erweitern"), thema=BRUECHE, klassenstufe=6)
def bruch_erweitern(rng, d, ctx):
    q_bereich, k_bereich = {
        1: ((2, 5), (2, 4)),
        2: ((2, 8), (2, 6)),
        3: ((3, 10), (3, 9)),
        4: ((3, 12), (4, 10)),
        5: ((3, 12), (5, 12)),
    }[d]
    q = rng.randint(*q_bereich)
    p = waehle(
        rng,
        lambda: rng.randint(1, q * 2 - 1 if d >= 4 else q - 1),
        lambda x: _teilerfremd(x, q),
        1,
    )
    k = rng.randint(*k_bereich)
    return Roh(
        "erweitern",
        _("Erweitere auf den neuen Nenner: %(p)s/%(q)s = ?/%(n)s. Wie lautet der Zähler?")
        % {"p": p, "q": q, "n": q * k},
        lsg_zahl(p * k),
        {"zaehler": p, "nenner": q, "neuer_nenner": q * k},
    )


def _bruch_paar(rng, d):
    """Zwei Brüche als (Zähler, Nenner), unverkürzt wie angezeigt, und die Rechenart für
    ``bruch_addsub``; das Ergebnis ist immer positiv."""
    if d <= 3:
        q = rng.randint(3, 10)
        if d == 1:
            p1 = rng.randint(1, q - 2)
            p2 = rng.randint(1, q - 1 - p1)
            op = "+"
        elif d == 2:
            p1 = rng.randint(2, q - 1)
            p2 = rng.randint(1, p1 - 1)
            op = "-"
        else:
            p1 = rng.randint(q // 2 + 1, q - 1)
            p2 = rng.randint(q - p1 + 1, q - 1)
            op = "+"
        return (p1, q), (p2, q), op, "gleichnamig"
    op = rng.choice("+-")
    if d == 4:
        q1 = rng.randint(2, 6)
        q2 = q1 * rng.randint(2, 3)
        a, b = (rng.randint(1, q1 - 1), q1), (rng.randint(1, q2 - 1), q2)
        if rng.random() < 0.5:
            a, b = b, a
        typ = "einfach_ungleichnamig"
    else:
        q1, q2 = waehle(
            rng,
            lambda: (rng.randint(2, 10), rng.randint(2, 10)),
            lambda x: x[0] != x[1] and kgv(*x) <= 30 and gcd(*x) < min(x),
            (3, 4),
        )
        a, b = (rng.randint(1, q1 - 1), q1), (rng.randint(1, q2 - 1), q2)
        typ = "ungleichnamig"
    if op == "-" and Fraction(*a) <= Fraction(*b):
        a, b = (b, a) if Fraction(*a) < Fraction(*b) else ((a[0] + 1, a[1]), b)
    return a, b, op, typ


@generator(
    "bruch_addsub", gettext_noop("Brüche addieren und subtrahieren"), thema=BRUECHE, klassenstufe=6
)
def bruch_addsub(rng, d, ctx):
    a, b, op, typ = _bruch_paar(rng, d)
    wert = Fraction(*a) + Fraction(*b) if op == "+" else Fraction(*a) - Fraction(*b)
    zeichen = "+" if op == "+" else "−"
    ausdruck = f"{a[0]}/{a[1]} {zeichen} {b[0]}/{b[1]} = ?"
    return Roh(
        f"{'add' if op == '+' else 'sub'}_{typ}",
        _("Rechne und kürze: %(t)s") % {"t": ausdruck},
        lsg_bruch(wert),
        {"a": list(a), "b": list(b), "op": op},
    )


# --- Dezimalzahlen --------------------------------------------------------------------------------

_STELLEN = {
    0: gettext_noop("Ganze"),
    1: gettext_noop("Zehntel"),
    2: gettext_noop("Hundertstel"),
    3: gettext_noop("Tausendstel"),
    -1: gettext_noop("Zehner"),
    -2: gettext_noop("Hunderter"),
    -3: gettext_noop("Tausender"),
}


@generator("dezimal_runden", gettext_noop("Dezimalzahlen runden"), thema=DEZIMAL, klassenstufe=6)
def dezimal_runden(rng, d, ctx):
    if d == 5:
        d = rng.choice((3, 4, 6))
    # (Nachkommastellen der Zahl, Zielstelle, Ganzzahlstellen)
    nk, ziel, ganz = {
        1: (1, 0, 2),
        2: (2, 1, 2),
        3: (3, 2, 2),
        4: (0, rng.choice((-1, -2)), 4),
        6: (4, 3, 1),
    }[d]
    q = waehle(
        rng,
        lambda: Fraction(rng.randint(10 ** (ganz - 1) * 10**nk + 1, 10**ganz * 10**nk - 1), 10**nk),
        lambda x: nk == 0 or (x * 10**nk) % 10 != 0,
        Fraction(37, 10),
    )
    antwort = runden(q, ziel)
    text = zahl_text(q) if nk else str(int(q))
    return Roh(
        "runden",
        _("Runde %(z)s auf %(s)s.") % {"z": text, "s": _(_STELLEN[ziel])},
        lsg_zahl(antwort, stellen=ziel or None) if ziel > 0 else lsg_zahl(antwort),
        {"zahl": str(q), "stelle": ziel},
    )


@generator(
    "dezimal_rechnen", gettext_noop("Mit Dezimalzahlen rechnen"), thema=DEZIMAL, klassenstufe=6
)
def dezimal_rechnen(rng, d, ctx):
    hoch = ctx.lim(500)
    if d <= 3:
        nk = 1 if d == 1 else 2
        skala = 10**nk
        a = Fraction(rng.randint(skala + 1, max(skala + 2, hoch * skala // 10)), skala)
        b = Fraction(rng.randint(1, max(2, hoch * skala // 10 - 1)), skala)
        if d == 3:  # unterschiedlich viele Stellen
            b = Fraction(rng.randint(1, 5000), 10 if rng.random() < 0.5 else 100)
        op = rng.choice("+-")
        if op == "-" and a <= b:
            a, b = b + 1, a
        wert = a + b if op == "+" else a - b
        zeichen = "+" if op == "+" else "−"
        return Roh(
            f"dezimal_{'add' if op == '+' else 'sub'}",
            f"{zahl_text(a)} {zeichen} {zahl_text(b)} = ?",
            lsg_zahl(wert),
            {"a": str(a), "b": str(b), "op": op},
        )
    if d == 4:
        a, n = Fraction(rng.randint(11, 99), 10), rng.randint(2, 9)
        if a.denominator == 1:
            a += Fraction(1, 10)
        return Roh(
            "dezimal_mal_ganz",
            f"{zahl_text(a)} · {n} = ?",
            lsg_zahl(a * n),
            {"a": str(a), "b": n},
        )
    if rng.random() < 0.5:
        a, b = Fraction(rng.randint(2, 19), 10), Fraction(rng.randint(2, 9), 10)
        return Roh(
            "dezimal_mal_dezimal",
            f"{zahl_text(a)} · {zahl_text(b)} = ?",
            lsg_zahl(a * b),
            {"a": str(a), "b": str(b)},
        )
    n = rng.randint(2, 9)
    r = Fraction(rng.randint(11, 400), 100)
    return Roh(
        "dezimal_durch_ganz",
        f"{zahl_text(r * n)} : {n} = ?",
        lsg_zahl(r),
        {"a": str(r * n), "b": n},
    )


# --- Prozent --------------------------------------------------------------------------------------


@generator("prozent_anteil", gettext_noop("Prozent: Anteile"), thema=PROZENT, klassenstufe=6)
def prozent_anteil(rng, d, ctx):
    if d == 1:
        a = rng.randint(1, 99)
        return Roh(
            "anteil_von_100",
            _("Wie viel Prozent sind %(a)s von 100?") % {"a": a},
            lsg_zahl(a, prozent=True),
            {"anteil": a, "grundwert": 100},
        )
    if d == 2:
        p, q = rng.choice(((1, 2), (1, 4), (3, 4), (1, 5), (2, 5), (1, 10), (3, 10), (1, 20)))
        return Roh(
            "bruch_als_prozent",
            _("Schreibe als Prozent: %(b)s") % {"b": f"{p}/{q}"},
            lsg_zahl(Fraction(100 * p, q), prozent=True),
            {"zaehler": p, "nenner": q},
        )
    g = rng.choice(
        {3: (200, 50, 20, 25, 10), 4: (40, 80, 250, 500, 8, 4), 5: tuple(range(12, 300))}[d]
    )
    a = waehle(rng, lambda: rng.randint(1, g - 1), lambda x: (100 * x) % g == 0, None)
    if a is None:
        g, a = 20, rng.randint(1, 19)
    return Roh(
        "anteil_von_grundwert",
        _("Wie viel Prozent sind %(a)s von %(g)s?") % {"a": a, "g": g},
        lsg_zahl(Fraction(100 * a, g), prozent=True),
        {"anteil": a, "grundwert": g},
    )


@generator("prozent_wert", gettext_noop("Prozent: Prozentwert"), thema=PROZENT, klassenstufe=6)
def prozent_wert(rng, d, ctx):
    prozente = {
        1: (50, 10),
        2: (25, 20, 50),
        3: (5, 1, 10, 20, 25, 50),
        4: (15, 30, 40, 60, 75, 80, 5),
        5: (2, 3, 8, 12, 15, 35, 45, 90),
    }[d]
    p = rng.choice(prozente)
    oben = ctx.lim(600)
    g = waehle(
        rng,
        lambda: rng.randint(2, max(3, oben // 10)) * 10,
        lambda x: (p * x) % 100 == 0 and x * p // 100 > 0,
        100,
    )
    return Roh(
        "prozentwert",
        _("Berechne %(p)s %% von %(g)s.") % {"p": p, "g": g},
        lsg_zahl(Fraction(p * g, 100)),
        {"prozent": p, "grundwert": g},
    )


# --- Größen ---------------------------------------------------------------------------------------

_FAKTOR = {
    ("m", "cm"): 100,
    ("cm", "mm"): 10,
    ("km", "m"): 1000,
    ("m", "mm"): 1000,
    ("kg", "g"): 1000,
    ("t", "kg"): 1000,
    ("l", "ml"): 1000,
    ("h", "min"): 60,
}


def _um(rng, gross, klein, stellen_, von_gross):
    """Wert in der einen Einheit und das Ergebnis in der anderen, beide ohne Rundung."""
    f = _FAKTOR[(gross, klein)]
    k = 0
    while 10 ** (k + 1) <= f and k < stellen_:
        k += 1
    if f == 60:
        k = 0
    skala = 10**k
    schritt = rng.randint(1, 99 if stellen_ > 1 else 20)
    r = Fraction(schritt, skala)
    if r.denominator == 1 and stellen_ >= 1 and skala > 1:
        r += Fraction(1, skala)
    if von_gross:
        return r, gross, r * f, klein
    return r * f, klein, r, gross


@generator("groessen_umrechnen", gettext_noop("Größen umrechnen"), thema=GROESSEN, klassenstufe=6)
def groessen_umrechnen(rng, d, ctx):
    paare = [("m", "cm"), ("kg", "g"), ("l", "ml"), ("cm", "mm")]
    if d >= 4:
        paare += [("km", "m"), ("t", "kg"), ("m", "mm")]
    if d == 5:
        paare.append(("h", "min"))
        if rng.random() < 0.5:
            gross, klein = rng.choice([p for p in paare if p[0] in ("kg", "m", "h", "l")])
            a = rng.randint(1, 9)
            b = rng.randint(1, 59) if gross == "h" else 5 * rng.randint(1, 19)
            return Roh(
                "mehrteilig",
                f"{a} {gross} {b} {klein} = ? {klein}",
                lsg_zahl(a * _FAKTOR[(gross, klein)] + b, einheit=klein),
                {"gross": a, "klein": b, "einheiten": [gross, klein]},
            )
    gross, klein = rng.choice(paare)
    von_gross = {1: True, 2: False, 3: True}.get(d, rng.random() < 0.5)
    wert, von, ergebnis, nach = _um(rng, gross, klein, {1: 0, 2: 1, 3: 1}.get(d, 2), von_gross)
    return Roh(
        "umrechnen",
        f"{zahl_text(wert)} {von} = ? {nach}",
        lsg_zahl(ergebnis, einheit=nach),
        {"wert": str(wert), "von": von, "nach": nach},
    )


# --- Rechengesetze, Klammern ----------------------------------------------------------------------


def _punkt_term(rng, art, hoch):
    """Ein Summand mit Punktrechnung: Text und ganzzahliger Wert."""
    if art == "n":
        n = rng.randint(2, hoch)
        return str(n), n
    if art == "mal":
        a, b = rng.randint(2, 9), rng.randint(2, hoch if hoch < 10 else 10)
        return f"{a} · {b}", a * b
    if art == "geteilt":
        b, q = rng.randint(2, 9), rng.randint(2, 9)
        return f"{b * q} : {b}", q
    a, b, c = rng.randint(2, 6), rng.randint(2, 6), rng.randint(2, 4)
    return f"{a} · {b} · {c}", a * b * c


def _summe_aus_termen(rng, arten, hoch):
    """Terme mit + und − verbinden; Zwischenergebnisse bleiben nicht negativ."""

    def ziehen():
        teile = [_punkt_term(rng, a, hoch) for a in arten]
        ops = [rng.choice("+-") for _i in arten[1:]]
        return teile, ops

    def gut(x):
        teile, ops = x
        wert = teile[0][1]
        for (_t, v), op in zip(teile[1:], ops, strict=True):
            wert = wert + v if op == "+" else wert - v
            if wert < 0:
                return False
        return wert > 0

    teile, ops = waehle(rng, ziehen, gut, ([("2", 2), ("3 · 4", 12)], ["+"]))
    text, wert = teile[0][0], teile[0][1]
    for (t, v), op in zip(teile[1:], ops, strict=True):
        text += f" {'+' if op == '+' else '−'} {t}"
        wert = wert + v if op == "+" else wert - v
    return text, wert


@generator("punkt_vor_strich", gettext_noop("Punkt vor Strich"), thema=GESETZE, klassenstufe=6)
def punkt_vor_strich(rng, d, ctx):
    hoch = ctx.lim(20)
    arten = {
        1: ["n", "mal"],
        2: ["mal", "mal"],
        3: ["n", "geteilt", "mal"],
        4: ["n", "mal", "geteilt", "n"],
        5: ["mal", "dreifach", "geteilt", "n"],
    }[d]
    if d in (1, 2):
        arten = rng.sample(arten, 2) if d == 1 else arten
    text, wert = _summe_aus_termen(rng, arten, hoch)
    return Roh(f"punkt_vor_strich_{d}", f"{text} = ?", lsg_zahl(wert), {"term": text})


@generator("klammern", gettext_noop("Klammern und Rechengesetze"), thema=GESETZE, klassenstufe=6)
def klammern(rng, d, ctx):
    a, b, c = rng.randint(2, 15), rng.randint(2, 15), rng.randint(2, 9)
    if d == 1:
        return Roh(
            "klammer_mal", f"({a} + {b}) · {c} = ?", lsg_zahl((a + b) * c), {"a": a, "b": b, "c": c}
        )
    if d == 2:
        a, b = max(a, b) + 1, min(a, b)
        return Roh(
            "mal_klammer",
            f"{c} · ({a} − {b}) = ?",
            lsg_zahl(c * (a - b)),
            {"a": a, "b": b, "c": c},
        )
    if d == 3:
        x = c * (a // c + rng.randint(1, 4)) - a
        return Roh(
            "klammer_geteilt",
            f"({a} + {x}) : {c} = ?",
            lsg_zahl(Fraction(a + x, c)),
            {"a": a, "x": x, "c": c},
        )
    if d == 4:
        if rng.random() < 0.5:
            z = rng.choice((25, 50, 20))
            f = {25: 4, 50: 2, 20: 5}[z]
            m = rng.randint(3, 19)
            reihenfolge = [m, z, f]
            rng.shuffle(reihenfolge)
            text = " · ".join(str(x) for x in reihenfolge)
            return Roh(
                "vorteilhaft_mal",
                _("Rechne vorteilhaft: %(t)s") % {"t": f"{text} = ?"},
                lsg_zahl(m * z * f),
                {"term": text},
            )
        m, x, y = rng.randint(3, 9), rng.randint(11, 29), 0
        y = 10 - x % 10
        text = f"{m} · {x} + {m} · {y}"
        return Roh(
            "vorteilhaft_verteilen",
            _("Rechne vorteilhaft: %(t)s") % {"t": f"{text} = ?"},
            lsg_zahl(m * (x + y)),
            {"term": text},
        )
    a, b, c, e = rng.randint(2, 9), rng.randint(2, 9), rng.randint(6, 15), rng.randint(2, 5)
    c = max(c, e + 1)
    return Roh(
        "klammer_klammer",
        f"({a} + {b}) · ({c} − {e}) = ?",
        lsg_zahl((a + b) * (c - e)),
        {"a": a, "b": b, "c": c, "e": e},
    )
