"""Humorvolle Wappen für Eltern (fester Katalog). Reine Daten, keine Geschlechter-Zuordnung."""

import random
from dataclasses import dataclass

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Wappen:
    schluessel: str
    emoji: str
    titel: str
    spruch: str


KATALOG = (
    Wappen("hausdrache", "🐉", _("Hausdrache"), _("Bewacht den Kühlschrank")),
    Wappen("rudelchef", "🦁", _("Rudelchef"), _("Hat das letzte Wort … meistens")),
    Wappen("kuechenchef", "🍳", _("Küchenchef"), _("Heute gibt's, was auf den Tisch kommt")),
    Wappen("familientaxi", "🚕", _("Familien-Taxi"), _("24/7 im Einsatz")),
    Wappen("bank", "🏦", _("Bank of Mama/Papa"), _("Kein Dispo!")),
    Wappen("grillmeister", "🔥", _("Grillmeister"), _("Fasst die Zange nicht ab")),
    Wappen("nachteule", "🦉", _("Nachteule"), _("Sieht alles, auch nach 22 Uhr")),
    Wappen("sockenfinder", "🧦", _("Sockenfinder"), _("Kennt jeden verlorenen Socken")),
    Wappen("burgherr", "🛡️", _("Burgherr/Burgfrau"), _("Hüter des Nests")),
)
NACH_SCHLUESSEL = {w.schluessel: w for w in KATALOG}
CHOICES = [(w.schluessel, format_lazy("{} {}", w.emoji, w.titel)) for w in KATALOG]


def info(schluessel):
    return NACH_SCHLUESSEL.get(schluessel)


def zufaellig(belegt=()):
    """Zufälliges Wappen, möglichst eines, das andere Eltern nicht schon haben."""
    frei = [w for w in KATALOG if w.schluessel not in set(belegt)]
    return random.choice(frei or KATALOG).schluessel
