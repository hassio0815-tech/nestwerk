"""Schrittfolge des Assistenten: sieben feste Schritte, danach die von Modulen registrierten
optionalen Schritte (``kern.registry.einrichtung_registrieren``), zuletzt der Abschluss.

Die Nummern ergeben sich aus der Position. Ohne registrierte Schritte ist der Abschluss Schritt 8.
"""

from apps.kern import registry

KERN_ANZAHL = 7  # Willkommen bis Startwerte


def erweiterungen():
    return registry.einrichtungsschritte()


def letzter():
    """Nummer des Abschluss-Schritts."""
    return KERN_ANZAHL + len(erweiterungen()) + 1


def erweiterung(nr):
    """Der registrierte Schritt mit dieser Nummer oder ``None`` (fester Schritt oder Abschluss)."""
    index = nr - KERN_ANZAHL - 1
    schritte = erweiterungen()
    return schritte[index] if 0 <= index < len(schritte) else None
