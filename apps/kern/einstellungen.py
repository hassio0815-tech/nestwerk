"""Einstellungen: typisierte Definitionen im Code, Werte nur in der DB (ARCHITECTURE 1).

- Jede App deklariert ihre Einstellungen mit ``definieren(...)`` (in ``AppConfig.ready()``).
- ``wert(schluessel)`` liest aus der DB. Fehlt der Wert, gibt es **keinen Code-Default**,
  sondern ``EinstellungFehlt``. Startwerte kommen per Datenmigration (``startwerte_schreiben``).
- ``setzen(...)`` validiert gegen die Definition und protokolliert im Audit-Log.
"""

import re
import zoneinfo
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction

from . import audit
from .models import Einstellung
from .registry import Verzeichnis

SCHLUESSEL_MUSTER = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class EinstellungFehler(Exception):
    """Basis aller Einstellungsfehler."""


class UnbekannteEinstellung(EinstellungFehler, LookupError):
    """Schlüssel ist nicht deklariert."""


class EinstellungFehlt(EinstellungFehler):
    """Deklariert, aber ohne Wert in der DB (Seed/Datenmigration oder Assistent fehlt)."""


class UngueltigerWert(EinstellungFehler, ValueError):
    """Wert passt nicht zur Definition."""


class Typ(StrEnum):
    GANZZAHL = "ganzzahl"
    BOOL = "bool"
    TEXT = "text"
    DATUM = "datum"  # gespeichert als "JJJJ-MM-TT", gelesen als date
    UHRZEIT = "uhrzeit"  # gespeichert als "HH:MM", gelesen als time
    ZEITZONE = "zeitzone"  # IANA-Name, gelesen als str
    LISTE = "liste"  # Elemente vom Typ ``element_typ``


@dataclass(frozen=True)
class Definition:
    schluessel: str
    typ: Typ
    bezeichnung: str
    beschreibung: str = ""
    einheit: str = ""
    minimum: int | None = None  # GANZZAHL (auch für Listen-Elemente)
    maximum: int | None = None
    max_laenge: int = 200  # TEXT
    auswahl: tuple | None = None  # erlaubte Werte (TEXT, GANZZAHL; bei LISTE je Element)
    element_typ: Typ | None = None  # nur LISTE
    validatoren: tuple[Callable[[Any], None], ...] = ()  # erhalten den gelesenen Wert
    # Technischer Zustand (z. B. Fortschritt des Einrichtungs-Assistenten): kein Familienwert,
    # erscheint nicht im Einstellungen-Editor (Review AP19, B-08)
    intern: bool = False

    @property
    def modul(self):
        return self.schluessel.split(".", 1)[0]

    def pruefen(self, wert):
        """Validiert ``wert`` (Python- oder JSON-Form) und liefert die JSON-Form."""
        if self.typ is Typ.LISTE:
            if not isinstance(wert, list | tuple):
                raise self._fehler(wert, "Liste erwartet")
            json_wert = [self._einzeln(self.element_typ, e) for e in wert]
        else:
            json_wert = self._einzeln(self.typ, wert)
        gelesen = self.lesen(json_wert, geprueft=True)
        for validator in self.validatoren:
            try:
                validator(gelesen)
            except (ValidationError, ValueError) as exc:
                raise self._fehler(wert, str(exc)) from exc
        return json_wert

    def lesen(self, json_wert, *, geprueft=False):
        """JSON-Form -> Python-Wert. Ungeprüfte Werte (aus der DB) werden erst validiert."""
        if not geprueft:
            json_wert = self.pruefen(json_wert)
        if self.typ is Typ.LISTE:
            return [_umwandeln(self.element_typ, e) for e in json_wert]
        return _umwandeln(self.typ, json_wert)

    def _einzeln(self, typ, wert):
        match typ:
            case Typ.GANZZAHL:
                if isinstance(wert, bool) or not isinstance(wert, int):
                    raise self._fehler(wert, "Ganzzahl erwartet")
                if self.minimum is not None and wert < self.minimum:
                    raise self._fehler(wert, f"kleiner als Minimum {self.minimum}")
                if self.maximum is not None and wert > self.maximum:
                    raise self._fehler(wert, f"größer als Maximum {self.maximum}")
                json_wert = wert
            case Typ.BOOL:
                if not isinstance(wert, bool):
                    raise self._fehler(wert, "Ja/Nein erwartet")
                json_wert = wert
            case Typ.TEXT:
                if not isinstance(wert, str):
                    raise self._fehler(wert, "Text erwartet")
                if len(wert) > self.max_laenge:
                    raise self._fehler(wert, f"länger als {self.max_laenge} Zeichen")
                json_wert = wert
            case Typ.DATUM:
                if isinstance(wert, datetime) or not isinstance(wert, date | str):
                    raise self._fehler(wert, "Datum erwartet")
                if isinstance(wert, str):
                    try:
                        wert = date.fromisoformat(wert)
                    except ValueError:
                        raise self._fehler(wert, "Datum im Format JJJJ-MM-TT erwartet") from None
                json_wert = wert.isoformat()
            case Typ.UHRZEIT:
                if isinstance(wert, str):
                    if not re.fullmatch(r"\d{2}:\d{2}", wert):
                        raise self._fehler(wert, "Uhrzeit im Format HH:MM erwartet")
                    try:
                        wert = time.fromisoformat(wert)
                    except ValueError:
                        raise self._fehler(wert, "ungültige Uhrzeit") from None
                if not isinstance(wert, time) or wert.tzinfo is not None:
                    raise self._fehler(wert, "Uhrzeit ohne Zeitzone erwartet")
                if wert.second or wert.microsecond:
                    raise self._fehler(wert, "Uhrzeit nur minutengenau")
                json_wert = wert.strftime("%H:%M")
            case Typ.ZEITZONE:
                if not isinstance(wert, str) or wert not in _zeitzonen():
                    raise self._fehler(wert, "unbekannte Zeitzone")
                json_wert = wert
            case _:
                raise ImproperlyConfigured(f"{self.schluessel}: Typ {typ} nicht als Element")
        if self.auswahl is not None and json_wert not in self.auswahl:
            raise self._fehler(wert, f"nicht in Auswahl {list(self.auswahl)}")
        return json_wert

    def _fehler(self, wert, grund):
        return UngueltigerWert(f"Einstellung '{self.schluessel}': {wert!r} ungültig ({grund})")


def _umwandeln(typ, json_wert):
    match typ:
        case Typ.DATUM:
            return date.fromisoformat(json_wert)
        case Typ.UHRZEIT:
            return time.fromisoformat(json_wert)
        case _:
            return json_wert


_zeitzonen_cache = None


def _zeitzonen():
    global _zeitzonen_cache
    if _zeitzonen_cache is None:
        _zeitzonen_cache = frozenset(zoneinfo.available_timezones())
    return _zeitzonen_cache


verzeichnis = Verzeichnis("Einstellung")


def definieren(schluessel, typ, bezeichnung, **optionen):
    """Deklariert eine Einstellung. Kein Default-Wert: Startwerte nur per Datenmigration."""
    if not SCHLUESSEL_MUSTER.match(schluessel) or len(schluessel) > 100:
        raise ImproperlyConfigured(f"Ungültiger Einstellungs-Schlüssel '{schluessel}'")
    typ = Typ(typ)
    element_typ = optionen.get("element_typ")
    if typ is Typ.LISTE:
        if element_typ is None or Typ(element_typ) is Typ.LISTE:
            raise ImproperlyConfigured(f"{schluessel}: LISTE braucht element_typ (keine Liste)")
        optionen["element_typ"] = Typ(element_typ)
    elif element_typ is not None:
        raise ImproperlyConfigured(f"{schluessel}: element_typ nur bei LISTE")
    if "auswahl" in optionen and optionen["auswahl"] is not None:
        optionen["auswahl"] = tuple(optionen["auswahl"])
    optionen["validatoren"] = tuple(optionen.get("validatoren", ()))
    definition = Definition(schluessel=schluessel, typ=typ, bezeichnung=bezeichnung, **optionen)
    if len(definition.modul) > 40:
        raise ImproperlyConfigured(f"{schluessel}: Modulname zu lang")
    return verzeichnis.registrieren(schluessel, definition)


def definition(schluessel):
    try:
        return verzeichnis.holen(schluessel)
    except LookupError:
        raise UnbekannteEinstellung(f"Einstellung '{schluessel}' ist nicht deklariert") from None


def definitionen(modul=None):
    """Alle Definitionen (für den Einstellungen-Editor), sortiert nach Schlüssel."""
    alle = verzeichnis.alle()
    if modul is not None:
        alle = [d for d in alle if d.modul == modul]
    return sorted(alle, key=lambda d: d.schluessel)


def wert(schluessel):
    """Aktueller Wert aus der DB. Kein Wert -> ``EinstellungFehlt`` (kein Code-Default)."""
    return werte(schluessel)[schluessel]


def werte(*schluessel):
    """Mehrere Werte mit einer Abfrage: ``{schluessel: wert}``."""
    defs = {s: definition(s) for s in schluessel}
    zeilen = dict(Einstellung.objects.filter(schluessel__in=defs).values_list("schluessel", "wert"))
    fehlend = [s for s in schluessel if s not in zeilen]
    if fehlend:
        raise EinstellungFehlt(
            f"Einstellung(en) ohne Wert in der DB: {', '.join(fehlend)} "
            "(Startwert per Datenmigration oder im Eltern-Dashboard setzen)"
        )
    return {s: d.lesen(zeilen[s]) for s, d in defs.items()}


def gespeicherte_werte():
    """Alle gespeicherten Werte in JSON-Form ``{schluessel: wert}`` (Einstellungen-Editor)."""
    return dict(Einstellung.objects.values_list("schluessel", "wert"))


def fehlende():
    """Deklarierte Schlüssel ohne DB-Wert (Systemstatus, Einrichtungs-Assistent)."""
    vorhanden = set(Einstellung.objects.values_list("schluessel", flat=True))
    return sorted(d.schluessel for d in verzeichnis.alle() if d.schluessel not in vorhanden)


def setzen(schluessel, neuer_wert, *, akteur=audit.AKTUELL):
    """Validiert und speichert einen Wert; Änderung wird im Audit-Log protokolliert.

    ``akteur``: Standard = angemeldeter Benutzer der Anfrage, ``None`` = System.

    Gibt den gespeicherten Wert in Python-Form zurück.
    """
    d = definition(schluessel)
    json_wert = d.pruefen(neuer_wert)
    if akteur is audit.AKTUELL:
        akteur = audit.aktueller_akteur()
    with transaction.atomic():
        zeile = Einstellung.objects.filter(schluessel=schluessel).first()
        if zeile is None or zeile.wert != json_wert:
            Einstellung.objects.update_or_create(
                schluessel=schluessel,
                defaults={
                    "wert": json_wert,
                    "modul": d.modul,
                    "geaendert_von": akteur if getattr(akteur, "pk", None) else None,
                },
            )
            audit.protokollieren(
                "einstellung.geaendert",
                akteur=akteur,
                objekt_typ="kern.einstellung",
                objekt_id=schluessel,
                details={"alt": zeile.wert if zeile else None, "neu": json_wert},
            )
    return d.lesen(json_wert, geprueft=True)


def startwerte_schreiben(einstellung_modell, startwerte):
    """Für Datenmigrationen: legt fehlende Werte an, überschreibt nie bestehende.

    ``einstellung_modell`` = historisches Modell (``apps.get_model("kern", "Einstellung")``).
    Jeder Schlüssel muss deklariert sein und wird gegen seine Definition validiert.
    """
    for schluessel, startwert in startwerte.items():
        d = definition(schluessel)
        einstellung_modell.objects.get_or_create(
            schluessel=schluessel, defaults={"wert": d.pruefen(startwert), "modul": d.modul}
        )


def kern_einstellungen_definieren():
    """Einstellungen, die kern selbst braucht (Gruppe ``allgemein``, DATA_MODEL 15.2)."""
    definieren("allgemein.anzeigename", Typ.TEXT, "Name der Installation", max_laenge=40)
    definieren(
        "allgemein.zeitzone",
        Typ.ZEITZONE,
        "Zeitzone",
        beschreibung="Fachliche Tage und Wochen werden in dieser Zeitzone gerechnet.",
    )
    definieren(
        "allgemein.go_live_datum",
        Typ.DATUM,
        "Go-live-Datum",
        beschreibung="Beginn des ersten App-Jahres.",
    )
    definieren("allgemein.sprache", Typ.TEXT, "Sprache", auswahl=("de",))
    definieren(
        "allgemein.joblauf_aufbewahrung_tage",
        Typ.GANZZAHL,
        "Aufbewahrung der Job-Läufe",
        beschreibung="Protokoll der geplanten Jobs (Systemstatus) wird danach gelöscht.",
        einheit="Tage",
        minimum=7,
        maximum=3650,
    )
    definieren(
        "allgemein.einrichtung_abgeschlossen", Typ.BOOL, "Einrichtung abgeschlossen", intern=True
    )
