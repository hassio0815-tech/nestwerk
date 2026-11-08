"""Aktionen direkt in der Benachrichtigungs-Karte (Bestätigen, Erlauben, Ablehnen ...).

``benachrichtigung`` kennt die Fachmodule nicht (Schichten): Ein Fachmodul meldet sich beim
Start für einen Ereignistyp an (``registrieren``) und liefert

- ``zustaende(eintraege)``: je Eintrag (``Benachrichtigung`` mit ``ereignis``) ob die Sache noch
  offen ist und welche Aktionen die Karte zeigt; eine Abfrage für die ganze Liste,
- ``ausfuehren(eintrag, aktion, benutzer)``: führt die Aktion über die Services des Fachmoduls
  aus und gibt einen Hinweistext zurück. Fachliche Fehler: ``AktionFehler``.

Typen ohne Anbieter haben nur "Öffnen"; offen heißt dort "noch nicht gelesen".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.utils.translation import gettext as _


class AktionFehler(Exception):
    """Aktion nicht (mehr) möglich; ``str(fehler)`` ist ein Text für die Oberfläche."""


@dataclass(frozen=True)
class Aktion:
    slug: str
    text: str
    variante: str = "sekundaer"  # Knopfvariante: primaer | sekundaer | geist | sanft
    icon: str = ""


@dataclass(frozen=True)
class Zustand:
    offen: bool
    aktionen: tuple[Aktion, ...] = ()


@dataclass(frozen=True)
class Anbieter:
    zustaende: Callable[[list], dict]  # {benachrichtigung_pk: Zustand}
    ausfuehren: Callable[..., str]


_ANBIETER: dict[str, Anbieter] = {}


def registrieren(typ_slug: str, *, zustaende: Callable, ausfuehren: Callable) -> None:
    _ANBIETER[typ_slug] = Anbieter(zustaende=zustaende, ausfuehren=ausfuehren)


def mit_anbieter(typ_slug: str) -> bool:
    return typ_slug in _ANBIETER


def zustaende(eintraege) -> dict:
    """``{pk: Zustand}`` für alle Einträge (Typen ohne Anbieter: offen = ungelesen)."""
    je_typ: dict[str, list] = {}
    for eintrag in eintraege:
        je_typ.setdefault(eintrag.ereignis.typ_id, []).append(eintrag)
    ergebnis = {}
    for typ, gruppe in je_typ.items():
        anbieter = _ANBIETER.get(typ)
        if anbieter is None:
            for eintrag in gruppe:
                ergebnis[eintrag.pk] = Zustand(offen=eintrag.gelesen_am is None)
        else:
            ergebnis.update(anbieter.zustaende(gruppe))
    return ergebnis


def ausfuehren(eintrag, aktion_slug: str, benutzer) -> str:
    """Führt eine Aktion aus, wenn die Karte sie gerade anbietet; sonst ``AktionFehler``."""
    anbieter = _ANBIETER.get(eintrag.ereignis.typ_id)
    zustand = zustaende([eintrag])[eintrag.pk] if anbieter else None
    if (
        anbieter is None
        or not zustand.offen
        or aktion_slug not in {a.slug for a in zustand.aktionen}
    ):
        raise AktionFehler(_("Das ist nicht mehr möglich."))
    return anbieter.ausfuehren(eintrag, aktion_slug, benutzer)


def zuruecksetzen() -> None:
    """Nur für Tests."""
    _ANBIETER.clear()
