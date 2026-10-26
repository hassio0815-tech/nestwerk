"""Ranking-Zustände für die Screenshots (AP30), gegen die Demo-DB.

    python tools/oberflaeche/ranking_demo.py daten

Gibt den Kindern unterschiedlich viel Fortschritt (XP diese Woche, Abzeichen/Rang folgen aus den
Regeln) und legt für die Vorwoche eine bewertete Woche an: Kind B ist Held der Woche.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nestwerk.settings.entwicklung")

import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402

from django.db import transaction  # noqa: E402

from apps.kern import zeit  # noqa: E402
from apps.kern.zeit import IsoWoche  # noqa: E402
from apps.konten.models import Benutzer  # noqa: E402
from apps.punkte import services as punkte  # noqa: E402
from apps.punkte.models import Art  # noqa: E402
from apps.spielregeln import services as spielregeln  # noqa: E402
from apps.spielregeln.models import Wochenauswertung  # noqa: E402

_zaehler = iter(range(1, 1000))


def xp(kind, menge):
    with transaction.atomic():
        spielregeln.aktivitaet_erfassen(
            kind, zeit.heute(), modul="demo-rk", referenz=f"rk{kind.pk}-{next(_zaehler)}"
        )
        punkte.buchen(
            kind,
            Art.AUFGABE,
            menge,
            schluessel=f"demo-rk:{kind.pk}:{next(_zaehler)}",
            quelle_modul="demo",
            von=None,
        )


def vorwoche(kind, xp_woche, zuwachs, held):
    w = IsoWoche.von(zeit.jetzt()).vorherige()
    Wochenauswertung.objects.update_or_create(
        kind=kind,
        iso_jahr=w.jahr,
        iso_woche=w.woche,
        defaults={
            "montag": w.montag,
            "aktiv": True,
            "neutral": False,
            "pausentage": 0,
            "xp_woche": xp_woche,
            "wochenserie_danach": 2,
            "aktive_wochen_gesamt": 2,
            "zuwachs_relativ": zuwachs,
            "held_der_woche": held,
            "finalisiert_am": zeit.jetzt() - timedelta(days=1),
        },
    )


def main():
    kinder = {k.anzeigename: k for k in Benutzer.objects.filter(rolle="kind")}
    a, b, c = kinder["Kind A"], kinder["Kind B"], kinder["Kind C"]
    xp(a, 120)
    xp(b, 60)
    xp(c, 25)
    vorwoche(a, 140, "0.100", False)
    vorwoche(b, 95, "0.900", True)
    vorwoche(c, 20, "-0.200", False)


if __name__ == "__main__":
    main()
