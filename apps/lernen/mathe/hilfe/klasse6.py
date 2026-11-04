"""Hilfe-Definitionen Klasse 6: schriftlich Rechnen, Brüche, Dezimalzahlen, Prozent, Größen."""

import re
from fractions import Fraction
from math import gcd

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from ..bausteine import bruch_text, kgv
from ..generatoren_klasse6 import _FAKTOR, _STELLEN
from . import ausdruck
from .bau import Hilfe, S, z
from .register import hilfe

_PLAETZE = (
    gettext_noop("Einer"),
    gettext_noop("Zehner"),
    gettext_noop("Hunderter"),
    gettext_noop("Tausender"),
)


@hilfe("mult_schriftlich")
def mult_schriftlich(aufgabe):
    a, b = aufgabe.parameter["a"], aufgabe.parameter["b"]
    zeilen, rs = [], []
    for i, ziffer in enumerate(reversed(str(b))):
        teil = a * int(ziffer) * 10**i
        rs.append(teil)
        zeilen.append(
            S(
                _("%(st)s-Ziffer von %(b)s: %(a)s · %(d)s = %(r)s"),
                st=_(_PLAETZE[min(i, 3)]),
                b=b,
                a=a,
                d=int(ziffer) * 10**i,
                r=teil,
            )
        )
    if len(rs) > 1:
        namen = {f"r{i + 1}": t for i, t in enumerate(rs)}
        vorlage = " + ".join(f"%({k})s" for k in namen)
        zeilen.append(
            S(
                _("Addiere die Teilergebnisse: %(rechnung)s") % {"rechnung": vorlage + " = %(r)s"},
                r=a * b,
                **namen,
            )
        )
    return Hilfe(
        (z(a), z(b)),
        _("das Produkt der beiden Zahlen"),
        _(
            "Mit welcher Ziffer der zweiten Zahl fängst du an? Was machst du mit den "
            "Teilergebnissen "
            "am Schluss?"
        ),
        tuple(zeilen),
    )


@hilfe("div_schriftlich")
def div_schriftlich(aufgabe):
    d, t = aufgabe.parameter["dividend"], aufgabe.parameter["teiler"]
    ziffern = [int(c) for c in str(d)]
    zeilen, rest, begonnen = [], 0, False
    for i, ziffer in enumerate(ziffern):
        aktuell = rest * 10 + ziffer
        q = aktuell // t
        rest = aktuell % t
        if not begonnen and q == 0 and i < len(ziffern) - 1:
            rest = aktuell
            continue
        vorlage = (
            _("Nimm %(rc)s: %(rc)s : %(t)s = %(rq)s, Rest %(rr)s")
            if not begonnen
            else _("Hole die nächste Ziffer herunter: %(rc)s : %(t)s = %(rq)s, Rest %(rr)s")
        )
        begonnen = True
        zeilen.append(S(vorlage, rc=aktuell, t=t, rq=q, rr=rest))
    if aufgabe.typ == "div_dezimal":
        n = 0
        while rest and n < 8:
            aktuell, n = rest * 10, n + 1
            zeilen.append(
                S(
                    _("Nach dem Komma, hänge eine Stelle an: %(rc)s : %(t)s = %(rq)s, Rest %(rr)s"),
                    rc=aktuell,
                    t=t,
                    rq=aktuell // t,
                    rr=aktuell % t,
                )
            )
            rest = aktuell % t
        denk = _(
            "Teile Stelle für Stelle. Was machst du, wenn ein Rest bleibt, aber keine Ziffer mehr "
            "übrig ist? Denke an das Komma."
        )
        gesucht = _("das Ergebnis als Dezimalzahl")
    elif aufgabe.typ == "div_mit_rest":
        denk = _("Teile Stelle für Stelle. Was bleibt am Ende übrig? Das ist der Rest.")
        gesucht = _("das Ergebnis mit Rest")
    else:
        denk = _(
            "Teile Stelle für Stelle von links. Hole die nächste Ziffer herunter, wenn ein Rest "
            "bleibt."
        )
        gesucht = _("das Ergebnis der Division")
    return Hilfe((z(d), z(t)), gesucht, denk, tuple(zeilen))


@hilfe("bruch_kuerzen")
def bruch_kuerzen(aufgabe):
    zl, n = aufgabe.parameter["zaehler"], aufgabe.parameter["nenner"]
    g = gcd(zl, n)
    return Hilfe(
        (f"{zl}/{n}",),
        _("der Bruch in einfachster Form"),
        _(
            "Durch welche Zahl kannst du Zähler und Nenner teilen? Geht es noch einmal weiter, "
            "bis nichts mehr passt?"
        ),
        (
            S(_("Eine Zahl, durch die Zähler und Nenner teilbar sind: %(rg)s"), rg=g),
            S(_("Zähler: %(z)s : %(rg)s = %(r1)s"), z=zl, rg=g, r1=zl // g),
            S(_("Nenner: %(n)s : %(rg)s = %(r2)s"), n=n, rg=g, r2=n // g),
        ),
    )


@hilfe("bruch_erweitern")
def bruch_erweitern(aufgabe):
    p, q, n = (aufgabe.parameter[k] for k in ("zaehler", "nenner", "neuer_nenner"))
    k = n // q
    return Hilfe(
        (f"{p}/{q}", z(n)),
        _("der neue Zähler"),
        _(
            "Mit welcher Zahl wurde der alte Nenner malgenommen, um den neuen zu bekommen? Das "
            "musst du mit dem Zähler auch tun."
        ),
        (
            S(_("Erweiterungszahl: %(n)s : %(q)s = %(rk)s"), n=n, q=q, rk=k),
            S(_("Zähler: %(p)s · %(rk)s = %(r)s"), p=p, rk=k, r=p * k),
        ),
    )


@hilfe("bruch_addsub")
def bruch_addsub(aufgabe):
    (p1, q1), (p2, q2) = aufgabe.parameter["a"], aufgabe.parameter["b"]
    plus = aufgabe.parameter["op"] == "+"
    op = "+" if plus else "−"
    summe = p1 + p2 if plus else p1 - p2
    wert = Fraction(p1, q1) + Fraction(p2, q2) if plus else Fraction(p1, q1) - Fraction(p2, q2)
    gegeben = (f"{p1}/{q1}", f"{p2}/{q2}")
    gesucht = _("der Bruch in einfachster Form")
    if q1 == q2:
        denk = _(
            "Was passiert bei gleichem Nenner mit dem Nenner und was mit den Zählern? Lässt sich "
            "das Ergebnis kürzen?"
        )
        schritte = (
            S(
                _("Der Nenner %(q)s bleibt. Zähler: %(p1)s %(op)s %(p2)s = %(r1)s"),
                q=q1,
                p1=p1,
                p2=p2,
                op=op,
                r1=summe,
            ),
            S(
                _("Kürze, wenn es geht: %(r1)s/%(q)s wird zu %(r)s"),
                q=q1,
                r1=summe,
                r=bruch_text(wert),
            ),
        )
    else:
        n = kgv(q1, q2)
        a1, a2 = p1 * (n // q1), p2 * (n // q2)
        denk = _(
            "Wie heißt der gemeinsame Nenner von %(q1)s und %(q2)s? Auf welchen Nenner musst du "
            "beide Brüche bringen?"
        ) % {"q1": q1, "q2": q2}
        schritte = (
            S(_("Gemeinsamer Nenner von %(q1)s und %(q2)s: %(rn)s"), q1=q1, q2=q2, rn=n),
            S(
                _("Erweitere: %(p1)s/%(q1)s = %(ra1)s/%(rn)s und %(p2)s/%(q2)s = %(ra2)s/%(rn)s"),
                p1=p1,
                q1=q1,
                p2=p2,
                q2=q2,
                ra1=a1,
                ra2=a2,
                rn=n,
            ),
            S(
                _("Zähler: %(ra1)s %(op)s %(ra2)s = %(rs)s"),
                ra1=a1,
                ra2=a2,
                op=op,
                rs=a1 + a2 if plus else a1 - a2,
            ),
            S(
                _("Kürze, wenn es geht: %(rs)s/%(rn)s wird zu %(r)s"),
                rs=a1 + a2 if plus else a1 - a2,
                rn=n,
                r=bruch_text(wert),
            ),
        )
    return Hilfe(gegeben, gesucht, denk, schritte)


@hilfe("dezimal_runden")
def dezimal_runden(aufgabe):
    q, stelle = Fraction(aufgabe.parameter["zahl"]), aufgabe.parameter["stelle"]
    name = _(_STELLEN[stelle])
    ziffer = int(abs(q) * Fraction(10) ** stelle * 10) % 10
    return Hilfe(
        (z(q),),
        _("die gerundete Zahl"),
        _(
            "Welche Stelle ist die Zielstelle? Welche Ziffer steht gleich rechts davon? Wird "
            "aufgerundet oder abgerundet?"
        ),
        (
            S(_("Die Zielstelle ist: %(s)s."), s=name),
            S(
                _("Die Ziffer rechts davon ist %(rz)s. Also wird %(ra)s."),
                rz=ziffer,
                ra=_("aufgerundet") if ziffer >= 5 else _("abgerundet"),
            ),
        ),
    )


def _stellen_hinter_komma(q):
    k = 0
    while (Fraction(q) * 10**k).denominator != 1:
        k += 1
    return k


@hilfe("dezimal_rechnen")
def dezimal_rechnen(aufgabe):
    p, typ = aufgabe.parameter, aufgabe.typ
    a = Fraction(p["a"])
    if typ in ("dezimal_add", "dezimal_sub"):
        b = Fraction(p["b"])
        plus = typ == "dezimal_add"
        st = max(_stellen_hinter_komma(a), _stellen_hinter_komma(b))
        return Hilfe(
            (z(a), z(b)),
            _("das Ergebnis der Rechnung mit Komma"),
            _(
                "Wie schreibst du die Zahlen untereinander? Wohin kommen die Kommas, und womit "
                "füllst "
                "du fehlende Stellen auf?"
            ),
            (
                S(
                    _("Kommas untereinander, mit Nullen aufgefüllt: %(a)s und %(b)s"),
                    a=z(a, st or None),
                    b=z(b, st or None),
                ),
                S(
                    _("%(a)s %(op)s %(b)s = %(r)s"),
                    a=z(a),
                    b=z(b),
                    op="+" if plus else "−",
                    r=z(a + b if plus else a - b),
                ),
            ),
        )
    if typ == "dezimal_mal_ganz":
        n = Fraction(p["b"])
        k = _stellen_hinter_komma(a)
        return Hilfe(
            (z(a), z(n)),
            _("das Produkt"),
            _("Rechne zuerst ohne Komma. Wo kommt das Komma am Ende hin? Zähle die Stellen."),
            (
                S(
                    _("Ohne Komma: %(a0)s · %(n)s = %(r1)s"),
                    a0=int(a * 10**k),
                    n=z(n),
                    r1=int(a * 10**k * n),
                ),
                S(
                    _("Stellen hinter dem Komma bei der Zahl: %(rk)s. Das Ergebnis: %(r)s"),
                    rk=k,
                    r=z(a * n),
                ),
            ),
        )
    if typ == "dezimal_mal_dezimal":
        b = Fraction(p["b"])
        ka, kb = _stellen_hinter_komma(a), _stellen_hinter_komma(b)
        return Hilfe(
            (z(a), z(b)),
            _("das Produkt"),
            _(
                "Rechne zuerst ohne Kommas. Wie viele Stellen hinter dem Komma haben beide Zahlen "
                "zusammen?"
            ),
            (
                S(
                    _("Ohne Kommas: %(a0)s · %(b0)s = %(r1)s"),
                    a0=int(a * 10**ka),
                    b0=int(b * 10**kb),
                    r1=int(a * 10**ka) * int(b * 10**kb),
                ),
                S(
                    _("Stellen hinter dem Komma zusammen: %(rk)s. Das Ergebnis: %(r)s"),
                    rk=ka + kb,
                    r=z(a * b),
                ),
            ),
        )
    n = Fraction(p["b"])  # dezimal_durch_ganz
    k = _stellen_hinter_komma(a)
    return Hilfe(
        (z(a), z(n)),
        _("der Quotient"),
        _(
            "Teile zuerst ohne Komma. Wo kommt das Komma hin? Es kommt dorthin, wo du die Ziffern "
            "hinter dem Komma erreichst."
        ),
        (
            S(
                _("Ohne Komma teilen: %(a0)s : %(n)s = %(r1)s"),
                a0=int(a * 10**k),
                n=z(n),
                r1=z(Fraction(int(a * 10**k)) / n),
            ),
            S(_("Das Komma setzen (%(rk)s Stellen): %(r)s"), rk=k, r=z(a / n)),
        ),
    )


@hilfe("prozent_anteil")
def prozent_anteil(aufgabe):
    p, typ = aufgabe.parameter, aufgabe.typ
    if typ == "anteil_von_100":
        a = p["anteil"]
        return Hilfe(
            (z(a), z(p["grundwert"])),
            _("der Anteil in Prozent"),
            _("Was bedeutet das Wort Prozent? Wie viele Hundertstel sind es?"),
            (S(_("%(a)s von %(g)s sind %(r)s %%"), a=a, g=p["grundwert"], r=a),),
        )
    if typ == "bruch_als_prozent":
        zl, n = p["zaehler"], p["nenner"]
        return Hilfe(
            (f"{zl}/{n}",),
            _("der Bruch als Prozentzahl"),
            _(
                "Auf welchen Nenner musst du den Bruch bringen, damit du die Prozent ablesen "
                "kannst?"
            ),
            (
                S(
                    _("Bringe den Bruch auf den Nenner %(rh)s: %(p)s/%(q)s = %(r1)s/%(rh)s"),
                    p=zl,
                    q=n,
                    rh=100,
                    r1=100 * zl // n,
                ),
                S(_("Der Zähler ist die Prozentzahl: %(r)s %%"), r=z(Fraction(100 * zl, n))),
            ),
        )
    a, g = p["anteil"], p["grundwert"]
    return Hilfe(
        (z(a), z(g)),
        _("der Anteil in Prozent"),
        _("Schreibe den Anteil als Bruch. Wie kommst du von diesem Bruch zu Hundertsteln?"),
        (
            S(_("Anteil als Bruch: %(a)s/%(g)s"), a=a, g=g),
            S(_("Teile: %(a)s : %(g)s = %(r1)s"), a=a, g=g, r1=z(Fraction(a, g))),
            S(
                _("In Prozent umrechnen: %(r1)s · %(rh)s = %(r)s %%"),
                r1=z(Fraction(a, g)),
                rh=100,
                r=z(Fraction(100 * a, g)),
            ),
        ),
    )


@hilfe("prozent_wert")
def prozent_wert(aufgabe):
    pz, g = aufgabe.parameter["prozent"], aufgabe.parameter["grundwert"]
    return Hilfe(
        (f"{pz} %", z(g)),
        _("der Prozentwert"),
        _("Wie viel ist ein Prozent vom Grundwert? Wie oft brauchst du dieses eine Prozent?"),
        (
            S(_("Ein Prozent: %(g)s : %(rh)s = %(r1)s"), g=g, rh=100, r1=z(Fraction(g, 100))),
            S(
                _("%(p)s Prozent: %(r1)s · %(p)s = %(r)s"),
                p=pz,
                r1=z(Fraction(g, 100)),
                r=z(Fraction(pz * g, 100)),
            ),
        ),
    )


@hilfe("groessen_umrechnen")
def groessen_umrechnen(aufgabe):
    p = aufgabe.parameter
    if aufgabe.typ == "mehrteilig":
        gross, klein = p["einheiten"]
        a, b = p["gross"], p["klein"]
        f = _FAKTOR[(gross, klein)]
        return Hilfe(
            (f"{a} {gross}", f"{b} {klein}"),
            _("die ganze Größe in der kleineren Einheit"),
            _(
                "Verwandle erst den großen Teil in die kleine Einheit. Was machst du dann mit dem "
                "anderen Teil?"
            ),
            (
                S(
                    _("Groß in klein: %(a)s %(g)s · %(rf)s = %(r1)s %(k)s"),
                    a=a,
                    g=gross,
                    rf=f,
                    r1=a * f,
                    k=klein,
                ),
                S(
                    _("Dazu der andere Teil: %(r1)s + %(b)s = %(r)s %(k)s"),
                    b=b,
                    r1=a * f,
                    r=a * f + b,
                    k=klein,
                ),
            ),
        )
    w, von, nach = Fraction(p["wert"]), p["von"], p["nach"]
    if (von, nach) in _FAKTOR:
        f, mal = _FAKTOR[(von, nach)], True
    else:
        f, mal = _FAKTOR[(nach, von)], False
    if mal:
        schritt = S(
            _("Ein %(v)s sind %(rf)s %(n)s: %(w)s · %(rf)s = %(r)s %(n)s"),
            v=von,
            n=nach,
            rf=f,
            w=z(w),
            r=z(w * f),
        )
        denk = _(
            "Ist die neue Einheit größer oder kleiner? Wird die Zahl dann größer oder kleiner? Mal "
            "oder geteilt?"
        )
    else:
        schritt = S(
            _("Ein %(n)s sind %(rf)s %(v)s: %(w)s : %(rf)s = %(r)s %(n)s"),
            v=von,
            n=nach,
            rf=f,
            w=z(w),
            r=z(w / f),
        )
        denk = _(
            "Ist die neue Einheit größer oder kleiner? Wird die Zahl dann größer oder kleiner? Mal "
            "oder geteilt?"
        )
    return Hilfe((f"{z(w)} {von}",), _("die Größe in der neuen Einheit"), denk, (schritt,))


@hilfe("punkt_vor_strich")
def punkt_vor_strich(aufgabe):
    term = aufgabe.parameter["term"]
    return Hilfe(
        _zahlen_im_term(term),
        _("das Ergebnis der ganzen Rechnung"),
        _(
            "Welche Rechnung musst du zuerst machen? Denke daran: Malnehmen und Teilen kommen vor "
            "Plus und Minus."
        ),
        tuple(ausdruck.schritte_fuer(term)),
    )


def _zahlen_im_term(term):
    return tuple(dict.fromkeys(re.findall(r"\d+", term)))


@hilfe("klammern")
def klammern(aufgabe):
    p, typ = aufgabe.parameter, aufgabe.typ
    if typ == "vorteilhaft_mal":
        zahlen = [int(x) for x in re.findall(r"\d+", p["term"])]
        paar = next(
            (x, y)
            for x in zahlen
            for y in zahlen
            if x != y and x * y == 100 and zahlen.index(x) != zahlen.index(y)
        )
        rest = list(zahlen)
        rest.remove(paar[0])
        rest.remove(paar[1])
        m = rest[0]
        return Hilfe(
            _zahlen_im_term(p["term"]),
            _("das Ergebnis, geschickt gerechnet"),
            _(
                "Welche Zahlen ergeben zusammen eine runde Zahl? Du darfst die Reihenfolge beim "
                "Malnehmen tauschen."
            ),
            (
                S(
                    _("Fasse geschickt zusammen: %(x)s · %(y)s = %(r1)s"),
                    x=paar[0],
                    y=paar[1],
                    r1=100,
                ),
                S(_("Rechne weiter: %(r1)s · %(m)s = %(r)s"), r1=100, m=m, r=100 * m),
            ),
        )
    if typ == "vorteilhaft_verteilen":
        m, x, m2, y = (int(v) for v in re.findall(r"\d+", p["term"]))
        return Hilfe(
            _zahlen_im_term(p["term"]),
            _("das Ergebnis, geschickt gerechnet"),
            _(
                "Kommt in beiden Produkten dieselbe Zahl vor? Dann kannst du sie ausklammern und "
                "zuerst die Klammer rechnen."
            ),
            (
                S(_("Klammere aus: %(m)s · (%(x)s + %(y)s)"), m=m, x=x, y=y),
                S(_("Rechne die Klammer: %(x)s + %(y)s = %(r1)s"), x=x, y=y, r1=x + y),
                S(_("Dann: %(m)s · %(r1)s = %(r)s"), m=m, r1=x + y, r=m * (x + y)),
            ),
        )
    text = aufgabe.text
    return Hilfe(
        _zahlen_im_term(text),
        _("das Ergebnis der ganzen Rechnung"),
        _("Was steht in der Klammer? Die Klammer rechnest du zuerst. Was kommt danach?"),
        tuple(ausdruck.schritte_fuer(text)),
    )
