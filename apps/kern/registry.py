"""Modul-Registry: Erweiterungspunkte für Kacheln, Metriken und Fortschritts-Provider.

Module registrieren in ``AppConfig.ready()`` (über ihr ``registry.py``). Andere Module fragen
nur die Registry, nie das registrierende Modul direkt (ARCHITECTURE 2.2/2.3).
"""

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ImproperlyConfigured


class UnbekannterEintrag(LookupError):
    """Schlüssel ist nicht registriert."""


class Verzeichnis:
    """Schlüssel -> Eintrag. Doppelte Registrierung ist ein Konfigurationsfehler."""

    def __init__(self, art):
        self.art = art
        self._eintraege = {}

    def registrieren(self, schluessel, eintrag):
        if schluessel in self._eintraege:
            raise ImproperlyConfigured(f"{self.art} '{schluessel}' ist doppelt registriert")
        self._eintraege[schluessel] = eintrag
        return eintrag

    def holen(self, schluessel):
        try:
            return self._eintraege[schluessel]
        except KeyError:
            raise UnbekannterEintrag(f"{self.art} '{schluessel}' ist nicht registriert") from None

    def __contains__(self, schluessel):
        return schluessel in self._eintraege

    def alle(self):
        return list(self._eintraege.values())

    @contextmanager
    def isoliert(self):
        """Für Tests: Änderungen am Verzeichnis werden danach zurückgesetzt."""
        stand = dict(self._eintraege)
        try:
            yield self
        finally:
            self._eintraege = stand


# --- Kacheln ---------------------------------------------------------------------------------

KIND = "kind"
ELTERN = "eltern"
TABLET = "tablet"
ZIELGRUPPEN = frozenset({KIND, ELTERN, TABLET})


@dataclass(frozen=True)
class Kachel:
    """Dashboard-Kachel. ``kontext(request) -> dict`` liefert die Template-Daten,
    ``sichtbar(request) -> bool`` blendet sie situativ aus."""

    schluessel: str
    modul: str
    titel: str
    template: str
    zielgruppen: frozenset[str]
    kontext: Callable[[Any], dict] | None = None
    sichtbar: Callable[[Any], bool] | None = None
    reihenfolge: int = 100

    def __post_init__(self):
        object.__setattr__(self, "zielgruppen", frozenset(self.zielgruppen))
        if not self.zielgruppen or not self.zielgruppen <= ZIELGRUPPEN:
            raise ImproperlyConfigured(
                f"Kachel '{self.schluessel}': Zielgruppen müssen aus {sorted(ZIELGRUPPEN)} sein"
            )


kachel_verzeichnis = Verzeichnis("Kachel")


def kachel_registrieren(kachel):
    return kachel_verzeichnis.registrieren(kachel.schluessel, kachel)


def kacheln(zielgruppe):
    """Kacheln einer Zielgruppe, sortiert nach Reihenfolge und Schlüssel."""
    if zielgruppe not in ZIELGRUPPEN:
        raise ValueError(f"Unbekannte Zielgruppe '{zielgruppe}'")
    treffer = [k for k in kachel_verzeichnis.alle() if zielgruppe in k.zielgruppen]
    return sorted(treffer, key=lambda k: (k.reihenfolge, k.schluessel))


# --- Metriken --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Metrik:
    """Katalog-Eintrag einer Metrik (z. B. ``avatar.ausbaustufe_voll``), auf die Regeln
    (Meilensteine, Abzeichen) verweisen können."""

    schluessel: str
    modul: str
    bezeichnung: str
    beschreibung: str = ""
    einheit: str = ""


metrik_verzeichnis = Verzeichnis("Metrik")


def metrik_registrieren(metrik):
    return metrik_verzeichnis.registrieren(metrik.schluessel, metrik)


def metrik(schluessel):
    return metrik_verzeichnis.holen(schluessel)


def metriken(modul=None):
    alle = metrik_verzeichnis.alle()
    if modul is not None:
        alle = [m for m in alle if m.modul == modul]
    return sorted(alle, key=lambda m: m.schluessel)


# --- Fortschritts-Provider -------------------------------------------------------------------


@dataclass(frozen=True)
class Provider:
    """Liefert Fortschritt für andere Module, z. B. ``avatar.ausbaustufe_fortschritt(kind)``."""

    schluessel: str
    modul: str
    bezeichnung: str
    funktion: Callable[..., Any] = field(repr=False)


provider_verzeichnis = Verzeichnis("Provider")


def provider_registrieren(provider):
    return provider_verzeichnis.registrieren(provider.schluessel, provider)


def provider_vorhanden(schluessel):
    return schluessel in provider_verzeichnis


def fortschritt(schluessel, *args, **kwargs):
    """Ruft den Provider ``schluessel`` auf. Unbekannt -> ``UnbekannterEintrag``."""
    return provider_verzeichnis.holen(schluessel).funktion(*args, **kwargs)


@contextmanager
def isoliert():
    """Für Tests: Kacheln, Metriken und Provider sind darin zunächst leer (ohne die von Apps
    in ``ready()`` registrierten) und werden danach wiederhergestellt."""
    verzeichnisse = (kachel_verzeichnis, metrik_verzeichnis, provider_verzeichnis)
    staende = [dict(v._eintraege) for v in verzeichnisse]
    for v in verzeichnisse:
        v._eintraege = {}
    try:
        yield
    finally:
        for v, stand in zip(verzeichnisse, staende, strict=True):
            v._eintraege = stand
