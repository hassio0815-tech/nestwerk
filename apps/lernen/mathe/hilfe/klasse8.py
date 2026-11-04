"""Hilfe-Definitionen Klasse 8: Gleichungen, Terme, Prozent, Zinsen, Dreisatz, Potenzen."""

import re
from fractions import Fraction

from django.utils.translation import gettext as _

from .. import term
from . import ausdruck
from .bau import Hilfe, S, euro, z, zk
from .register import hilfe

MINUS = "−"


def _zahl(text):
    return int(text.replace(MINUS, "-"))


# --- Gleichungen ----------------------------------------------------------------------------------


@hilfe("gleichung_linear")
def gleichung_linear(aufgabe):
    text = aufgabe.parameter["gleichung"].replace("-", MINUS)
    typ = aufgabe.typ
    gegeben = tuple(dict.fromkeys(re.findall(r"\d+", text)))
    gesucht = _("der Wert von x, bei dem die Gleichung stimmt")
    num = r"(−?\d+)"
    if typ in ("plus", "minus"):
        a, c = re.fullmatch(rf"x [+−] {num} = {num}", text).groups()
        a, c = int(a), _zahl(c)
        plus = typ == "plus"
        denk = _(
            "Was steht auf der Seite von x zusätzlich? Mit welcher Rechnung wirst du es auf beiden "
            "Seiten los?"
        )
        schritte = (
            S(
                _("Auf beiden Seiten %(op)s %(a)s: x = %(c)s %(op)s %(a)s = %(r)s"),
                op=_("minus") if plus else _("plus"),
                a=a,
                c=c,
                r=c - a if plus else c + a,
            ),
        )
    elif typ == "mal":
        a, c = re.fullmatch(rf"{num}x = {num}", text).groups()
        a, c = int(a), _zahl(c)
        denk = _("Was passiert mit x, wenn eine Zahl davor steht? Wie wirst du diese Zahl los?")
        schritte = (
            S(
                _("Auf beiden Seiten teilen durch %(a)s: x = %(c)s : %(a)s = %(r)s"),
                a=a,
                c=c,
                r=c // a,
            ),
        )
    elif typ in ("mal_plus", "mal_minus"):
        a, vz, b, c = re.fullmatch(rf"{num}x ([+−]) {num} = {num}", text).groups()
        a, b, c = int(a), int(b), _zahl(c)
        plus = vz == "+"
        rechts = c - b if plus else c + b
        denk = _("Welche Zahl steht allein, ohne x? Entferne zuerst sie, dann die Zahl vor x.")
        schritte = (
            S(
                _("Auf beiden Seiten %(op)s %(b)s: %(a)sx = %(c)s %(op)s %(b)s = %(r1)s"),
                op=_("minus") if plus else _("plus"),
                a=a,
                b=b,
                c=c,
                r1=rechts,
            ),
            S(_("Teile durch %(a)s: x = %(r1)s : %(a)s = %(r)s"), a=a, r1=rechts, r=rechts // a),
        )
    elif typ == "klammer":
        a, b, c = re.fullmatch(rf"{num}\(x \+ {num}\) = {num}", text).groups()
        a, b, c = int(a), int(b), _zahl(c)
        denk = _(
            "Du kannst zuerst durch die Zahl vor der Klammer teilen. Was bleibt in der Klammer "
            "übrig?"
        )
        schritte = (
            S(
                _("Teile beide Seiten durch %(a)s: x + %(b)s = %(c)s : %(a)s = %(r1)s"),
                a=a,
                b=b,
                c=c,
                r1=c // a,
            ),
            S(
                _("Auf beiden Seiten minus %(b)s: x = %(r1)s − %(b)s = %(r)s"),
                b=b,
                r1=c // a,
                r=c // a - b,
            ),
        )
    elif typ == "klammer_plus":
        a, b, e, c = re.fullmatch(rf"{num}\(x − {num}\) \+ {num} = {num}", text).groups()
        a, b, e, c = int(a), int(b), int(e), _zahl(c)
        r1 = c - e
        denk = _(
            "Welche Zahl steht außerhalb der Klammer allein? Entferne sie zuerst. Dann teilst du "
            "und löst die Klammer."
        )
        schritte = (
            S(
                _("Auf beiden Seiten minus %(e)s: %(a)s(x − %(b)s) = %(c)s − %(e)s = %(r1)s"),
                a=a,
                b=b,
                c=c,
                e=e,
                r1=r1,
            ),
            S(
                _("Teile durch %(a)s: x − %(b)s = %(r1)s : %(a)s = %(r2)s"),
                a=a,
                b=b,
                r1=r1,
                r2=r1 // a,
            ),
            S(
                _("Auf beiden Seiten plus %(b)s: x = %(r2)s + %(b)s = %(r)s"),
                b=b,
                r2=r1 // a,
                r=r1 // a + b,
            ),
        )
    else:  # x_beidseitig
        links, rechts = text.split(" = ")
        pl, pr = term.lesen(links), term.lesen(rechts)
        x, k = (("x", 1),), ()
        al, bl = pl.get((x[0],), 0), pl.get(k, 0)
        ar, br = pr.get((x[0],), 0), pr.get(k, 0)
        d, e = al - ar, br - bl
        denk = _(
            "Sammle alle x auf einer Seite und alle Zahlen auf der anderen. Teile dann durch die "
            "Zahl vor x."
        )
        schritte = (
            S(_("Alle x nach links: %(a)sx − %(c)sx = %(rd)sx"), a=al, c=zk(ar), rd=d),
            S(_("Alle Zahlen nach rechts: %(b)s − %(c)s = %(re)s"), b=zk(br), c=zk(bl), re=e),
            S(
                _("Teile durch %(rd)s: x = %(re)s : %(rd)s = %(r)s"),
                rd=d,
                re=e,
                r=z(Fraction(e, d)),
            ),
        )
        gegeben = tuple(dict.fromkeys(re.findall(r"\d+", text)))
    return Hilfe(gegeben, gesucht, denk, schritte)


# --- Terme ----------------------------------------------------------------------------------------


def _summanden(text):
    """``3x − 5`` -> ``[(3, "x"), (-5, "")]`` (Text wie vom Generator: Leerzeichen um + und −)."""
    teile = re.findall(r"([+−]?)\s*(\d*)([a-z]²?)?", text.replace(" ", ""))
    ergebnis = []
    for vz, zahl, m in teile:
        if not zahl and not m:
            continue
        c = int(zahl) if zahl else 1
        ergebnis.append((-c if vz == MINUS else c, m or ""))
    return ergebnis


def _summe_text(zeilen):
    text = ""
    for c, m in zeilen:
        teil = (str(abs(c)) if (abs(c) != 1 or not m) else "") + m
        text += (f" {MINUS if c < 0 else '+'} " if text else (MINUS if c < 0 else "")) + teil
    return text


@hilfe("term_zusammenfassen")
def term_zusammenfassen(aufgabe):
    text = aufgabe.parameter["term"]
    gruppen = {}
    for c, m in _summanden(text):
        gruppen.setdefault(m, []).append(c)
    schritte = []
    for m, koeffs in gruppen.items():
        name = f"{m}" if m else _("die Zahlen")
        gleich = _summe_text([(c, m) for c in koeffs])
        schritte.append(
            S(
                _("Gleichartige Terme (%(m)s): %(t)s = %(r)s"),
                m=name,
                t=gleich,
                r=_summe_text([(sum(koeffs), m)]) if sum(koeffs) else "0",
            )
        )
    return Hilfe(
        (text,),
        _("der Term, so kurz wie möglich"),
        _(
            "Welche Terme haben denselben Buchstaben? Nur gleichartige Terme darfst du "
            "zusammenfassen. Achte auf die Vorzeichen."
        ),
        tuple(schritte),
    )


def _produkte(text):
    """Teilt eine Summe von Produkten am Plus außerhalb der Klammern."""
    produkte, tiefe, start = [], 0, 0
    for i, c in enumerate(text):
        if c == "(":
            tiefe += 1
        elif c == ")":
            tiefe -= 1
        elif c == "+" and tiefe == 0:
            produkte.append(text[start:i].strip())
            start = i + 1
    produkte.append(text[start:].strip())
    return produkte


def _faktoren(produkt):
    """``8(x + 7)`` -> ``["8", "(x + 7)"]``; ``(x + 2)(x + 3)`` -> zwei Klammern."""
    faktoren = []
    vorne = produkt.split("(")[0].strip()
    if vorne:
        faktoren.append(vorne)
    return faktoren + re.findall(r"\([^)]*\)", produkt)


def _poly(text):
    return term.format_term(term.lesen(text.replace(MINUS, "-")))


def _teile(faktor):
    if faktor.startswith("("):
        return _summanden(faktor[1:-1])
    return [(_zahl(faktor), "")]


def _klammert(text):
    return f"({text})" if text.startswith(MINUS) else text


@hilfe("term_ausmultiplizieren")
def term_ausmultiplizieren(aufgabe):
    text = aufgabe.parameter["term"]
    schritte = []
    for produkt in _produkte(text):
        faktoren = _faktoren(produkt)
        if len(faktoren) < 2:
            continue
        for c1, m1 in _teile(faktoren[0]):
            for c2, m2 in _teile(faktoren[1]):
                a, b = _summe_text([(c1, m1)]), _summe_text([(c2, m2)])
                prod = _poly(f"({a})*({b})")
                schritte.append(
                    S(
                        _("Multipliziere: %(a)s · %(b)s = %(r)s"),
                        a=_klammert(a),
                        b=_klammert(b),
                        r=prod,
                    )
                )
    schritte.append(S(_("Fasse gleichartige Terme zusammen: %(r)s"), r=_poly(text)))
    return Hilfe(
        (text,),
        _("der ausmultiplizierte, zusammengefasste Term"),
        _(
            "Jeder Summand der ersten Klammer wird mit jedem Summanden der zweiten Klammer "
            "malgenommen. Achte auf die Vorzeichen."
        ),
        tuple(schritte),
    )


# --- Prozent und Zinsen ---------------------------------------------------------------------------


def _prozent_schritte(g, p, einheit=""):
    """Ein Prozent bestimmen, dann mit der Prozentzahl malnehmen."""
    g, p = Fraction(g), Fraction(p)
    e = f" {einheit}" if einheit else ""
    return (
        S(_("Ein Prozent: %(g)s : %(rh)s = %(r1)s"), g=z(g), rh=100, r1=z(g / 100)),
        S(
            _("%(p)s Prozent: %(r1)s · %(p)s = %(r)s%(e)s"),
            p=z(p),
            r1=z(g / 100),
            r=z(g * p / 100),
            e=e,
        ),
    )


@hilfe("prozent_rechnen")
def prozent_rechnen(aufgabe):
    pr, typ = aufgabe.parameter, aufgabe.typ
    if typ == "prozentwert":
        g, p = pr["grundwert"], pr["prozent"]
        return Hilfe(
            (z(g), f"{p} %"),
            _("der Prozentwert"),
            _("Wie viel ist ein Prozent vom Grundwert? Wie oft brauchst du dieses eine Prozent?"),
            _prozent_schritte(g, p),
        )
    if typ == "prozentsatz":
        g, p = pr["grundwert"], pr["prozent"]
        w = Fraction(p * g, 100)
        return Hilfe(
            (z(w), z(g)),
            _("der Prozentsatz"),
            _(
                "Welcher Teil vom Grundwert ist der Prozentwert? Wie rechnest du diesen Bruch in "
                "Prozent um?"
            ),
            (
                S(
                    _("Teile den Prozentwert durch den Grundwert: %(w)s : %(g)s = %(r1)s"),
                    w=z(w),
                    g=z(g),
                    r1=z(w / g),
                ),
                S(
                    _("In Prozent umrechnen: %(r1)s · %(rh)s = %(r)s %%"),
                    r1=z(w / g),
                    rh=100,
                    r=z(Fraction(p)),
                ),
            ),
        )
    if typ == "grundwert":
        g, p = pr["grundwert"], pr["prozent"]
        w = Fraction(p * g, 100)
        return Hilfe(
            (z(w), f"{p} %"),
            _("der Grundwert"),
            _("Wie viel sind ein Prozent? Wie viele Prozent braucht der ganze Grundwert?"),
            (
                S(_("Ein Prozent: %(w)s : %(p)s = %(r1)s"), w=z(w), p=p, r1=z(w / p)),
                S(
                    _("Das Ganze, der Grundwert: %(r1)s · %(rh)s = %(r)s"),
                    r1=z(w / p),
                    rh=100,
                    r=z(g),
                ),
            ),
        )
    if typ == "rabatt":
        g, p = pr["grundwert"], pr["prozent"]
        nachlass = Fraction(g * p, 100)
        return Hilfe(
            (f"{g} €", f"{p} %"),
            _("der neue Preis nach dem Rabatt"),
            _(
                "Wie viel Euro sind der Rabatt? Wird der Preis durch den Rabatt größer oder "
                "kleiner?"
            ),
            (
                S(_("Rabatt: %(p)s %% von %(g)s € = %(r1)s €"), p=p, g=g, r1=euro(nachlass)),
                S(
                    _("Neuer Preis: %(g)s € − %(r1)s € = %(r)s €"),
                    g=g,
                    r1=euro(nachlass),
                    r=euro(g - nachlass),
                ),
            ),
        )
    if typ == "mehrwertsteuer":
        n, p = pr["netto"], pr["prozent"]
        steuer = Fraction(n * p, 100)
        return Hilfe(
            (f"{n} €", f"{p} %"),
            _("der Bruttopreis"),
            _(
                "Wie viel Euro sind die Steuer? Wird der Preis durch die Steuer größer oder "
                "kleiner?"
            ),
            (
                S(_("Steuer: %(p)s %% von %(n)s € = %(r1)s €"), p=p, n=n, r1=euro(steuer)),
                S(
                    _("Bruttopreis: %(n)s € + %(r1)s € = %(r)s €"),
                    n=n,
                    r1=euro(steuer),
                    r=euro(n + steuer),
                ),
            ),
        )
    alt, p = pr["alt"], pr["prozent"]  # aenderung_prozent
    plus = Fraction(alt * p, 100)
    neu = alt + plus
    return Hilfe(
        (f"{alt} €", f"{z(neu)} €"),
        _("die Änderung in Prozent"),
        _("Um wie viel Euro hat sich der Preis geändert? Welcher Teil vom alten Preis ist das?"),
        (
            S(_("Unterschied: %(b)s € − %(a)s € = %(r1)s €"), a=alt, b=z(neu), r1=z(plus)),
            S(
                _("Teile durch den alten Preis: %(r1)s : %(a)s = %(r2)s"),
                a=alt,
                r1=z(plus),
                r2=z(plus / alt),
            ),
            S(
                _("In Prozent umrechnen: %(r2)s · %(rh)s = %(r)s %%"),
                r2=z(plus / alt),
                rh=100,
                r=z(Fraction(p)),
            ),
        ),
    )


@hilfe("zinsen")
def zinsen(aufgabe):
    pr, typ = aufgabe.parameter, aufgabe.typ
    k = pr["kapital"]
    if typ in ("jahreszinsen", "jahreszinsen_dezimal"):
        p = Fraction(pr["prozent"])
        return Hilfe(
            (f"{k} €", f"{z(p)} %"),
            _("die Zinsen für ein Jahr"),
            _("Die Zinsen sind ein Prozentwert. Was ist der Grundwert, was die Prozentzahl?"),
            _prozent_schritte(k, p, "€"),
        )
    p = Fraction(pr["prozent"])
    if typ == "zinssatz":
        zins = k * p / 100
        return Hilfe(
            (f"{k} €", f"{z(zins)} €"),
            _("der Zinssatz"),
            _(
                "Welcher Teil vom Kapital sind die Zinsen? Wie rechnest du diesen Teil in Prozent "
                "um?"
            ),
            (
                S(
                    _("Teile die Zinsen durch das Kapital: %(z)s : %(k)s = %(r1)s"),
                    z=z(zins),
                    k=k,
                    r1=z(zins / k),
                ),
                S(
                    _("In Prozent umrechnen: %(r1)s · %(rh)s = %(r)s %%"),
                    r1=z(zins / k),
                    rh=100,
                    r=z(p),
                ),
            ),
        )
    if typ == "kapital":
        zins = k * p / 100
        return Hilfe(
            (f"{z(p)} %", f"{z(zins)} €"),
            _("das Kapital"),
            _(
                "Die Zinsen sind ein Prozentwert, das Kapital ist der Grundwert. Wie viel sind ein "
                "Prozent?"
            ),
            (
                S(_("Ein Prozent: %(z)s : %(p)s = %(r1)s"), z=z(zins), p=z(p), r1=z(zins / p)),
                S(
                    _("Das Ganze, der Grundwert: %(r1)s · %(rh)s = %(r)s"),
                    r1=z(zins / p),
                    rh=100,
                    r=z(Fraction(k)),
                ),
            ),
        )
    if typ == "monatszinsen":
        m = pr["monate"]
        jahr = Fraction(k * p, 100)
        return Hilfe(
            (f"{k} €", f"{m} Monate", f"{z(p)} %"),
            _("die Zinsen für die Monate"),
            _(
                "Rechne zuerst die Zinsen für ein ganzes Jahr. Welcher Teil vom Jahr sind die "
                "Monate?"
            ),
            (
                S(
                    _("Zinsen für ein Jahr: %(k)s € · %(p)s %% = %(r1)s €"),
                    k=k,
                    p=z(p),
                    r1=euro(jahr),
                ),
                S(_("Teil vom Jahr: %(m)s : %(rj)s = %(r2)s"), m=m, rj=12, r2=z(Fraction(m, 12))),
                S(
                    _("Zinsen: %(r1)s € · %(r2)s = %(r)s €"),
                    r1=euro(jahr),
                    r2=z(Fraction(m, 12)),
                    r=euro(jahr * m / 12),
                ),
            ),
        )
    j1 = Fraction(k * p, 100)  # zinseszins, zwei Jahre
    k1 = k + j1
    j2 = k1 * p / 100
    return Hilfe(
        (f"{k} €", f"{z(p)} %"),
        _("das Guthaben am Ende"),
        _("Rechne Jahr für Jahr. Mit welchem Betrag beginnt das zweite Jahr?"),
        (
            S(_("Erstes Jahr, Zinsen: %(k)s € · %(p)s %% = %(r1)s €"), k=k, p=z(p), r1=euro(j1)),
            S(
                _("Guthaben nach dem ersten Jahr: %(k)s € + %(r1)s € = %(r2)s €"),
                k=k,
                r1=euro(j1),
                r2=euro(k1),
            ),
            S(
                _("Zweites Jahr, Zinsen: %(r2)s € · %(p)s %% = %(r3)s €"),
                r2=euro(k1),
                p=z(p),
                r3=euro(j2),
            ),
            S(
                _("Guthaben nach dem zweiten Jahr: %(r2)s € + %(r3)s € = %(r)s €"),
                r2=euro(k1),
                r3=euro(j2),
                r=euro(k1 + j2),
            ),
        ),
    )


# --- Dreisatz -------------------------------------------------------------------------------------

_EINHEITEN = ("€", "€", "l")


@hilfe("dreisatz_proportional")
def dreisatz_proportional(aufgabe):
    pr = aufgabe.parameter
    n1, n2, einheitswert, k = pr["n1"], pr["n2"], Fraction(pr["einheitswert"]), pr["szenario"]
    gesamt = n1 * einheitswert
    e = _EINHEITEN[k]
    fmt = (lambda q: euro(q)) if k < 2 else z
    return Hilfe(
        (z(n1), f"{fmt(gesamt)} {e}", z(n2)),
        _("der Wert für die neue Menge"),
        _("Wie viel ist es für nur eine Einheit? Wie oft brauchst du diesen Wert danach?"),
        (
            S(
                _("Auf eine Einheit: %(t)s : %(n1)s = %(r1)s"),
                t=fmt(gesamt),
                n1=n1,
                r1=z(einheitswert) if k == 2 else euro(einheitswert),
            ),
            S(
                _("Auf die neue Menge: %(r1)s · %(n2)s = %(r)s %(e)s"),
                r1=z(einheitswert) if k == 2 else euro(einheitswert),
                n2=n2,
                r=fmt(n2 * einheitswert),
                e=e,
            ),
        ),
    )


@hilfe("dreisatz_antiproportional")
def dreisatz_antiproportional(aufgabe):
    pr = aufgabe.parameter
    n1, n2, t1, gesamt = pr["n1"], pr["n2"], pr["t1"], pr["gesamt"]
    return Hilfe(
        (z(n1), z(t1), z(n2)),
        _("die Zeit für die neue Anzahl"),
        _(
            "Mehr oder weniger: Wird es mit der neuen Anzahl schneller oder langsamer? Rechne mit "
            "dem Gesamtaufwand."
        ),
        (
            S(_("Gesamtaufwand: %(n1)s · %(t1)s = %(r1)s"), n1=n1, t1=t1, r1=gesamt),
            S(_("Für die neue Anzahl: %(r1)s : %(n2)s = %(r)s"), n2=n2, r1=gesamt, r=gesamt // n2),
        ),
    )


# --- Potenzen, Wurzeln, Negatives -----------------------------------------------------------------


def _zahlen_text(text):
    return tuple(dict.fromkeys(re.findall(r"\d+", text)))


@hilfe("potenzen")
def potenzen(aufgabe):
    text = aufgabe.text
    if aufgabe.typ in ("quadrat", "potenz", "negative_basis"):
        denk = _(
            "Wie oft steht die Basis als Faktor da? Schreibe die Mal-Aufgabe aus. Achte auf das "
            "Vorzeichen."
        )
    else:
        denk = _("Rechne zuerst die Potenzen aus. Plus und Minus kommen danach.")
    return Hilfe(
        _zahlen_text(text),
        _("der Wert der Potenz-Aufgabe"),
        denk,
        tuple(ausdruck.schritte_fuer(text)),
    )


@hilfe("wurzeln")
def wurzeln(aufgabe):
    pr, typ = aufgabe.parameter, aufgabe.typ
    gesucht = _("der Wert der Wurzel-Aufgabe")
    if typ in ("wurzel", "quadrat_umkehren"):
        rad = pr.get("radikand", pr.get("quadrat"))
        w = int(round(rad**0.5))
        return Hilfe(
            (z(rad),),
            gesucht if typ == "wurzel" else _("die positive Zahl mit diesem Quadrat"),
            _(
                "Welche Zahl mit sich selbst malgenommen ergibt die Zahl? Probiere nahe "
                "Quadratzahlen aus."
            ),
            (
                S(
                    _("Probiere: %(r1)s · %(r1)s = %(a)s, also ist die Wurzel %(r)s"),
                    a=rad,
                    r1=w,
                    r=w,
                ),
            ),
        )
    if typ == "wurzel_dezimal":
        q = Fraction(pr["radikand"])
        w = Fraction(int(round((q * 100) ** 0.5)), 10)
        return Hilfe(
            (z(q),),
            gesucht,
            _(
                "Schreibe die Zahl als Bruch mit dem Nenner, der zu den Hundertsteln passt. Aus "
                "welchen Zahlen kannst du dann die Wurzel ziehen?"
            ),
            (
                S(_("Als Bruch: %(q)s = %(r1)s/%(rh)s"), q=z(q), r1=int(q * 100), rh=100),
                S(
                    _("Wurzel aus dem Zähler und aus dem Nenner: %(r2)s/%(r3)s = %(r)s"),
                    r2=int(round(int(q * 100) ** 0.5)),
                    r3=10,
                    r=z(w),
                ),
            ),
        )
    if typ == "wurzel_summe":
        a, b = pr["a"], pr["b"]
        minus = "−" in aufgabe.text
        wa, wb = int(round(a**0.5)), int(round(b**0.5))
        return Hilfe(
            (z(a), z(b)),
            gesucht,
            _("Ziehe zuerst jede Wurzel einzeln. Rechne danach Plus oder Minus."),
            (
                S(_("Einzeln: √%(a)s = %(r1)s und √%(b)s = %(r2)s"), a=a, b=b, r1=wa, r2=wb),
                S(
                    _("Dann: %(r1)s %(op)s %(r2)s = %(r)s"),
                    r1=wa,
                    r2=wb,
                    op="−" if minus else "+",
                    r=wa - wb if minus else wa + wb,
                ),
            ),
        )
    a, b = pr["a"], pr["b"]  # wurzel_pythagoras
    return Hilfe(
        (z(a), z(b)),
        gesucht,
        _(
            "Rechne zuerst unter der Wurzel. Welche Zahl mit sich selbst malgenommen ergibt dann "
            "das Ergebnis?"
        ),
        (
            S(_("Unter der Wurzel: %(a)s + %(b)s = %(r1)s"), a=a, b=b, r1=a + b),
            S(_("Wurzel ziehen: √%(r1)s = %(r)s"), r1=a + b, r=int(round((a + b) ** 0.5))),
        ),
    )


@hilfe("negative_zahlen")
def negative_zahlen(aufgabe):
    text = aufgabe.parameter["term"]
    typ = aufgabe.typ
    if typ in ("neg_plus_pos", "pos_minus_gross"):
        denk = _(
            "Liegt das Ergebnis über oder unter dem Nullpunkt? Frage dich: Welche Zahl ist weiter "
            "von null entfernt?"
        )
    elif typ in ("malnehmen", "teilen", "produkt_plus", "produkt_minus"):
        denk = _(
            "Welches Vorzeichen hat das Ergebnis, wenn du Zahlen mit Vorzeichen malnimmst oder "
            "teilst? Rechne erst den Betrag."
        )
    elif typ == "punkt_vor_strich":
        denk = _("Was musst du zuerst rechnen? Beachte Punkt vor Strich und die Vorzeichen.")
    else:
        denk = _(
            "Was bedeutet es, wenn Vorzeichen direkt hintereinander stehen? Schreibe die Aufgabe "
            "ohne Klammern auf."
        )
    return Hilfe(
        _zahlen_text(text),
        _("das Ergebnis mit dem richtigen Vorzeichen"),
        denk,
        tuple(ausdruck.schritte_fuer(text)),
    )
