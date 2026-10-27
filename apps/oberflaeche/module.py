"""Modul-Launcher: datengetriebene Liste der Bereiche, die nach der Anmeldung zur Wahl stehen.

Ein neues Modul (z. B. Lernen) fügt nur einen Eintrag in ``MODULE`` hinzu. Einträge, deren
URL-Name (noch) nicht existiert, werden ausgelassen."""

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.konten.models import Rolle


@dataclass(frozen=True)
class Modul:
    schluessel: str
    name: str
    kurz: str
    icon: str  # Name aus dem Symbol-Sprite (komponenten/_sprite.html)
    url_name: str
    rollen: tuple = (Rolle.ELTERN,)


MODULE = (
    Modul(
        "aufgaben",
        _("Aufgaben & Belohnungen"),
        _("Meldungen prüfen, Wochenplan und Aufgaben"),
        "stern",
        "aufgaben:entscheidungen",
    ),
    Modul(
        "eltern",
        _("Eltern-Bereich"),
        _("Übersicht, Ranking und Familienziel"),
        "home",
        "oberflaeche:eltern_heim",
    ),
    Modul(
        "dungeon",
        _("Dungeon"),
        _("Ränge, Mods, Abzeichen und Sondertage der Kinder"),
        "pokal",
        "oberflaeche:eltern_dungeon",
    ),
    Modul(
        "familie",
        _("Familie"),
        _("Kinder, Eltern und Passwort"),
        "person",
        "oberflaeche:familie",
    ),
    Modul(
        "einstellungen",
        _("Einstellungen"),
        _("Regeln, Darstellung und Benachrichtigungen"),
        "einstellungen",
        "oberflaeche:einstellungen",
    ),
    # Künftig z. B.: Modul("lernen", "Lernen", "Üben und Entdecken", "schule", "lernen:start"),
)


def fuer(user):
    """Module, die ``user`` sehen darf, mit aufgelöster URL."""
    ergebnis = []
    for modul in MODULE:
        if user.rolle not in modul.rollen:
            continue
        if modul.schluessel == "dungeon" and not getattr(user, "dungeon_anzeigen", True):
            continue
        try:
            url = reverse(modul.url_name)
        except NoReverseMatch:
            continue
        ergebnis.append({"modul": modul, "url": url})
    return ergebnis
