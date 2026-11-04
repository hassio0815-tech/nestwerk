"""Hilfe-Definitionen Klasse 3: Plus und Minus, Einmaleins, Umkehraufgaben, Teilen, Geld, Längen.

Texte der Stufen 1, 2 und 5 nennen nur Zahlen aus der Aufgabe (keine Zahlwörter, keine Ziffern aus
Vorlagen): so kann der Text die Lösung nicht verraten.
"""

from fractions import Fraction

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from .bau import Hilfe, S, euro, z
from .register import hilfe

_STELLEN = (
    gettext_noop("Einer"),
    gettext_noop("Zehner"),
    gettext_noop("Hunderter"),
    gettext_noop("Tausender"),
    gettext_noop("Zehntausender"),
)


def _stelle(i):
    return _(_STELLEN[min(i, len(_STELLEN) - 1)])


def _add_schritte(a, b):
    """Schriftlich addieren, Stelle für Stelle mit Übertrag."""
    schritte, uebertrag, i = [], 0, 0
    while a or b or uebertrag:
        da, db = a % 10, b % 10
        summe = da + db + uebertrag
        werte = {"st": _stelle(i), "a": da, "b": db, "r": summe, "rz": summe % 10}
        werte["ru"] = summe // 10
        if i == 0:
            vorlage = _("%(st)s: %(a)s + %(b)s = %(r)s. Schreibe %(rz)s, übertrage %(ru)s.")
        else:
            werte["ru0"] = uebertrag
            vorlage = _(
                "%(st)s: %(a)s + %(b)s + %(ru0)s (Übertrag) = %(r)s. Schreibe %(rz)s, "
                "übertrage %(ru)s."
            )
        schritte.append(S(vorlage, **werte))
        uebertrag = summe // 10
        a, b, i = a // 10, b // 10, i + 1
    return schritte


def _sub_schritte(a, b):
    """Schriftlich subtrahieren, Stelle für Stelle mit Entbündeln."""
    schritte, geliehen, i = [], 0, 0
    while a or b:
        da, db = a % 10 - geliehen, b % 10
        geliehen_neu = 1 if da < db else 0
        oben = da + 10 * geliehen_neu
        schritte.append(
            S(
                _("%(st)s: %(ro)s − %(b)s = %(r)s (die obere Ziffer wird bei Bedarf entbündelt)"),
                st=_stelle(i),
                ro=oben,
                b=db,
                r=oben - db,
            )
        )
        geliehen = geliehen_neu
        a, b, i = a // 10, b // 10, i + 1
    return schritte


@hilfe("add_sub_100")
@hilfe("add_sub_1000")
def plus_minus(aufgabe):
    p = aufgabe.parameter
    a, b, plus = p["a"], p["b"], p["op"] == "+"
    if plus:
        gesucht = _("die Summe der beiden Zahlen")
        denk = _(
            "Mit welchen Ziffern fängst du bei der schriftlichen Addition an? Und was machst du, "
            "wenn eine Stelle zweistellig wird?"
        )
        schritte = _add_schritte(a, b)
    else:
        gesucht = _("der Unterschied der beiden Zahlen")
        denk = _(
            "Mit welchen Ziffern fängst du bei der schriftlichen Subtraktion an? Was tust du, "
            "wenn die obere Ziffer kleiner ist als die untere?"
        )
        schritte = _sub_schritte(a, b)
    if aufgabe.typ.endswith("_glatt"):
        denk = _(
            "Rechne mit den vollen Hundertern, als wären es Einer. Denke danach an die Nullen."
        )
    return Hilfe((z(a), z(b)), gesucht, denk, tuple(schritte))


def _ohne_nullen(n):
    k = 0
    while n and n % 10 == 0:
        n, k = n // 10, k + 1
    return n, k


@hilfe("einmaleins")
def einmaleins(aufgabe):
    a, b = aufgabe.parameter["a"], aufgabe.parameter["b"]
    gegeben = (z(a), z(b))
    gesucht = _("das Ergebnis der Mal-Aufgabe")
    if aufgabe.typ == "einmaleins_zehner":
        a0, ka = _ohne_nullen(a)
        b0, kb = _ohne_nullen(b)
        denk = _(
            "Kannst du die Aufgabe erst ohne die Nullen rechnen? Was machst du danach mit den "
            "Nullen?"
        )
        schritte = (
            S(_("Rechne ohne die Nullen: %(a)s · %(b)s = %(r1)s"), a=a0, b=b0, r1=a0 * b0),
            S(
                _("Hänge die Nullen wieder an (%(rk)s Stück): %(r1)s wird zu %(r)s"),
                rk=ka + kb,
                r1=a0 * b0,
                r=a * b,
            ),
        )
    else:
        denk = _(
            "Welche Reihe kennst du hier? Vielleicht hilft dir die Tauschaufgabe, wenn die Zahlen "
            "andersherum stehen."
        )
        schritte = (S(_("Tauschaufgabe: %(b)s · %(a)s = %(r)s"), a=a, b=b, r=a * b),)
    return Hilfe(gegeben, gesucht, denk, schritte)


@hilfe("umkehr")
def umkehr(aufgabe):
    p = aufgabe.parameter
    if "ziel" in p:
        a, ziel = p["a"], p["ziel"]
        return Hilfe(
            (z(a), z(ziel)),
            _("die Zahl, die zur ersten Zahl noch fehlt, damit das Ziel herauskommt"),
            _(
                "Wie weit ist es von der ersten Zahl bis zum Ziel? Du kannst auch in Schritten "
                "ergänzen, zum Beispiel erst bis zum nächsten vollen Zehner."
            ),
            (
                S(_("Gegenaufgabe: %(z)s − %(a)s = %(r)s"), z=ziel, a=a, r=ziel - a),
                S(_("Probe: %(a)s + %(r)s = %(z)s"), z=ziel, a=a, r=ziel - a),
            ),
        )
    f, prod = p["faktor"], p["produkt"]
    return Hilfe(
        (z(f), z(prod)),
        _("die fehlende Zahl in der Mal-Aufgabe"),
        _(
            "Welche Zahl mal %(f)s ergibt das Produkt? Denke an die Reihe von %(f)s oder rechne "
            "mit der Umkehraufgabe."
        )
        % {"f": z(f)},
        (
            S(_("Umkehraufgabe: %(p)s : %(f)s = %(r)s"), p=prod, f=f, r=prod // f),
            S(_("Probe: %(r)s · %(f)s = %(p)s"), p=prod, f=f, r=prod // f),
        ),
    )


@hilfe("division_ohne_rest")
def division(aufgabe):
    d, t = aufgabe.parameter["dividend"], aufgabe.parameter["teiler"]
    return Hilfe(
        (z(d), z(t)),
        _("wie oft die zweite Zahl in die erste passt"),
        _(
            "In welcher Reihe kommt die erste Zahl vor? Frage dich: Die zweite Zahl mal wie viel "
            "ergibt die erste?"
        ),
        (
            S(
                _("Frage dich: %(t)s · ___ = %(d)s. Probiere: %(t)s · %(r)s = %(d)s"),
                t=t,
                d=d,
                r=d // t,
            ),
            S(_("Umkehraufgabe: %(d)s : %(t)s = %(r)s"), d=d, t=t, r=d // t),
        ),
    )


@hilfe("geld")
def geld(aufgabe):
    p, typ = aufgabe.parameter, aufgabe.typ
    if typ == "euro_in_cent":
        e = p["euro"]
        return Hilfe(
            (f"{e} €",),
            _("der Betrag in Cent"),
            _("Wie viele Cent hat ein Euro? Wie oft brauchst du das?"),
            (S(_("Ein Euro sind %(rh)s Cent: %(e)s · %(rh)s = %(r)s ct"), e=e, rh=100, r=e * 100),),
        )
    if typ == "euro_cent_in_cent":
        e, c = p["euro"], p["cent"]
        return Hilfe(
            (f"{e} €", f"{c} ct"),
            _("der ganze Betrag in Cent"),
            _(
                "Verwandle erst die Euro in Cent. Was machst du dann mit den Cent, die schon da "
                "sind?"
            ),
            (
                S(_("Euro in Cent: %(e)s · %(rh)s = %(r1)s ct"), e=e, rh=100, r1=e * 100),
                S(_("Dazu die Cent: %(r1)s + %(c)s = %(r)s ct"), c=c, r1=e * 100, r=e * 100 + c),
            ),
        )
    if typ == "cent_in_euro":
        c = p["cent"]
        return Hilfe(
            (f"{c} ct",),
            _("der Betrag in Euro, mit Komma geschrieben"),
            _(
                "Wie viele ganze Euro stecken in den Cent? Was bleibt übrig? Schreibe es mit "
                "Komma, "
                "mit so vielen Stellen, wie bei Geld üblich."
            ),
            (
                S(
                    _("Ganze Euro: %(c)s : %(rh)s = %(re)s, Rest %(rc)s ct"),
                    c=c,
                    rh=100,
                    re=c // 100,
                    rc=c % 100,
                ),
                S(_("Schreibe mit Komma: %(r)s €"), r=euro(Fraction(c, 100))),
            ),
        )
    if typ == "summe":
        a, b = Fraction(p["a"]), Fraction(p["b"])
        return Hilfe(
            (f"{euro(a)} €", f"{euro(b)} €"),
            _("der Preis für beide Dinge zusammen"),
            _("Schreibe die Beträge so untereinander, dass Komma unter Komma steht, und addiere."),
            (S(_("%(a)s € + %(b)s € = %(r)s €"), a=euro(a), b=euro(b), r=euro(a + b)),),
        )
    if typ == "wechselgeld":
        b, k = p["bezahlt"], Fraction(p["kosten"])
        return Hilfe(
            (f"{b} €", f"{euro(k)} €"),
            _("das Geld, das du zurückbekommst"),
            _(
                "Was gibst du, und was kostet der Einkauf? Rechne den Unterschied, oder zähle vom "
                "Preis aus bis zu dem Betrag hoch, den du gegeben hast."
            ),
            (S(_("%(b)s € − %(k)s € = %(r)s €"), b=b, k=euro(k), r=euro(b - k)),),
        )
    n, preis = p["n"], Fraction(p["preis"])  # mehrere_preise
    return Hilfe(
        (z(n), f"{euro(preis)} €"),
        _("der Preis für alle Hefte zusammen"),
        _("Wie oft musst du den Preis eines Hefts nehmen? Mal oder plus, was passt?"),
        (S(_("%(n)s · %(p)s € = %(r)s €"), n=n, p=euro(preis), r=euro(n * preis)),),
    )


@hilfe("laenge")
def laenge(aufgabe):
    p, typ = aufgabe.parameter, aufgabe.typ
    if typ == "m_in_cm":
        m = p["m"]
        return Hilfe(
            (f"{m} m",),
            _("die Länge in Zentimetern"),
            _("Wie viele Zentimeter hat ein Meter? Wie oft brauchst du das?"),
            (S(_("Ein Meter sind %(rh)s cm: %(m)s · %(rh)s = %(r)s cm"), m=m, rh=100, r=m * 100),),
        )
    if typ == "cm_in_m":
        c = p["cm"]
        return Hilfe(
            (f"{c} cm",),
            _("die Länge in Metern"),
            _("Wie viele Zentimeter hat ein Meter? Wie viele ganze Meter passen in die Länge?"),
            (S(_("Ein Meter sind %(rh)s cm: %(c)s : %(rh)s = %(r)s m"), c=c, rh=100, r=c // 100),),
        )
    if typ == "m_cm_in_cm":
        m, c = p["m"], p["cm"]
        return Hilfe(
            (f"{m} m", f"{c} cm"),
            _("die ganze Länge in Zentimetern"),
            _("Verwandle erst die Meter in Zentimeter. Was machst du dann mit den Zentimetern?"),
            (
                S(_("Meter in Zentimeter: %(m)s · %(rh)s = %(r1)s cm"), m=m, rh=100, r1=m * 100),
                S(
                    _("Dazu die Zentimeter: %(r1)s + %(c)s = %(r)s cm"),
                    c=c,
                    r1=m * 100,
                    r=m * 100 + c,
                ),
            ),
        )
    if typ == "cm_in_mm":
        c = p["cm"]
        return Hilfe(
            (f"{c} cm",),
            _("die Länge in Millimetern"),
            _("Wie viele Millimeter hat ein Zentimeter? Wie oft brauchst du das?"),
            (
                S(
                    _("Ein Zentimeter sind %(rh)s mm: %(c)s · %(rh)s = %(r)s mm"),
                    c=c,
                    rh=10,
                    r=c * 10,
                ),
            ),
        )
    if typ == "mm_in_cm":
        mm = p["mm"]
        return Hilfe(
            (f"{mm} mm",),
            _("die Länge in Zentimetern"),
            _(
                "Wie viele Millimeter hat ein Zentimeter? Wie viele ganze Zentimeter passen in die "
                "Länge?"
            ),
            (
                S(
                    _("Ein Zentimeter sind %(rh)s mm: %(m)s : %(rh)s = %(r)s cm"),
                    m=mm,
                    rh=10,
                    r=mm // 10,
                ),
            ),
        )
    m, c, c2 = p["m"], p["cm"], p["cm2"]  # laengen_addieren
    return Hilfe(
        (f"{m} m", f"{c} cm", f"{c2} cm"),
        _("die ganze Länge in Zentimetern"),
        _("Verwandle erst die Meter in Zentimeter. Dann kannst du alles zusammenzählen."),
        (
            S(_("Meter in Zentimeter: %(m)s · %(rh)s = %(r1)s cm"), m=m, rh=100, r1=m * 100),
            S(
                _("Alles zusammen: %(r1)s + %(c)s + %(c2)s = %(r)s cm"),
                c=c,
                c2=c2,
                r1=m * 100,
                r=m * 100 + c + c2,
            ),
        ),
    )
