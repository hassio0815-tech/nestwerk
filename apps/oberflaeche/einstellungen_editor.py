"""Generischer Einstellungen-Editor: Formularfelder, Parsen und Speichern direkt aus den
Definitionen der Registry (``kern.einstellungen``). Neue Einstellungen erscheinen ohne
Änderung hier. Gespeichert wird über ``einstellungen.setzen`` (Validierung + Audit)."""

from django.db import transaction

from apps.kern import einstellungen
from apps.kern.einstellungen import Typ

MODUL_TITEL = {
    "allgemein": "Allgemein",
    "konten": "Anmeldung und Geräte",
    "aufgaben": "Aufgaben",
    "belohnung": "Belohnungen",
    "benachrichtigung": "Benachrichtigungen",
    "einrichtung": "Einrichtung",
    "oberflaeche": "Oberfläche und Tablet",
    "punkte": "Punkte",
    "ereignisse": "Ereignisse und Betrieb",
    "spielregeln": "Spielregeln",
}
ZUERST = ("allgemein",)


class FeldFehler(ValueError):
    """Eingabe lässt sich nicht in den Typ der Einstellung umwandeln."""


def modul_titel(modul):
    return MODUL_TITEL.get(modul, modul.capitalize())


def definitionen(modul=None):
    """Im Editor änderbare Definitionen: ohne interne (technischer Zustand, z. B. ob die
    Einrichtung abgeschlossen ist; sonst ließe sich der Assistent versehentlich wieder öffnen)."""
    return [d for d in einstellungen.definitionen(modul) if not d.intern]


def module():
    """Module mit Einstellungen: ``allgemein`` zuerst, dann alphabetisch nach Titel."""
    namen = {d.modul for d in definitionen()}
    return sorted(namen, key=lambda m: (m not in ZUERST, modul_titel(m).lower()))


def _text(definition, wert):
    typ = definition.element_typ if definition.typ is Typ.LISTE else definition.typ
    if typ is Typ.UHRZEIT and hasattr(wert, "strftime"):
        return wert.strftime("%H:%M")
    if typ is Typ.DATUM and hasattr(wert, "isoformat"):
        return wert.isoformat()
    return str(wert)


def anzeige_text(definition, wert):
    """Wert -> Text im Formularfeld."""
    if definition.typ is Typ.LISTE:
        return "\n".join(_text(definition, e) for e in wert)
    if definition.typ is Typ.BOOL:
        return "1" if wert else ""
    return _text(definition, wert)


def feldart(definition):
    if definition.typ is Typ.BOOL:
        return "bool"
    if definition.typ is Typ.LISTE:
        return "liste"
    if definition.auswahl is not None:
        return "auswahl"
    return {
        Typ.GANZZAHL: "zahl",
        Typ.DATUM: "datum",
        Typ.UHRZEIT: "uhrzeit",
    }.get(definition.typ, "text")


def _gespeichert():
    return einstellungen.gespeicherte_werte()


def felder(modul, *, eingaben=None, fehler=None):
    """Felder eines Moduls für das Template. ``eingaben`` = vom Nutzer eingegebene Texte
    (nach fehlgeschlagenem Speichern), ``fehler`` = ``{schluessel: Meldung}``."""
    gespeichert = _gespeichert()
    eingaben = eingaben or {}
    fehler = fehler or {}
    ergebnis = []
    for d in definitionen(modul):
        fehlt = d.schluessel not in gespeichert
        if d.schluessel in eingaben:
            text = eingaben[d.schluessel]
        elif fehlt:
            text = ""
        else:
            try:
                text = anzeige_text(d, d.lesen(gespeichert[d.schluessel]))
            except einstellungen.EinstellungFehler:
                text = ""
        ergebnis.append(
            {
                "definition": d,
                "name": d.schluessel,
                "art": feldart(d),
                "text": text,
                "fehlt": fehlt,
                "fehler": fehler.get(d.schluessel, ""),
                "auswahl": list(d.auswahl) if d.auswahl is not None else [],
            }
        )
    return ergebnis


def _einzeln(typ, text):
    if typ is Typ.GANZZAHL:
        try:
            return int(text.strip())
        except ValueError:
            raise FeldFehler("Bitte eine ganze Zahl eingeben.") from None
    return text.strip() if typ in (Typ.DATUM, Typ.UHRZEIT, Typ.ZEITZONE) else text


def parsen(definition, rohtext):
    """Formulartext -> Python-/JSON-Wert für ``Definition.pruefen``."""
    if definition.typ is Typ.BOOL:
        return rohtext == "1"
    if definition.typ is Typ.LISTE:
        teile = [t.strip() for t in rohtext.replace(",", "\n").splitlines()]
        return [_einzeln(definition.element_typ, t) for t in teile if t]
    return _einzeln(definition.typ, rohtext)


def eingaben_aus_post(modul, post):
    """Rohtexte aller Felder des Moduls. Fehlende Checkbox = ausgeschaltet."""
    eingaben = {}
    for d in definitionen(modul):
        if d.typ is Typ.BOOL:
            eingaben[d.schluessel] = "1" if post.getlist(d.schluessel)[-1:] == ["1"] else ""
        elif d.schluessel in post:
            eingaben[d.schluessel] = post.get(d.schluessel, "")
    return eingaben


def speichern(modul, eingaben):
    """Prüft alle Felder des Moduls und speichert nur, wenn **alle** gültig sind.

    Rückgabe: ``(fehler, geaendert)``; ``fehler`` = ``{schluessel: Meldung}``, ``geaendert`` =
    Schlüssel, deren Wert sich geändert hat.
    """
    fehler = {}
    neue = {}
    for d in definitionen(modul):
        if d.schluessel not in eingaben:
            continue
        try:
            neue[d.schluessel] = d.pruefen(parsen(d, eingaben[d.schluessel]))
        except FeldFehler as exc:
            fehler[d.schluessel] = str(exc)
        except einstellungen.UngueltigerWert as exc:
            fehler[d.schluessel] = _meldung(exc)
    if fehler:
        return fehler, []
    gespeichert = _gespeichert()
    geaendert = []
    with transaction.atomic():
        for schluessel, json_wert in neue.items():
            if gespeichert.get(schluessel, _FEHLT) != json_wert:
                einstellungen.setzen(schluessel, json_wert)
                geaendert.append(schluessel)
    return {}, geaendert


_FEHLT = object()


def _meldung(exc):
    """Kurzer Grund aus ``Einstellung 'x': 5 ungültig (grund)``."""
    text = str(exc)
    if "(" in text and text.endswith(")"):
        grund = text[text.rindex("(") + 1 : -1]
        return grund[:1].upper() + grund[1:] + "."
    return "Ungültiger Wert."
