"""Schritt 7: generische Übersicht aller Einstellungen aus der Registry, gruppiert nach Modul.

Neue Module erscheinen automatisch, sobald sie Einstellungen deklarieren. Schritte 1, 5 und 6
behandeln einzelne Schlüssel; sie fehlen hier.
"""

import re
from collections import defaultdict

from apps.kern import einstellungen
from apps.kern.einstellungen import Typ

MODUL_TITEL = {
    "allgemein": "Allgemein",
    "konten": "Anmeldung und Sicherheit",
    "punkte": "Punkte",
    "aufgaben": "Aufgaben",
    "belohnung": "Belohnungen und Taschengeld",
    "benachrichtigung": "Benachrichtigungen",
    "spielregeln": "Spielregeln",
}
AUSGEBLENDETE_MODULE = {"einrichtung"}
BEHANDELT = {
    "allgemein.anzeigename",
    "allgemein.sprache",
    "allgemein.zeitzone",
    "allgemein.go_live_datum",
    "allgemein.einrichtung_abgeschlossen",
    "konten.kind_netze_cidr",
    "konten.vertraute_proxys",
}
TRENNER = re.compile(r"[\n,;]+")


def schluessel_der_uebersicht():
    return [
        d.schluessel
        for d in einstellungen.definitionen()
        if d.modul not in AUSGEBLENDETE_MODULE and d.schluessel not in BEHANDELT
    ]


def _art(d):
    if d.typ is Typ.BOOL:
        return "bool"
    if d.typ is Typ.LISTE:
        return "liste"
    if d.auswahl is not None:
        return "auswahl"
    return {
        Typ.GANZZAHL: "zahl",
        Typ.DATUM: "datum",
        Typ.UHRZEIT: "uhrzeit",
    }.get(d.typ, "text")


def _aktuell(d):
    try:
        return einstellungen.wert(d.schluessel)
    except einstellungen.EinstellungFehlt:
        return None


def _als_text(d, wert):
    if wert is None:
        return ""
    if d.typ is Typ.LISTE:
        trenner = ", " if d.element_typ is Typ.GANZZAHL else "\n"
        return trenner.join(str(e) for e in wert)
    if d.typ in (Typ.DATUM, Typ.UHRZEIT):
        return wert.isoformat(timespec="minutes") if d.typ is Typ.UHRZEIT else wert.isoformat()
    return str(wert)


def feldname(schluessel):
    return "e_" + schluessel.replace(".", "__")


def felder(daten=None, fehler=None):
    """Gruppen ``[(titel, modul, [feld, ...])]``; mit ``daten`` (POST) werden Eingaben gezeigt."""
    fehler = fehler or {}
    gruppen = defaultdict(list)
    for schluessel in schluessel_der_uebersicht():
        d = einstellungen.definition(schluessel)
        aktuell = _aktuell(d)
        name = feldname(schluessel)
        art = _art(d)
        if daten is not None:
            wert = ("on" if daten.get(name) else "") if art == "bool" else daten.get(name, "")
        else:
            wert = _als_text(d, aktuell)
        gruppen[d.modul].append(
            {
                "name": name,
                "definition": d,
                "art": art,
                "wert": wert,
                "angehakt": bool(wert) if art == "bool" else False,
                "auswahl": [str(a) for a in d.auswahl] if d.auswahl else [],
                "fehler": fehler.get(schluessel, ""),
                "fehlt": aktuell is None,
            }
        )
    return [
        (MODUL_TITEL.get(modul, modul.capitalize()), modul, liste)
        for modul, liste in sorted(gruppen.items())
    ]


def _grund(exc):
    treffer = re.search(r"\((.*)\)$", str(exc))
    return treffer.group(1) if treffer else str(exc)


def _lesen(d, roh):
    """Eingabetext -> Python-Wert. Wirft ``ValueError`` mit deutscher Meldung."""
    art = _art(d)
    if art == "bool":
        return roh == "on"
    roh = (roh or "").strip()
    if d.typ is Typ.LISTE:
        eintraege = [e.strip() for e in TRENNER.split(roh) if e.strip()]
        if d.element_typ is Typ.GANZZAHL:
            try:
                return [int(e) for e in eintraege]
            except ValueError:
                raise ValueError("Ganze Zahlen erwartet") from None
        return eintraege
    if d.typ is Typ.GANZZAHL:
        if not roh:
            raise ValueError("Bitte ausfüllen")
        try:
            return int(roh)
        except ValueError:
            raise ValueError("Ganze Zahl erwartet") from None
    if not roh and d.typ is not Typ.TEXT:
        raise ValueError("Bitte ausfüllen")
    return roh


def pruefen(daten):
    """Liest und validiert alle Felder. Gibt ``(aenderungen, fehler)`` zurück: ``aenderungen``
    = ``{schluessel: wert}`` nur für Geändertes, ``fehler`` = ``{schluessel: meldung}``."""
    aenderungen, fehler = {}, {}
    for schluessel in schluessel_der_uebersicht():
        d = einstellungen.definition(schluessel)
        try:
            wert = _lesen(d, daten.get(feldname(schluessel), ""))
            json_wert = d.pruefen(wert)
        except einstellungen.UngueltigerWert as exc:
            fehler[schluessel] = _grund(exc)
            continue
        except ValueError as exc:
            fehler[schluessel] = str(exc)
            continue
        aktuell = _aktuell(d)
        if aktuell is None or d.pruefen(aktuell) != json_wert:
            aenderungen[schluessel] = wert
    return aenderungen, fehler
