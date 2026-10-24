"""Registrierungen von avatar in ``kern.registry`` (AP26): Metriken für Abzeichen/Meilensteine
(AP23/AP27) und Dashboard-Kacheln.

Metriken (Wert je Kind, live berechnet, nur aktuelles Thema, nur fertige und schon zählende
Mods, Zeitbremse beachtet):

- ``ausbaustufe``: Ausbaustufe im aktuellen Rang (Slots mit zählendem Mod der Seltenheit = Rang).
  Bereiche ``seltenheit-<n>`` -> (zählende Slots der Seltenheit n, Rangname).
- ``ausbaustufe_seltenheit_<n>`` (n = 1..6): zählende Slots der Seltenheit n, unabhängig vom
  aktuellen Rang (K4). Für "Ausbaustufe 6 in Rang N" eine einmalige Regel je Seltenheit.
- ``godmode_aktivwochen``, ``godmode_zyklus`` und ``godmode_set_vollstaendig`` (AP27, Bereiche
  ``zyklus-K``), siehe ``godmode``.
"""

from apps.kern import registry
from apps.kern.registry import ELTERN, KIND, Kachel, Metrik, Provider

from . import godmode, kacheln, mods

MODUL = "avatar"
SELTENHEITEN = range(1, 7)


def metriken_registrieren():
    registry.metrik_registrieren(
        Metrik(
            "ausbaustufe",
            MODUL,
            "Ausbaustufe",
            beschreibung="Gebaute Slots im aktuellen Rang (aktuelles Thema, höchstens 1 neuer "
            "zählender Mod je Woche)",
            einheit="Slots",
        )
    )
    registry.provider_registrieren(
        Provider("metrik.ausbaustufe", MODUL, "Ausbaustufe", mods.metrik_ausbaustufe)
    )
    registry.provider_registrieren(
        Provider(
            "metrik.ausbaustufe.bereiche",
            MODUL,
            "Ausbaustufe je Seltenheit",
            mods.metrik_ausbaustufe_bereiche,
        )
    )
    for n in SELTENHEITEN:
        schluessel = f"ausbaustufe_seltenheit_{n}"
        registry.metrik_registrieren(
            Metrik(
                schluessel,
                MODUL,
                f"Ausbaustufe Seltenheit {n}",
                beschreibung=f"Gebaute Slots mit Mods der Seltenheit {n} (aktuelles Thema)",
                einheit="Slots",
            )
        )
        registry.provider_registrieren(
            Provider(f"metrik.{schluessel}", MODUL, schluessel, mods.metrik_seltenheit(n))
        )
    godmode_metriken_registrieren()


def godmode_metriken_registrieren():
    """AP27: God-Mode-Zyklen und Mod-Sets (Bereiche ``zyklus-K``)."""
    eintraege = (
        (
            "godmode_aktivwochen",
            "Aktive Wochen in God Mode",
            "Aktive Wochen nach der Woche des Aufstiegs in God Mode",
            "Wochen",
            godmode.metrik_aktivwochen,
            None,
        ),
        (
            "godmode_zyklus",
            "God-Mode-Zyklen",
            "Geschaffte God-Mode-Zyklen (je Zyklus die eingestellten aktiven Wochen); "
            "je Bereich zyklus-K: 1 = geschafft",
            "Zyklen",
            godmode.metrik_zyklus,
            godmode.metrik_zyklus_bereiche,
        ),
        (
            "godmode_set_vollstaendig",
            "God-Mode-Sets",
            "Vollständig gebaute God-Mode-Sets; je Bereich zyklus-K: gebaute Slots des Sets K",
            "Slots",
            godmode.metrik_set_vollstaendig,
            godmode.metrik_set_bereiche,
        ),
    )
    for schluessel, bezeichnung, beschreibung, einheit, wert, bereiche in eintraege:
        registry.metrik_registrieren(
            Metrik(schluessel, MODUL, bezeichnung, beschreibung=beschreibung, einheit=einheit)
        )
        registry.provider_registrieren(Provider(f"metrik.{schluessel}", MODUL, bezeichnung, wert))
        if bereiche is not None:
            registry.provider_registrieren(
                Provider(f"metrik.{schluessel}.bereiche", MODUL, bezeichnung, bereiche)
            )


def kacheln_registrieren():
    registry.kachel_registrieren(
        Kachel(
            "avatar.kind_avatar",
            MODUL,
            "Mein Avatar",
            "avatar/kachel_kind.html",
            {KIND},
            kacheln.kind_kontext,
            sichtbar=kacheln.kind_sichtbar,
            reihenfolge=5,
        )
    )
    registry.kachel_registrieren(
        Kachel(
            "avatar.kind_werkstatt",
            MODUL,
            "Meine Werkstatt",
            "avatar/kacheln/kind_werkstatt.html",
            {KIND},
            kacheln.werkstatt_kontext,
            sichtbar=kacheln.werkstatt_sichtbar,
            reihenfolge=13,
        )
    )
    registry.kachel_registrieren(
        Kachel(
            "avatar.eltern_mods",
            MODUL,
            "Mods und Bauaufträge",
            "avatar/kacheln/eltern_mods.html",
            {ELTERN},
            kacheln.eltern_kontext,
            reihenfolge=28,
        )
    )
