"""Einstellungen des Einrichtungs-Assistenten (Zwischenstand, kein eigenes Modell)."""

from apps.kern.einstellungen import Typ, definieren

LETZTER_SCHRITT = 8

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
        maximum=LETZTER_SCHRITT,
        intern=True,
    )
    definieren(
        "einrichtung.basis_url",
        Typ.TEXT,
        "Öffentliche Adresse (Basis-URL)",
        beschreibung="Adresse der App, z. B. https://nestwerk.example.org. "
        "Links in E-Mails und Push nutzen diesen Wert (Rückfall: Umgebungsvariable BASIS_URL).",
        max_laenge=200,
    )
    definieren(
        "einrichtung.smtp_uebersprungen",
        Typ.BOOL,
        "Einrichtung: E-Mail-Versand übersprungen",
        intern=True,
    )
