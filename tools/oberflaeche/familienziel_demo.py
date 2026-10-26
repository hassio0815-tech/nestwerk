"""Familienziel-Zustände für die Screenshots (AP29), gegen die Demo-DB.

    python tools/oberflaeche/familienziel_demo.py fortschritt|abstimmung|erreicht

- fortschritt: Kind A und B haben Punkte (Kind C noch nicht): Balken, Beiträge, "Fast"-Hinweis.
- abstimmung: Abstimmungstag = heute, Fenster ganztägig, Woche für die Folgewoche angelegt.
- erreicht: Ziel und Bedingung erfüllt (Konfetti-Leiste).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nestwerk.settings.entwicklung")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from apps.familienziel import selectors, services  # noqa: E402
from apps.familienziel.models import Familienbelohnung  # noqa: E402
from apps.kern import einstellungen, zeit  # noqa: E402
from apps.konten.models import Benutzer  # noqa: E402
from apps.punkte import services as punkte  # noqa: E402
from apps.punkte.models import Art  # noqa: E402
from apps.spielregeln import services as spielregeln  # noqa: E402

_zaehler = iter(range(1, 1000))


def xp(kind, menge):
    with transaction.atomic():
        spielregeln.aktivitaet_erfassen(
            kind, zeit.heute(), modul="demo-fz", referenz=f"fz{kind.pk}-{next(_zaehler)}"
        )
        punkte.buchen(
            kind,
            Art.AUFGABE,
            menge,
            schluessel=f"demo-fz:{kind.pk}:{next(_zaehler)}",
            quelle_modul="demo",
            von=None,
        )


def main(modus):
    kinder = {k.anzeigename: k for k in Benutzer.objects.filter(rolle="kind")}
    a, b, c = kinder["Kind A"], kinder["Kind B"], kinder["Kind C"]
    services.sicherstellen()
    if modus == "fortschritt":
        eltern = Benutzer.objects.filter(rolle="eltern").order_by("pk").first()
        woche = selectors.woche(zeit.aktuelle_woche())
        pizza = Familienbelohnung.objects.get(titel="Pizza")
        services.woche_festlegen(woche, von=eltern, belohnung=pizza)
        xp(a, 180)
        xp(b, 90)
    elif modus == "abstimmung":
        einstellungen.setzen("familienziel.abstimmung_tag", zeit.heute().isoweekday(), akteur=None)
        services.sicherstellen()
    elif modus == "erreicht":
        xp(c, 40)
        xp(a, 120)
    services.sicherstellen()


if __name__ == "__main__":
    main(sys.argv[1])
