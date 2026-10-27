"""Start-Meilensteine für Sondertage (AP27, Entscheidung 1, ARCHITECTURE 7.6/13.1 O3).

- Rang N in 2..5: ``rang >= N`` UND ``ausbaustufe_seltenheit_N >= 6`` (alle 6 Slots in Seltenheit
  N gebaut), einmal im Leben (auch nach Themenwechsel nicht erneut).
- God Mode: je Zyklus (Bereich ``zyklus-K``) Wochen geschafft UND Mod-Set K vollständig;
  wiederholbar, endlos. Kein zusätzlicher Stufe-6-Meilenstein (O3).

Daten, nicht Code: Eltern können Bedingungen in der Meilenstein-Verwaltung anpassen oder Regeln
ausschalten; diese Funktion überschreibt nie (get_or_create je Schlüssel).
"""

from django.utils.translation import gettext_noop as _

MODUL = "sondertag"
BELOHNUNGSART = "sondertag"

RAENGE = ((2, "Uncommon"), (3, "Rare"), (4, "Epic"), (5, "Legendary"))
# Namen/Beschreibungen sind msgids (docs/i18n.md): feste Texte, damit makemessages sie findet.
NAMEN = {
    2: _("Sondertag: Ausbaustufe 6 in Uncommon"),
    3: _("Sondertag: Ausbaustufe 6 in Rare"),
    4: _("Sondertag: Ausbaustufe 6 in Epic"),
    5: _("Sondertag: Ausbaustufe 6 in Legendary"),
}
BESCHREIBUNGEN = {
    2: _("Rang Uncommon erreicht und alle 6 Slots mit Uncommon-Mods gebaut."),
    3: _("Rang Rare erreicht und alle 6 Slots mit Rare-Mods gebaut."),
    4: _("Rang Epic erreicht und alle 6 Slots mit Epic-Mods gebaut."),
    5: _("Rang Legendary erreicht und alle 6 Slots mit Legendary-Mods gebaut."),
}
GODMODE_SCHLUESSEL = "sondertag-godmode-zyklus"


def rang_schluessel(stufe: int) -> str:
    return f"sondertag-rang-{stufe}"


def regeln() -> list[dict]:
    ergebnis = []
    for nr, (stufe, _name) in enumerate(RAENGE, 1):
        ergebnis.append(
            {
                "schluessel": rang_schluessel(stufe),
                "name": NAMEN[stufe],
                "beschreibung": BESCHREIBUNGEN[stufe],
                "bedingungen": [
                    {"metrik": "rang", "vergleich": ">=", "wert": stufe},
                    {"metrik": f"ausbaustufe_seltenheit_{stufe}", "vergleich": ">=", "wert": 6},
                ],
                "wiederholbar": "einmalig",
                "reihenfolge": 200 + nr,
            }
        )
    ergebnis.append(
        {
            "schluessel": GODMODE_SCHLUESSEL,
            "name": _("Sondertag: God-Mode-Zyklus"),
            "beschreibung": _(
                "Je God-Mode-Zyklus (26 aktive Wochen) das neue Mod-Set komplett gebaut."
            ),
            "bedingungen": [
                {"metrik": "godmode_zyklus", "vergleich": ">=", "wert": 1},
                {"metrik": "godmode_set_vollstaendig", "vergleich": ">=", "wert": 6},
            ],
            "wiederholbar": "bereich",
            "reihenfolge": 210,
        }
    )
    return ergebnis


def anlegen(regel_modell):
    """Legt fehlende Regeln an (historisches oder echtes Modell ``MeilensteinRegel``)."""
    for r in regeln():
        regel_modell.objects.get_or_create(
            schluessel=r["schluessel"],
            defaults={
                "name": r["name"],
                "beschreibung": r["beschreibung"],
                "bedingungen": r["bedingungen"],
                "belohnungsart": BELOHNUNGSART,
                "wiederholbar": r["wiederholbar"],
                "modul": MODUL,
                "reihenfolge": r["reihenfolge"],
                "aktiv": True,
            },
        )
