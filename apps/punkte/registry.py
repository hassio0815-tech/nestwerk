"""Erweiterungspunkt: Reservierungs-Provider für das verfügbare Guthaben (DATA_MODEL 3.1).

Module, die Guthaben vormerken (z. B. ``belohnung``: offene Einlöseanträge, AP15),
registrieren in ``AppConfig.ready()``:

    reservierung_registrieren("belohnung.offene_antraege", offene_antraege, modul="belohnung")

``funktion(kind) -> int`` liefert die reservierten Punkte (>= 0) des Kindes. punkte kennt die
registrierenden Module nicht (Schichtenregel), es fragt nur dieses Verzeichnis.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from django.core.exceptions import ImproperlyConfigured

from apps.kern.registry import Verzeichnis

__all__ = ["Reservierung", "isoliert", "reservierung_registrieren", "reservierungen"]


@dataclass(frozen=True)
class Reservierung:
    schluessel: str
    modul: str
    funktion: Callable[[object], int] = field(repr=False)


reservierung_verzeichnis = Verzeichnis("Reservierungs-Provider")


def reservierung_registrieren(schluessel, funktion, *, modul):
    if not callable(funktion):
        raise ImproperlyConfigured(f"Reservierungs-Provider '{schluessel}' ist nicht aufrufbar")
    return reservierung_verzeichnis.registrieren(
        schluessel, Reservierung(schluessel=schluessel, modul=modul, funktion=funktion)
    )


def reservierungen():
    return sorted(reservierung_verzeichnis.alle(), key=lambda r: r.schluessel)


def isoliert():
    """Für Tests: Registrierungen werden danach zurückgesetzt."""
    return reservierung_verzeichnis.isoliert()
