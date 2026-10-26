"""Zentrale Umgebungsvariablen-Auflösung (Präfix ``NESTWERK_``).

Der frühere Projektname war FamKo. Bestehende Installationen setzen weiterhin ``FAMKO_*`` in
ihrer ``.env``; diese Namen bleiben als Fallback gültig. ``NESTWERK_*`` hat Vorrang.
Reines Standardbibliotheks-Modul (auch von den Settings vor dem App-Start importierbar).
"""

import os

PRAEFIX = "NESTWERK_"
ALTER_PRAEFIX = "FAMKO_"  # nur Kompatibilität mit bestehenden Installationen


def umgebung(name, default=None):
    """Wert von ``NESTWERK_<name>``, sonst ``FAMKO_<name>``, sonst ``default``.

    Eine gesetzte, aber leere neue Variable zählt als gesetzt (überschreibt bewusst den alten Wert).
    """
    neu = os.environ.get(PRAEFIX + name)
    if neu is not None:
        return neu
    return os.environ.get(ALTER_PRAEFIX + name, default)
