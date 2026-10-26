"""Humorvolle Wappen für Eltern (fester Katalog). Reine Daten, keine Geschlechter-Zuordnung."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Wappen:
    schluessel: str
    emoji: str
    titel: str
    spruch: str


KATALOG = (
    Wappen("hausdrache", "🐉", "Hausdrache", "Bewacht den Kühlschrank"),
    Wappen("rudelchef", "🦁", "Rudelchef", "Hat das letzte Wort … meistens"),
    Wappen("kuechenchef", "🍳", "Küchenchef", "Heute gibt's, was auf den Tisch kommt"),
    Wappen("familientaxi", "🚕", "Familien-Taxi", "24/7 im Einsatz"),
    Wappen("bank", "🏦", "Bank of Mama/Papa", "Kein Dispo!"),
    Wappen("grillmeister", "🔥", "Grillmeister", "Fasst die Zange nicht ab"),
    Wappen("nachteule", "🦉", "Nachteule", "Sieht alles, auch nach 22 Uhr"),
    Wappen("sockenfinder", "🧦", "Sockenfinder", "Kennt jeden verlorenen Socken"),
    Wappen("burgherr", "🛡️", "Burgherr/Burgfrau", "Hüter des Nests"),
)
NACH_SCHLUESSEL = {w.schluessel: w for w in KATALOG}
CHOICES = [(w.schluessel, f"{w.emoji} {w.titel}") for w in KATALOG]


def info(schluessel):
    return NACH_SCHLUESSEL.get(schluessel)


def zufaellig(belegt=()):
    """Zufälliges Wappen, möglichst eines, das andere Eltern nicht schon haben."""
    frei = [w for w in KATALOG if w.schluessel not in set(belegt)]
    return random.choice(frei or KATALOG).schluessel
