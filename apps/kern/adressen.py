"""Öffentliche Basis-Adresse der App (für Links in Mails und Push).

Maßgeblich ist die Einstellung ``einrichtung.basis_url`` (im Assistenten und im
Eltern-Dashboard änderbar); fehlt sie oder ist leer, gilt ``settings.BASIS_URL``."""

from django.conf import settings

from . import einstellungen

SCHLUESSEL = "einrichtung.basis_url"


def basis_url():
    """Basis-URL ohne abschließenden Schrägstrich; leer, wenn nichts konfiguriert ist."""
    try:
        db_wert = einstellungen.wert(SCHLUESSEL)
    except einstellungen.EinstellungFehler:
        db_wert = ""
    wert = (db_wert or "").strip() or (getattr(settings, "BASIS_URL", "") or "").strip()
    return wert.rstrip("/")
