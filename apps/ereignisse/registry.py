"""Code-Katalog der Ereignistypen und Handler (ARCHITECTURE 5.1).

Apps deklarieren in ``AppConfig.ready()`` (üblich: über ihr ``events.py``):

    typ_deklarieren("aufgabe.gemeldet", modul="aufgaben", bezeichnung="Aufgabe gemeldet",
                    zielgruppe="eltern", standard_kanaele=["push", "email"])
    handler_registrieren("aufgabe.gemeldet", benachrichtigen)            # asynchron (Worker)
    handler_registrieren("aktivitaet.erfasst", abzeichen_pruefen, synchron=True)

- Asynchrone Handler laufen im Worker, je Ereignis genau einmal wirksam (eigene DB-Transaktion,
  zusammen mit dem Statuswechsel). Kein Netzwerk-I/O im Handler: Versand über eigene
  Zustell-Zeilen (benachrichtigung).
- Synchrone Handler laufen in ``veroeffentlichen`` in der Transaktion des Aufrufers (sparsam).
- Der Handler-Name (Standard ``modul.funktion``) wird in ``EreignisVerarbeitung`` gespeichert und
  muss stabil bleiben.
"""

import re
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from apps.kern.registry import UnbekannterEintrag, Verzeichnis

from .models import Zielgruppe

SLUG_MUSTER = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

__all__ = [
    "EreignisTypDefinition",
    "Handler",
    "UnbekannterEintrag",
    "alle_typen_handler_registrieren",
    "handler_fuer",
    "handler_registrieren",
    "nachlauf_registrieren",
    "nachlaeufe",
    "isoliert",
    "typ",
    "typ_deklarieren",
    "typen",
]


@dataclass(frozen=True)
class EreignisTypDefinition:
    slug: str
    modul: str
    bezeichnung: str
    zielgruppe: str
    standard_kanaele: tuple[str, ...] = ()
    deep_link_muster: str = ""
    push_ttl_sekunden: int = 86400
    entscheidung: bool = False  # Eltern müssen entscheiden (Profil "Mail nur bei Entscheidungen")


@dataclass(frozen=True)
class Handler:
    name: str
    typ: str
    funktion: Callable[[Any], Any] = field(repr=False)
    synchron: bool = False


typ_verzeichnis = Verzeichnis("Ereignistyp")
handler_verzeichnis = Verzeichnis("Ereignis-Handler")


def typ_deklarieren(
    slug,
    *,
    modul,
    bezeichnung,
    zielgruppe,
    standard_kanaele=(),
    deep_link_muster="",
    push_ttl_sekunden=86400,
    entscheidung=False,
):
    """Deklariert einen Ereignistyp (Startwerte für die DB-Zeile ``EreignisTyp``).

    ``entscheidung=True``: Eltern müssen etwas entscheiden (z. B. Meldung, Antrag); nur im Code
    definiert, nicht in der DB.
    """
    if not SLUG_MUSTER.match(slug) or len(slug) > 80:
        raise ImproperlyConfigured(f"Ungültiger Ereignistyp '{slug}' (Format 'bereich.ereignis')")
    if zielgruppe not in Zielgruppe.values:
        raise ImproperlyConfigured(f"Ereignistyp '{slug}': unbekannte Zielgruppe '{zielgruppe}'")
    if not modul or len(modul) > 40 or len(bezeichnung) > 120 or len(deep_link_muster) > 200:
        raise ImproperlyConfigured(f"Ereignistyp '{slug}': Feld zu lang oder leer")
    if isinstance(standard_kanaele, str) or not all(isinstance(k, str) for k in standard_kanaele):
        raise ImproperlyConfigured(f"Ereignistyp '{slug}': standard_kanaele muss Liste sein")
    if not isinstance(push_ttl_sekunden, int) or push_ttl_sekunden <= 0:
        raise ImproperlyConfigured(f"Ereignistyp '{slug}': push_ttl_sekunden > 0 erwartet")
    definition = EreignisTypDefinition(
        slug=slug,
        modul=modul,
        bezeichnung=bezeichnung,
        zielgruppe=str(zielgruppe),
        standard_kanaele=tuple(standard_kanaele),
        deep_link_muster=deep_link_muster,
        push_ttl_sekunden=push_ttl_sekunden,
        entscheidung=bool(entscheidung),
    )
    return typ_verzeichnis.registrieren(slug, definition)


def typ(slug):
    """Definition eines Typs. Unbekannt -> ``UnbekannterEintrag``."""
    return typ_verzeichnis.holen(slug)


def typen(modul=None):
    alle = typ_verzeichnis.alle()
    if modul is not None:
        alle = [t for t in alle if t.modul == modul]
    return sorted(alle, key=lambda t: t.slug)


def handler_registrieren(typ_slug, funktion, *, name=None, synchron=False):
    """Registriert ``funktion(ereignis)`` für einen deklarierten Typ.

    ``name`` muss global eindeutig und stabil sein (Standard: ``modul.funktion``).
    """
    if typ_slug not in typ_verzeichnis:
        raise ImproperlyConfigured(
            f"Handler für unbekannten Ereignistyp '{typ_slug}' (erst typ_deklarieren)"
        )
    if not callable(funktion):
        raise ImproperlyConfigured("Handler muss aufrufbar sein")
    name = name or f"{funktion.__module__}.{funktion.__qualname__}"
    if len(name) > 100:
        raise ImproperlyConfigured(f"Handler-Name zu lang (max. 100): {name}")
    handler = Handler(name=name, typ=typ_slug, funktion=funktion, synchron=synchron)
    return handler_verzeichnis.registrieren((typ_slug, name), handler)


ALLE_TYPEN = "*"


def alle_typen_handler_registrieren(funktion, *, name, synchron=False):
    """Handler für **alle** Ereignistypen (auch später deklarierte), z. B. den Router von
    ``benachrichtigung``. ``name`` ist Pflicht, global eindeutig und stabil."""
    if not callable(funktion):
        raise ImproperlyConfigured("Handler muss aufrufbar sein")
    if len(name) > 100:
        raise ImproperlyConfigured(f"Handler-Name zu lang (max. 100): {name}")
    eintrag = Handler(name=name, typ=ALLE_TYPEN, funktion=funktion, synchron=synchron)
    return handler_verzeichnis.registrieren((ALLE_TYPEN, name), eintrag)


def handler_fuer(typ_slug, *, synchron):
    """Registrierte Handler eines Typs inkl. der Handler für alle Typen (sortiert nach Name)."""
    treffer = [
        h
        for h in handler_verzeichnis.alle()
        if h.typ in (typ_slug, ALLE_TYPEN) and h.synchron is synchron
    ]
    return sorted(treffer, key=lambda h: h.name)


def handler(typ_slug, name):
    """Asynchroner Handler ``name`` für ``typ_slug``. Unbekannt -> ``UnbekannterEintrag``."""
    if (ALLE_TYPEN, name) in handler_verzeichnis:
        return handler_verzeichnis.holen((ALLE_TYPEN, name))
    return handler_verzeichnis.holen((typ_slug, name))


nachlauf_verzeichnis = Verzeichnis("Worker-Nachlauf")


def nachlauf_registrieren(name, funktion):
    """Registriert ``funktion() -> int`` für jede Worker-Runde (nach den Handlern), z. B. den
    Versand fälliger Zustellungen. Rückgabe = Anzahl erledigter Einheiten (>0 = weiter ohne Pause).
    Fehler werden protokolliert und stoppen den Worker nicht."""
    if not callable(funktion):
        raise ImproperlyConfigured("Nachlauf muss aufrufbar sein")
    return nachlauf_verzeichnis.registrieren(name, (name, funktion))


def nachlaeufe():
    return sorted(nachlauf_verzeichnis.alle())


@contextmanager
def isoliert():
    """Für Tests: Typen, Handler und Nachläufe werden danach zurückgesetzt. Innerhalb ist der
    Katalog der Handler/Nachläufe leer (kein Router, keine Fremd-Handler)."""
    with (
        typ_verzeichnis.isoliert(),
        handler_verzeichnis.isoliert(),
        nachlauf_verzeichnis.isoliert(),
    ):
        handler_verzeichnis._eintraege = {}
        nachlauf_verzeichnis._eintraege = {}
        yield
