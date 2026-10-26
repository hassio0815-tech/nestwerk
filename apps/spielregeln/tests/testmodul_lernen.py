"""Test-Modul "Lernen" (AP23-Beweis): registriert eigene Metriken nur über ``kern.registry`` –
genau so, wie es später ``lernen``/``forschen``/``avatar`` (AP26 ``ausbaustufe``) tun. Die Engine in
``spielregeln`` wird dafür nicht geändert.

Werte kommen aus ``WERTE`` (je Kind-PK), damit Tests sie gezielt setzen können.
"""

from contextlib import contextmanager

from apps.kern import registry
from apps.kern.registry import Metrik, Provider

MODUL = "lernen_test"
WERTE: dict[tuple[str, int], object] = {}


def setzen(metrik, kind, wert):
    WERTE[(metrik, kind.pk)] = wert


def _wert(metrik):
    return lambda kind: WERTE.get((metrik, kind.pk), 0)


def _bereiche(metrik):
    return lambda kind: WERTE.get((f"{metrik}.bereiche", kind.pk), {})


def registrieren():
    for schluessel, bezeichnung in (
        ("lernen_test.vokabeln", "Vokabeln gelernt"),
        ("lernen_test.stufe", "Teststufe"),
        ("lernen_test.ausbaustufe", "Test-Ausbaustufe"),
    ):
        registry.metrik_registrieren(Metrik(schluessel, MODUL, bezeichnung))
        registry.provider_registrieren(
            Provider(f"metrik.{schluessel}", MODUL, bezeichnung, _wert(schluessel))
        )
    # Metrik mit Bereichen (z. B. Ausbaustufe je Seltenheit)
    registry.provider_registrieren(
        Provider(
            "metrik.lernen_test.ausbaustufe.bereiche",
            MODUL,
            "Ausbaustufe je Seltenheit",
            _bereiche("lernen_test.ausbaustufe"),
        )
    )


@contextmanager
def aktiv():
    """Registriert das Test-Modul und entfernt es danach wieder."""
    with registry.metrik_verzeichnis.isoliert(), registry.provider_verzeichnis.isoliert():
        WERTE.clear()
        registrieren()
        try:
            yield
        finally:
            WERTE.clear()
