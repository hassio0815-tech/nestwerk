"""Startwerte der Abzeichen (Entscheidung 12, SPEC 18.3): Tagesserie 7/14/30, Wochenserie
1/2/4/8/12/24/48, Quartal voll aktiv, ein Abzeichen je Rangaufstieg. Abzeichen geben keine Punkte.

Serien-Abzeichen sind einmalig (K12) und hängen am **Rekord** der Serie: "einmal 7 Tage in Folge"
ist genau "Rekord-Tagesserie ≥ 7" – so holt jede spätere Prüfung (Job) eine verpasste Verleihung
sicher nach.
"""

from django.utils.translation import gettext_noop as _

TAGESSERIE = (7, 14, 30)
WOCHENSERIE = (1, 2, 4, 8, 12, 24, 48)


# Namen und Beschreibungen sind msgids (docs/i18n.md): feste Texte, damit makemessages sie findet.
TAGESSERIE_NAMEN = {
    7: _("Tagesserie 7"),
    14: _("Tagesserie 14"),
    30: _("Tagesserie 30"),
}
TAGESSERIE_TEXTE = {
    7: _("7 Tage in Folge mit einer bestätigten Aufgabe."),
    14: _("14 Tage in Folge mit einer bestätigten Aufgabe."),
    30: _("30 Tage in Folge mit einer bestätigten Aufgabe."),
}
WOCHENSERIE_NAMEN = {
    1: _("Wochenserie 1"),
    2: _("Wochenserie 2"),
    4: _("Wochenserie 4"),
    8: _("Wochenserie 8"),
    12: _("Wochenserie 12"),
    24: _("Wochenserie 24"),
    48: _("Wochenserie 48"),
}
WOCHENSERIE_TEXTE = {
    1: _("Eine aktive Woche geschafft."),
    2: _("2 aktive Wochen in Folge."),
    4: _("4 aktive Wochen in Folge."),
    8: _("8 aktive Wochen in Folge."),
    12: _("12 aktive Wochen in Folge."),
    24: _("24 aktive Wochen in Folge."),
    48: _("48 aktive Wochen in Folge."),
}


def startwerte():
    """Zeilen als dicts (Feldname -> Wert), in Anzeige-Reihenfolge."""
    zeilen = []
    for i, n in enumerate(TAGESSERIE):
        zeilen.append(
            {
                "schluessel": f"tagesserie-{n}",
                "name": TAGESSERIE_NAMEN[n],
                "beschreibung": TAGESSERIE_TEXTE[n],
                "symbol": f"tagesserie-{n}",
                "gruppe": "tagesserie",
                "metrik": "rekord_tagesserie",
                "schwelle": n,
                "wiederholbar": "einmalig",
                "reihenfolge": 10 + i,
            }
        )
    for i, n in enumerate(WOCHENSERIE):
        zeilen.append(
            {
                "schluessel": f"wochenserie-{n}",
                "name": WOCHENSERIE_NAMEN[n],
                "beschreibung": WOCHENSERIE_TEXTE[n],
                "symbol": f"wochenserie-{n}",
                "gruppe": "wochenserie",
                "metrik": "rekord_wochenserie",
                "schwelle": n,
                "wiederholbar": "einmalig",
                "reihenfolge": 20 + i,
            }
        )
    zeilen.append(
        {
            "schluessel": "quartal-voll-aktiv",
            "name": _("Volles Quartal"),
            "beschreibung": _("Ein ganzes Quartal lang jede Woche aktiv (Pausen zählen nicht)."),
            "symbol": "quartal-voll-aktiv",
            "gruppe": "quartal",
            "metrik": "quartal_voll_aktiv",
            "schwelle": 1,
            "wiederholbar": "bereich",
            "reihenfolge": 40,
        }
    )
    zeilen.append(
        {
            "schluessel": "rangaufstieg",
            "name": _("Rangaufstieg"),
            "beschreibung": _("Einen neuen Rang erreicht."),
            "symbol": "rangaufstieg",
            "gruppe": "rang",
            "metrik": "rang",
            "schwelle": 2,
            "wiederholbar": "bereich",
            "reihenfolge": 50,
        }
    )
    zeilen.extend(_ruhmeshalle())
    return zeilen


# P3-A: Ruhmeshalle (Metriken liefert das Modul avatar über kern.registry)
RUHMESHALLE = (
    (
        "erster-held",
        _("Erster Held"),
        _("Den ersten Helden in die Ruhmeshalle gestellt."),
        "ruhmeshalle_eintraege",
        1,
    ),
    (
        "heldentrio",
        _("Heldentrio"),
        _("Drei Helden in der Ruhmeshalle."),
        "ruhmeshalle_eintraege",
        3,
    ),
    (
        "sammler",
        _("Sammler"),
        _("In jedem der 10 Themen einen Helden in der Ruhmeshalle."),
        "ruhmeshalle_themen",
        10,
    ),
    (
        "legende",
        _("Legende"),
        _("Einen Helden auf höchstem Rang in die Ruhmeshalle gestellt."),
        "ruhmeshalle_hoechster_rang",
        6,
    ),
)


def _ruhmeshalle():
    return [
        {
            "schluessel": schluessel,
            "name": name,
            "beschreibung": beschreibung,
            "symbol": schluessel,
            "gruppe": "ruhmeshalle",
            "metrik": metrik,
            "schwelle": schwelle,
            "wiederholbar": "einmalig",
            "modul": "avatar",
            "reihenfolge": 60 + i,
        }
        for i, (schluessel, name, beschreibung, metrik, schwelle) in enumerate(RUHMESHALLE)
    ]


def anlegen(modell):
    """Legt fehlende Start-Abzeichen an; überschreibt nie (Eltern-Änderungen bleiben)."""
    for zeile in startwerte():
        werte = dict(zeile)
        schluessel = werte.pop("schluessel")
        modell.objects.get_or_create(
            schluessel=schluessel, defaults={"modul": "spielregeln", "aktiv": True, **werte}
        )
