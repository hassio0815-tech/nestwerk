"""Startwerte der Abzeichen (Entscheidung 12, SPEC 18.3): Tagesserie 7/14/30, Wochenserie
1/2/4/8/12/24/48, Quartal voll aktiv, ein Abzeichen je Rangaufstieg. Abzeichen geben keine Punkte.

Serien-Abzeichen sind einmalig (K12) und hängen am **Rekord** der Serie: "einmal 7 Tage in Folge"
ist genau "Rekord-Tagesserie ≥ 7" – so holt jede spätere Prüfung (Job) eine verpasste Verleihung
sicher nach.
"""

TAGESSERIE = (7, 14, 30)
WOCHENSERIE = (1, 2, 4, 8, 12, 24, 48)


def _wochen(n):
    return "Eine aktive Woche geschafft." if n == 1 else f"{n} aktive Wochen in Folge."


def startwerte():
    """Zeilen als dicts (Feldname -> Wert), in Anzeige-Reihenfolge."""
    zeilen = []
    for i, n in enumerate(TAGESSERIE):
        zeilen.append(
            {
                "schluessel": f"tagesserie-{n}",
                "name": f"Tagesserie {n}",
                "beschreibung": f"{n} Tage in Folge mit einer bestätigten Aufgabe.",
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
                "name": f"Wochenserie {n}",
                "beschreibung": _wochen(n),
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
            "name": "Volles Quartal",
            "beschreibung": "Ein ganzes Quartal lang jede Woche aktiv (Pausen zählen nicht).",
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
            "name": "Rangaufstieg",
            "beschreibung": "Einen neuen Rang erreicht.",
            "symbol": "rangaufstieg",
            "gruppe": "rang",
            "metrik": "rang",
            "schwelle": 2,
            "wiederholbar": "bereich",
            "reihenfolge": 50,
        }
    )
    return zeilen


def anlegen(modell):
    """Legt fehlende Start-Abzeichen an; überschreibt nie (Eltern-Änderungen bleiben)."""
    for zeile in startwerte():
        werte = dict(zeile)
        schluessel = werte.pop("schluessel")
        modell.objects.get_or_create(
            schluessel=schluessel, defaults={**werte, "modul": "spielregeln", "aktiv": True}
        )
