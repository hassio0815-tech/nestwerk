"""Generatoren Klasse 3: Plus und Minus bis 100 und 1000, Einmaleins, Größen.

Alles bleibt im Natürlichen: keine negativen Ergebnisse, Division ohne Rest.
"""

from fractions import Fraction

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from .aufgabe import Roh
from .bausteine import (
    entbuendelungen_sub,
    lsg_zahl,
    uebertraege_add,
    waehle,
    zahl_text,
)
from .registry import generator

PLUS_MINUS = "mathe_3_plusminus"
EINMALEINS = "mathe_3_einmaleins"
GROESSEN = "mathe_3_groessen"

_REIHEN = {
    1: (2, 5, 10),
    2: (3, 4),
    3: (6, 7, 8, 9),
    4: (2, 3, 4, 5, 6, 7, 8, 9, 10),
    5: (3, 4, 6, 7, 8, 9, 10),
}


def _rechnung(rng, op, modus, grenze, *, glatt=False, klein=False):
    """Zwei Zahlen ``a op b`` mit oder ohne Übertrag/Entbündelung, Ergebnis im Zahlenraum."""
    schritt = 100 if grenze >= 200 else 10
    unten = 10 if grenze >= 20 else 1

    def ziehen():
        if glatt:
            return (
                schritt * rng.randint(1, max(1, grenze // schritt)),
                schritt * rng.randint(1, max(1, grenze // schritt)),
            )
        a = rng.randint(unten, grenze)
        b = rng.randint(1, min(9, grenze) if klein else grenze)
        return a, b

    def gut(p):
        a, b = p
        if op == "+":
            n = uebertraege_add(a, b)
            return a + b <= grenze and (n == 0 if modus == "ohne" else n >= 1)
        n = entbuendelungen_sub(a, b)
        return a > b and (n == 0 if modus == "ohne" else n >= 1)

    fallback = (2, 3) if op == "+" else (5, 3)
    return waehle(rng, ziehen, gut, fallback)


def _plus_minus(rng, varianten, grenze, bezeichnung):
    op, modus, glatt, klein = rng.choice(varianten)
    a, b = _rechnung(rng, op, modus, grenze, glatt=glatt, klein=klein)
    wert = a + b if op == "+" else a - b
    zeichen = "+" if op == "+" else "−"
    if glatt:
        typ = f"{bezeichnung}_glatt"
    else:
        typ = f"{'add' if op == '+' else 'sub'}_{modus}_{'uebertrag' if op == '+' else 'borgen'}"
    return Roh(
        typ,
        f"{a} {zeichen} {b} = ?",
        lsg_zahl(wert),
        {"a": a, "b": b, "op": op, "grenze": grenze},
    )


@generator(
    "add_sub_100",
    gettext_noop("Plus und Minus bis 100"),
    thema=PLUS_MINUS,
    klassenstufe=3,
)
def add_sub_100(rng, d, ctx):
    tabelle = {
        1: [("+", "ohne", False, True), ("-", "ohne", False, True)],
        2: [("+", "ohne", False, False), ("-", "ohne", False, False)],
        3: [("+", "mit", False, False)],
        4: [("-", "mit", False, False)],
        5: [("+", "mit", False, False), ("-", "mit", False, False)],
    }
    return _plus_minus(rng, tabelle[d], ctx.lim(100), "100")


@generator(
    "add_sub_1000",
    gettext_noop("Plus und Minus bis 1000"),
    thema=PLUS_MINUS,
    klassenstufe=3,
)
def add_sub_1000(rng, d, ctx):
    tabelle = {
        1: [("+", "ohne", True, False), ("-", "ohne", True, False)],
        2: [("+", "ohne", False, False)],
        3: [("-", "ohne", False, False)],
        4: [("+", "mit", False, False)],
        5: [("-", "mit", False, False), ("+", "mit", False, False)],
    }
    return _plus_minus(rng, tabelle[d], ctx.lim(1000), "1000")


@generator("einmaleins", gettext_noop("Kleines Einmaleins"), thema=EINMALEINS, klassenstufe=3)
def einmaleins(rng, d, ctx):
    reihe = rng.choice(_REIHEN[d])
    faktor = rng.randint(1, 10)
    zehner = d == 5 and rng.random() < 0.5
    if zehner:
        faktor *= 10
    a, b = (reihe, faktor) if rng.random() < 0.5 else (faktor, reihe)
    return Roh(
        "einmaleins_zehner" if zehner else "einmaleins",
        f"{a} · {b} = ?",
        lsg_zahl(a * b),
        {"a": a, "b": b},
    )


@generator("umkehr", gettext_noop("Umkehraufgaben"), thema=EINMALEINS, klassenstufe=3)
def umkehr(rng, d, ctx):
    if d >= 4 and rng.random() < 0.5:
        ziel = 1000 if d == 5 else 100
        schritt = 10 if d == 5 else 1
        a = schritt * rng.randint(1, ziel // schritt - 1)
        return Roh(
            f"ergaenzen_{ziel}",
            _("Ergänze: %(a)s + ? = %(z)s") % {"a": a, "z": ziel},
            lsg_zahl(ziel - a),
            {"a": a, "ziel": ziel},
        )
    reihe = rng.choice(_REIHEN[min(d, 4)])
    faktor = rng.randint(1, 10)
    produkt = reihe * faktor
    if rng.random() < 0.5:
        text = f"? · {reihe} = {produkt}"
    else:
        text = f"{reihe} · ? = {produkt}"
    return Roh("fehlender_faktor", text, lsg_zahl(faktor), {"faktor": reihe, "produkt": produkt})


@generator("division_ohne_rest", gettext_noop("Teilen ohne Rest"), thema=EINMALEINS, klassenstufe=3)
def division_ohne_rest(rng, d, ctx):
    if d == 5:
        teiler = rng.choice((2, 3, 4, 5))
        quotient = rng.randint(11, 100 // teiler)
    else:
        teiler = rng.choice(_REIHEN[d])
        quotient = rng.randint(1, 10)
    dividend = teiler * quotient
    return Roh(
        "division",
        f"{dividend} : {teiler} = ?",
        lsg_zahl(quotient),
        {"dividend": dividend, "teiler": teiler},
    )


def _euro(q):
    return zahl_text(q, 2)


@generator("geld", gettext_noop("Euro und Cent"), thema=GROESSEN, klassenstufe=3)
def geld(rng, d, ctx):
    if d == 1:
        e = rng.randint(1, 5)
        return Roh(
            "euro_in_cent",
            _("Wie viele Cent sind %(e)s €?") % {"e": e},
            lsg_zahl(e * 100, einheit="ct"),
            {"euro": e},
        )
    if d == 2:
        e, c = rng.randint(1, 9), 10 * rng.randint(1, 9)
        if rng.random() < 0.5:
            return Roh(
                "euro_cent_in_cent",
                f"{e} € {c} ct = ? ct",
                lsg_zahl(e * 100 + c, einheit="ct"),
                {"euro": e, "cent": c},
            )
        return Roh(
            "cent_in_euro",
            f"{e * 100 + c} ct = ? €",
            lsg_zahl(Fraction(e * 100 + c, 100), einheit="€", stellen=2),
            {"cent": e * 100 + c},
        )
    preise = [Fraction(10 * rng.randint(2, 40), 100) for _i in range(2)]
    if d == 3:
        a, b = preise
        return Roh(
            "summe",
            _("Ein Heft kostet %(a)s €, ein Stift %(b)s €. Wie viel kosten beide zusammen?")
            % {"a": _euro(a), "b": _euro(b)},
            lsg_zahl(a + b, einheit="€", stellen=2),
            {"a": str(a), "b": str(b)},
        )
    if d == 4:
        bezahlt = rng.choice((5, 10, 20))
        kosten = Fraction(10 * rng.randint(5, bezahlt * 10 - 5), 100)
        return Roh(
            "wechselgeld",
            _(
                "Du bezahlst mit %(b)s €. Dein Einkauf kostet %(k)s €. Wie viel Geld bekommst du "
                "zurück?"
            )
            % {"b": bezahlt, "k": _euro(kosten)},
            lsg_zahl(bezahlt - kosten, einheit="€", stellen=2),
            {"bezahlt": bezahlt, "kosten": str(kosten)},
        )
    n = rng.randint(2, 9)
    preis = Fraction(10 * rng.randint(2, 50 // n * 2 or 2), 100)
    return Roh(
        "mehrere_preise",
        _("%(n)s Hefte kosten je %(p)s €. Wie viel kosten sie zusammen?")
        % {"n": n, "p": _euro(preis)},
        lsg_zahl(n * preis, einheit="€", stellen=2),
        {"n": n, "preis": str(preis)},
    )


@generator("laenge", gettext_noop("Meter und Zentimeter"), thema=GROESSEN, klassenstufe=3)
def laenge(rng, d, ctx):
    if d == 1:
        m = rng.randint(1, 9)
        return Roh(
            "m_in_cm",
            _("Wie viele Zentimeter sind %(m)s m?") % {"m": m},
            lsg_zahl(m * 100, einheit="cm"),
            {"m": m},
        )
    if d == 2:
        m = rng.randint(1, 9)
        if rng.random() < 0.5:
            return Roh("cm_in_m", f"{m * 100} cm = ? m", lsg_zahl(m, einheit="m"), {"cm": m * 100})
        return Roh("m_in_cm", f"{m} m = ? cm", lsg_zahl(m * 100, einheit="cm"), {"m": m})
    if d == 3:
        m, c = rng.randint(1, 9), 5 * rng.randint(1, 19)
        return Roh(
            "m_cm_in_cm",
            f"{m} m {c} cm = ? cm",
            lsg_zahl(m * 100 + c, einheit="cm"),
            {"m": m, "cm": c},
        )
    if d == 4:
        if rng.random() < 0.5:
            n = rng.randint(2, 30)
            return Roh("cm_in_mm", f"{n} cm = ? mm", lsg_zahl(n * 10, einheit="mm"), {"cm": n})
        n = 10 * rng.randint(2, 40)
        return Roh("mm_in_cm", f"{n} mm = ? cm", lsg_zahl(n // 10, einheit="cm"), {"mm": n})
    m, c, c2 = rng.randint(1, 5), 5 * rng.randint(1, 19), 5 * rng.randint(1, 19)
    return Roh(
        "laengen_addieren",
        f"{m} m {c} cm + {c2} cm = ? cm",
        lsg_zahl(m * 100 + c + c2, einheit="cm"),
        {"m": m, "cm": c, "cm2": c2},
    )
