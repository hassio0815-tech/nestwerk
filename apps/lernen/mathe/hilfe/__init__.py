"""Hilfeleiter für Mathe-Aufgaben (SPEC 21.3, 21.13, Etappe 10b): lokal, regelbasiert, ohne KI.

Fünf Stufen, jede nur auf Wunsch des Kindes:

1. Nachfragen: was ist gegeben, was gesucht (mit den Zahlen der Aufgabe)
2. Denkanstoß passend zur Rechenart
3. analoges Beispiel mit ANDEREN Zahlen, ganz vorgerechnet (``registry.analog``-Prinzip)
4. Verweis auf die Erklärkarte der Rechenart
5. Lösungsstruktur der ECHTEN Aufgabe als Gerüst ohne Zwischen- und Endergebnisse (``___``)

Die Lösung der echten Aufgabe steht in keiner Stufe. Das stellt zweierlei sicher: Die Texte werden
aus den Zahlen der Aufgabe gebaut und enthalten Ergebnisse nur als ``___``; und ``leckt`` prüft
jeden Text noch einmal gegen die Lösung (sonst weicht er auf eine neutrale Form aus). Pro
Rechenart gibt es eine Definition in ``klasse3``, ``klasse6`` oder ``klasse8`` (Registry:
``register``).
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext as _

from .. import registry
from ..aufgabe import Aufgabe, Loesung
from . import klasse3, klasse6, klasse8  # noqa: F401  (melden ihre Definitionen an)
from .bau import LUECKE, Hilfe, leckt, zahlen_in
from .karten import KartenText, karte_fuer, karte_text
from .karten import alle_karten as alle_karten
from .register import definition, schluessel_alle

STUFEN = (1, 2, 3, 4, 5)
MAX_STUFE = 5
BEISPIEL_VERSUCHE = 200


@dataclass(frozen=True)
class Stufentext:
    """Der Text einer Stufe, fertig übersetzt. ``zeilen``: die Rechenschritte (Stufen 3 und 5)."""

    stufe: int
    titel: str
    absaetze: tuple = ()
    zeilen: tuple = ()
    karte: str = ""  # Schlüssel der Erklärkarte (Stufe 4)
    ersatz: bool = False  # der Text musste auf eine neutrale Form ausweichen
    beispiel: object = field(default=None, compare=False)


def titel(stufe):
    return {
        1: _("Stufe 1: Nachfragen"),
        2: _("Stufe 2: Denkanstoß"),
        3: _("Stufe 3: Ein ähnliches Beispiel"),
        4: _("Stufe 4: Der Rechen-Tipp"),
        5: _("Stufe 5: So gehst du vor"),
    }[stufe]


def aufgabe_aus_frage(frage):
    """Die ``Aufgabe`` zu einer erzeugten ``Frage`` (aus ``gen_daten``); ``None`` sonst."""
    daten = frage.gen_daten if frage.generiert else None
    if not daten or daten.get("generator") not in registry.alle():
        return None
    return Aufgabe(
        generator=daten["generator"],
        typ=daten["typ"],
        thema=daten["thema"],
        klassenstufe=daten["klassenstufe"],
        schwierigkeit=daten["schwierigkeit"],
        seed=daten["seed"],
        text=frage.frage,
        loesung=Loesung.from_dict(daten["loesung"]),
        parameter=daten.get("parameter", {}),
    )


def hat_hilfe(generator):
    return definition(generator) is not None


def alle_definitionen():
    return schluessel_alle()


def _neutral(aufgabe):
    """Allgemeine Hilfe ohne Zahlen, falls eine Definition fehlt oder versagt."""
    return Hilfe(
        (),
        _("das Ergebnis der Aufgabe"),
        _("Lies die Aufgabe noch einmal. Was weißt du schon? Was fehlt dir noch?"),
        (),
    )


def hilfe_fuer(aufgabe):
    """Die ``Hilfe`` zur Aufgabe; bei einem Fehler in der Definition die neutrale Form."""
    funktion = definition(aufgabe.generator)
    if funktion is None:
        return _neutral(aufgabe), True
    try:
        return funktion(aufgabe), False
    except Exception:  # noqa: BLE001  Hilfe darf das Üben nie stoppen
        return _neutral(aufgabe), True


# --- Das analoge Beispiel -------------------------------------------------------------------------


def _kern(aufgabe):
    return {k: v for k, v in aufgabe.parameter.items() if k != "grenze"}


def beispiel_fuer(aufgabe):
    """Eine gleichartige Aufgabe mit ANDEREN Zahlen und anderer Lösung (nie dieselbe Aufgabe).

    Bevorzugt: gleicher Typ, keine gemeinsame Zahl im Text, andere Lösung, und der vorgerechnete
    Text enthält nicht die Lösung der echten Aufgabe. Sonst weniger streng, aber immer mit anderen
    Zahlen und anderer Lösung (soweit der Zahlenraum der Rechenart es zulässt)."""
    kontext = registry.Kontext(aufgabe.parameter.get("grenze"))
    echte = zahlen_in(aufgabe.text)
    kern = _kern(aufgabe)
    stufen = [[], [], []]
    for i in range(1, BEISPIEL_VERSUCHE + 1):
        kand = registry.erzeugen(
            aufgabe.generator, aufgabe.schwierigkeit, aufgabe.seed + i, kontext
        )
        if _kern(kand) == kern or kand.loesung.anzeige == aufgabe.loesung.anzeige:
            continue
        if (
            kand.loesung.wert
            and kand.loesung.wert == aufgabe.loesung.wert
            and kand.loesung.rest == aufgabe.loesung.rest
        ):
            continue
        gleich_typ = kand.typ == aufgabe.typ
        fremd = not (zahlen_in(kand.text) & echte)
        if gleich_typ and fremd:
            sicher = _beispiel_sicher(kand, aufgabe)
            if sicher:
                return kand
            stufen[0].append(kand)
        elif gleich_typ:
            stufen[1].append(kand)
        else:
            stufen[2].append(kand)
        if len(stufen[0]) >= 3:
            break
    for gruppe in stufen:
        if gruppe:
            return gruppe[0]
    return None


def _beispiel_sicher(beispiel, aufgabe):
    text = _beispiel_text(beispiel)
    return not leckt(text, aufgabe)


def _beispiel_text(beispiel):
    hilfe, _fehler = hilfe_fuer(beispiel)
    zeilen = [s.zeile(False) for s in hilfe.schritte]
    return "\n".join([beispiel.text, *zeilen, beispiel.loesung.anzeige])


# --- Die Stufen -----------------------------------------------------------------------------


def _stufe1(hilfe):
    absaetze = [_("Lies die Aufgabe noch einmal in Ruhe.")]
    if hilfe.gegeben:
        # Dezimalzahlen haben ein Komma: dann trennt ein Semikolon ("23,2; 12,5" statt "23,2, 12,5")
        trenner = "; " if any("," in g for g in hilfe.gegeben) else ", "
        absaetze.append(_("Gegeben ist: %(g)s.") % {"g": trenner.join(hilfe.gegeben)})
    absaetze.append(_("Gesucht ist: %(s)s.") % {"s": hilfe.gesucht})
    absaetze.append(_("Magst du es mit eigenen Worten sagen, bevor du rechnest?"))
    return absaetze


def _stufe5(aufgabe, hilfe):
    """Das Gerüst; erst mit allen Aufgabenzahlen, bei Treffern nur noch mit denen aus dem Text."""
    for sichtbar in (None, zahlen_in(aufgabe.text)):
        zeilen = [s.zeile(True, sichtbar) for s in hilfe.schritte]
        zeilen.append(_("Ergebnis: %(l)s") % {"l": LUECKE})
        if not leckt("\n".join(zeilen), aufgabe):
            return zeilen, False
    return [], True


def stufe_text(aufgabe, stufe, sprachstufe=2):
    """Der Text der Stufe ``stufe`` (1 bis 5) zur Aufgabe, in der Sprache des Aufrufers."""
    if stufe not in STUFEN:
        raise ValueError(f"Hilfestufe {stufe}")
    hilfe, ersatz = hilfe_fuer(aufgabe)
    ueberschrift = titel(stufe)
    if stufe == 1:
        absaetze = _stufe1(hilfe)
        if leckt("\n".join(absaetze), aufgabe):
            absaetze, ersatz = _stufe1(_neutral(aufgabe)), True
        return Stufentext(1, ueberschrift, tuple(absaetze), ersatz=ersatz)
    if stufe == 2:
        absaetze = [hilfe.denk]
        if leckt(hilfe.denk, aufgabe):
            absaetze, ersatz = [_neutral(aufgabe).denk], True
        return Stufentext(2, ueberschrift, tuple(absaetze), ersatz=ersatz)
    if stufe == 3:
        beispiel = beispiel_fuer(aufgabe)
        if beispiel is None:
            return Stufentext(
                3,
                ueberschrift,
                (_("Für diese Aufgabe gibt es gerade kein Beispiel."),),
                ersatz=True,
            )
        h, fehler = hilfe_fuer(beispiel)
        zeilen = [s.zeile(False) for s in h.schritte]
        zeilen.append(_("Ergebnis des Beispiels: %(l)s") % {"l": beispiel.loesung.anzeige})
        absaetze = (
            _("So rechnet man eine ähnliche Aufgabe mit anderen Zahlen:"),
            beispiel.text,
        )
        return Stufentext(
            3, ueberschrift, absaetze, tuple(zeilen), ersatz=fehler, beispiel=beispiel
        )
    if stufe == 4:
        karte = karte_fuer(aufgabe.generator)
        verweis = _("Schau in die Rechen-Tipps. Dort steht die Regel zu deiner Aufgabe.")
        absaetze = [verweis]
        if karte is not None:
            text = karte_text(karte, sprachstufe, mit_beispiel=False)
            # erst mit Titel und Merksatz, dann nur mit dem Titel, sonst nur der Verweis
            for versuch in ([text.titel, verweis, text.merksatz], [text.titel, verweis]):
                if not leckt("\n".join(versuch), aufgabe):
                    absaetze = versuch
                    break
        return Stufentext(4, ueberschrift, tuple(absaetze), karte=karte.schluessel if karte else "")
    zeilen, ersatz5 = _stufe5(aufgabe, hilfe)
    absaetze = [_("So gehst du vor. Die Striche füllst du selbst aus.")]
    if ersatz5:
        absaetze = [hilfe.denk]
    return Stufentext(5, ueberschrift, tuple(absaetze), tuple(zeilen), ersatz=ersatz or ersatz5)


def stufen_bis(aufgabe, bis, sprachstufe=2):
    """Die Texte der Stufen 1 bis ``bis`` (jede Stufe, die das Kind schon freigeschaltet hat)."""
    return [stufe_text(aufgabe, s, sprachstufe) for s in range(1, min(bis, MAX_STUFE) + 1)]


def karte_anzeige(aufgabe, sprachstufe=2):
    """Die Erklärkarte zur offenen Aufgabe für die Üben-Seite: ``(KartenText, verborgen)``.

    Zeigt die Karte ein Ergebnis, das die Lösung der offenen Aufgabe wäre (z. B. ``1 m = 100 cm``),
    fällt erst das Beispiel und dann der Merksatz weg (``verborgen=True``: nur der Titel bleibt,
    der Text steht unter "Rechen-Tipps"). ``None``, wenn es keine Karte gibt."""
    karte = karte_fuer(aufgabe.generator)
    if karte is None:
        return None
    text = karte_text(karte, sprachstufe)
    if not leckt(f"{text.merksatz}\n{text.beispiel}", aufgabe):
        return text, False
    ohne = karte_text(karte, sprachstufe, mit_beispiel=False)
    if not leckt(ohne.merksatz, aufgabe):
        return ohne, False
    return KartenText(text.schluessel, text.titel, "", ""), True
