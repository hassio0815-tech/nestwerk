"""Lokale Textaufgaben-Vorlagen (SPEC 21.13, Etappe 10b): Einkleidung ohne KI.

Zu den Zahlen einer erzeugten Aufgabe gibt es eine kurze Sachaufgabe. Alle Zahlen kommen aus der
Aufgabe, nie neue, und die Lösung ist dieselbe wie bei der reinen Rechnung. Pro Rechenart (wo es
sinnvoll ist) mindestens zwei Vorlagen; welche gilt, entscheidet der Seed. Keine Namen von Personen.

Dieselben Rechenarten kann (nur auf Wunsch der Eltern) die KI einkleiden, siehe ``mathe_ki``.
"""

import re
from fractions import Fraction

from django.utils.translation import gettext as _

from .hilfe.bau import z

_VORLAGEN = {}


def vorlagen(generator_schluessel):
    """Decorator: meldet die Vorlagen einer Rechenart an. Die Funktion gibt die Liste der Texte
    (übersetzt) zurück, ``[]`` für Aufgabentypen ohne Vorlage."""

    def anmelden(funktion):
        _VORLAGEN[generator_schluessel] = funktion
        return funktion

    return anmelden


def generatoren():
    return tuple(_VORLAGEN)


def alle_texte(aufgabe):
    """Alle Textfassungen der Aufgabe (leer, wenn es für sie keine gibt)."""
    funktion = _VORLAGEN.get(aufgabe.generator)
    if funktion is None:
        return []
    try:
        return funktion(aufgabe)
    except (KeyError, ValueError, TypeError, AttributeError):
        return []


def hat_vorlage(aufgabe):
    return bool(alle_texte(aufgabe))


def lokal(aufgabe):
    """Die lokale Textfassung (der Seed wählt unter den Vorlagen), ``None`` ohne Vorlage."""
    texte = alle_texte(aufgabe)
    return texte[aufgabe.seed % len(texte)] if texte else None


@vorlagen("add_sub_100")
@vorlagen("add_sub_1000")
def _add_sub(a):
    p = {"a": a.parameter["a"], "b": a.parameter["b"]}
    if a.parameter["op"] == "+":
        return [
            _(
                "In einer Schachtel liegen %(a)s Murmeln. Es kommen %(b)s dazu. Wie viele Murmeln "
                "sind es jetzt?"
            )
            % p,
            _(
                "Im Bus sitzen %(a)s Fahrgäste. An der Haltestelle steigen %(b)s ein. Wie viele "
                "Fahrgäste sind jetzt im Bus?"
            )
            % p,
        ]
    return [
        _(
            "Im Regal stehen %(a)s Bücher. %(b)s Bücher werden ausgeliehen. Wie viele Bücher "
            "stehen noch im Regal?"
        )
        % p,
        _(
            "Auf dem Schulhof spielen %(a)s Kinder. %(b)s Kinder gehen ins Haus. Wie viele Kinder "
            "spielen noch draußen?"
        )
        % p,
    ]


@vorlagen("einmaleins")
def _einmaleins(a):
    p = {"a": a.parameter["a"], "b": a.parameter["b"]}
    return [
        _(
            "Eine Packung hat %(a)s Kekse. Du kaufst %(b)s Packungen. Wie viele Kekse sind das "
            "zusammen?"
        )
        % p,
        _("In einem Saal gibt es %(a)s Reihen mit je %(b)s Stühlen. Wie viele Stühle sind es?") % p,
    ]


@vorlagen("umkehr")
def _umkehr(a):
    p = a.parameter
    if "ziel" in p:
        q = {"a": p["a"], "z": p["ziel"]}
        return [
            _(
                "Du hast %(a)s Punkte gesammelt und brauchst %(z)s Punkte. Wie viele Punkte fehlen "
                "noch?"
            )
            % q,
            _(
                "In einem Korb sollen %(z)s Äpfel liegen. Schon drin sind %(a)s. Wie viele Äpfel "
                "fehlen noch?"
            )
            % q,
        ]
    q = {"f": p["faktor"], "p": p["produkt"]}
    return [
        _(
            "In jeder Tüte sind %(f)s Bonbons. Insgesamt sind es %(p)s Bonbons. Wie viele Tüten "
            "sind das?"
        )
        % q,
        _(
            "Es gibt %(p)s Stifte. Jedes Kind bekommt %(f)s Stifte. Wie viele Kinder sind in der "
            "Gruppe?"
        )
        % q,
    ]


@vorlagen("division_ohne_rest")
def _division(a):
    p = {"d": a.parameter["dividend"], "t": a.parameter["teiler"]}
    return [
        _(
            "%(d)s Karten werden gleichmäßig an %(t)s Kinder verteilt. Wie viele Karten bekommt "
            "jedes Kind?"
        )
        % p,
        _("%(d)s Murmeln werden in Gruppen zu je %(t)s Murmeln gelegt. Wie viele Gruppen sind das?")
        % p,
    ]


@vorlagen("mult_schriftlich")
def _mult(a):
    p = {"a": a.parameter["a"], "b": a.parameter["b"]}
    return [
        _(
            "Ein Lastwagen bringt bei jeder Fahrt %(a)s Kisten. Er fährt %(b)s Mal. Wie viele "
            "Kisten sind das insgesamt?"
        )
        % p,
        _(
            "Ein Verlag druckt %(b)s Bücher mit je %(a)s Seiten. Wie viele Seiten sind das "
            "insgesamt?"
        )
        % p,
    ]


@vorlagen("div_schriftlich")
def _div(a):
    p = {"d": a.parameter["dividend"], "t": a.parameter["teiler"]}
    if a.typ == "div_mit_rest":
        return [
            _(
                "%(d)s Schüler fahren in Bussen mit je %(t)s Plätzen. Wie viele volle Busse sind "
                "es, und wie viele Schüler bleiben übrig? Schreibe das Ergebnis mit Rest."
            )
            % p,
            _(
                "%(d)s Eier werden in Packungen zu je %(t)s Stück gepackt. Wie viele volle "
                "Packungen gibt es, und wie viele Eier bleiben übrig? Schreibe das Ergebnis mit "
                "Rest."
            )
            % p,
        ]
    if a.typ == "div_dezimal":
        return [
            _(
                "%(d)s Liter Saft werden gleichmäßig auf %(t)s Gläser verteilt. Wie viele Liter "
                "kommen in jedes Glas? Gib das Ergebnis als Dezimalzahl an."
            )
            % p,
            _(
                "%(d)s Meter Band werden in %(t)s gleich lange Stücke geschnitten. Wie lang ist "
                "ein Stück in Metern? Gib das Ergebnis als Dezimalzahl an."
            )
            % p,
        ]
    return [
        _(
            "%(d)s Schüler fahren in Bussen mit je %(t)s Plätzen, alle Busse sind voll. Wie viele "
            "Busse sind es?"
        )
        % p,
        _("%(d)s Kekse werden gerecht an %(t)s Gäste verteilt. Wie viele Kekse bekommt jeder Gast?")
        % p,
    ]


@vorlagen("bruch_addsub")
def _bruch(a):
    (p1, q1), (p2, q2) = a.parameter["a"], a.parameter["b"]
    p = {"a": f"{p1}/{q1}", "b": f"{p2}/{q2}"}
    if a.parameter["op"] == "+":
        return [
            _(
                "Zuerst wird %(a)s einer Pizza gegessen, später noch %(b)s. Welcher Teil der Pizza "
                "ist gegessen? Gib den Bruch gekürzt an."
            )
            % p,
            _(
                "Ein Tank ist zu %(a)s gefüllt. Dann kommen %(b)s Tankfüllungen dazu. Welcher Teil "
                "des Tanks ist jetzt gefüllt? Gib den Bruch gekürzt an."
            )
            % p,
        ]
    return [
        _(
            "Von einem Kuchen sind %(a)s übrig. Davon werden %(b)s eines ganzen Kuchens gegessen. "
            "Welcher Teil des Kuchens bleibt? Gib den Bruch gekürzt an."
        )
        % p,
        _(
            "Ein Tank ist zu %(a)s voll. Es werden %(b)s Tankfüllungen entnommen. Welcher Teil des "
            "Tanks ist noch voll? Gib den Bruch gekürzt an."
        )
        % p,
    ]


@vorlagen("prozent_wert")
def _prozent(a):
    p = {"p": a.parameter["prozent"], "g": a.parameter["grundwert"]}
    return [
        _(
            "In einer Schule sind %(g)s Kinder. %(p)s %% davon kommen mit dem Rad. Wie viele "
            "Kinder sind das?"
        )
        % p,
        _(
            "Ein Sack enthält %(g)s Kilogramm Kartoffeln. %(p)s %% davon sind für die Suppe. Wie "
            "viele Kilogramm sind das?"
        )
        % p,
    ]


@vorlagen("dezimal_rechnen")
def _dezimal(a):
    if a.typ not in ("dezimal_add", "dezimal_sub"):
        return []
    p = {"a": z(Fraction(a.parameter["a"])), "b": z(Fraction(a.parameter["b"]))}
    if a.typ == "dezimal_add":
        return [
            _(
                "Ein Brett ist %(a)s m lang, ein zweites %(b)s m. Wie lang sind beide zusammen? "
                "Gib das Ergebnis in Metern an."
            )
            % p,
            _(
                "In einen Eimer kommen erst %(a)s Liter Wasser, dann noch %(b)s Liter. Wie viele "
                "Liter sind es jetzt?"
            )
            % p,
        ]
    return [
        _(
            "Von einem Band mit %(a)s m Länge werden %(b)s m abgeschnitten. Wie viele Meter "
            "bleiben übrig?"
        )
        % p,
        _(
            "Ein Eimer enthält %(a)s Liter. Es werden %(b)s Liter ausgegossen. Wie viele Liter "
            "bleiben?"
        )
        % p,
    ]


@vorlagen("gleichung_linear")
def _gleichung(a):
    text = a.parameter["gleichung"].replace("-", "−")
    num = r"(\d+)"
    if a.typ == "plus":
        k, c = re.fullmatch(rf"x \+ {num} = {num}", text).groups()
        p = {"a": k, "c": c}
        return [
            _("Ich denke mir eine Zahl x und addiere %(a)s. Ich erhalte %(c)s. Wie heißt x?") % p,
            _("Wenn du zu einer Zahl x die Zahl %(a)s dazuzählst, kommt %(c)s heraus. Wie heißt x?")
            % p,
        ]
    if a.typ == "minus":
        k, c = re.fullmatch(rf"x − {num} = {num}", text).groups()
        p = {"a": k, "c": c}
        return [
            _("Ich denke mir eine Zahl x und ziehe %(a)s ab. Ich erhalte %(c)s. Wie heißt x?") % p,
            _("Wenn du von einer Zahl x die Zahl %(a)s wegnimmst, bleibt %(c)s. Wie heißt x?") % p,
        ]
    if a.typ == "mal":
        k, c = re.fullmatch(rf"{num}x = {num}", text).groups()
        p = {"a": k, "c": c}
        return [
            _("Ich denke mir eine Zahl x und nehme sie mal %(a)s. Ich erhalte %(c)s. Wie heißt x?")
            % p,
            _("Eine Zahl x wird mit %(a)s malgenommen, das Ergebnis ist %(c)s. Wie heißt x?") % p,
        ]
    if a.typ in ("mal_plus", "mal_minus"):
        k, vz, b, c = re.fullmatch(rf"{num}x ([+−]) {num} = {num}", text).groups()
        p = {"a": k, "b": b, "c": c}
        if vz == "+":
            return [
                _(
                    "Ich nehme eine Zahl x mal %(a)s und addiere dann %(b)s. Ich erhalte %(c)s. "
                    "Wie heißt x?"
                )
                % p,
                _(
                    "Eine Zahl x wird mit %(a)s malgenommen, dazu kommen %(b)s. Das Ergebnis ist "
                    "%(c)s. Wie heißt x?"
                )
                % p,
            ]
        return [
            _(
                "Ich nehme eine Zahl x mal %(a)s und ziehe dann %(b)s ab. Ich erhalte %(c)s. Wie "
                "heißt x?"
            )
            % p,
            _(
                "Eine Zahl x wird mit %(a)s malgenommen, davon werden %(b)s abgezogen. Das "
                "Ergebnis ist %(c)s. Wie heißt x?"
            )
            % p,
        ]
    return []


@vorlagen("wurzeln")
def _wurzeln(a):
    if a.typ not in ("wurzel", "quadrat_umkehren"):
        return []
    p = {"q": a.parameter.get("radikand") or a.parameter["quadrat"]}
    return [
        _(
            "Ein quadratisches Beet hat eine Fläche von %(q)s Quadratmetern. Wie lang ist eine "
            "Seite in Metern?"
        )
        % p,
        _(
            "Ein Quadrat hat den Flächeninhalt %(q)s Quadratzentimeter. Wie lang ist eine Seite in "
            "Zentimetern?"
        )
        % p,
    ]


@vorlagen("negative_zahlen")
def _negativ(a):
    m = re.fullmatch(r"−(\d+) \+ (\d+)", a.parameter["term"])
    if a.typ == "neg_plus_pos" and m:
        p = {"a": m.group(1), "b": m.group(2)}
        return [
            _(
                "Am Morgen zeigt das Thermometer −%(a)s Grad. Bis zum Mittag wird es %(b)s Grad "
                "wärmer. Wie viele Grad zeigt es dann?"
            )
            % p,
            _(
                "Ein U-Boot taucht in −%(a)s Metern Höhe, also unter dem Meeresspiegel. Es steigt "
                "%(b)s Meter auf. In welcher Höhe ist es dann?"
            )
            % p,
        ]
    m = re.fullmatch(r"(\d+) − (\d+)", a.parameter["term"])
    if a.typ == "pos_minus_gross" and m:
        p = {"a": m.group(1), "b": m.group(2)}
        return [
            _(
                "Auf einem Konto sind %(a)s Euro. Es werden %(b)s Euro abgebucht. Wie hoch ist der "
                "Kontostand jetzt (in Euro)?"
            )
            % p,
            _(
                "Es sind %(a)s Grad. Bis zur Nacht wird es %(b)s Grad kälter. Wie viele Grad zeigt "
                "das Thermometer dann?"
            )
            % p,
        ]
    return []
