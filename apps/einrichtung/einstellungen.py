"""Einstellungen des Einrichtungs-Assistenten (Zwischenstand, kein eigenes Modell)."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

# Obergrenze des Zwischenstands (sieben feste Schritte, Modul-Schritte, Abschluss)
MAX_SCHRITT = 30

STARTWERTE = {
    "einrichtung.schritt": 1,
    "einrichtung.basis_url": "",
    "einrichtung.smtp_uebersprungen": False,
}


def einstellungen_definieren():
    definieren(
        "einrichtung.schritt",
        Typ.GANZZAHL,
        "Einrichtung: erreichter Schritt",
        beschreibung="Höchster Schritt, den der Assistent freigegeben hat (Zwischenstand).",
        minimum=1,
        maximum=MAX_SCHRITT,
        intern=True,
    )
    definieren(
        "einrichtung.basis_url",
        Typ.TEXT,
        _("Öffentliche Adresse (Basis-URL)"),
        beschreibung=_(
            "Adresse der App, z. B. https://nestwerk.example.org. "
            "Links in E-Mails und Push nutzen diesen Wert (Rückfall: Umgebungsvariable BASIS_URL)."
        ),
        max_laenge=200,
    )
    definieren(
        "einrichtung.smtp_uebersprungen",
        Typ.BOOL,
        "Einrichtung: E-Mail-Versand übersprungen",
        intern=True,
    )
