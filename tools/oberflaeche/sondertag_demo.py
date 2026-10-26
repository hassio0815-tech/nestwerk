"""Sondertag-Zustände für die Screenshots (AP27), gegen die Demo-DB.

    python tools/oberflaeche/sondertag_demo.py aufbau|worker

- aufbau:
  - Kind A: Rang Uncommon, alle 6 Uncommon-Mods gebaut -> Sondertag verdient; letzter Sondertag
    vor 100 Tagen (nachgetragen, mit Papa) -> einlösbar erst in 50 Tagen (Pop-up mit Wunsch).
  - Kind B: Rang Uncommon, 4 von 6 Uncommon-Mods; letzter Sondertag vor 30 Tagen -> Kachel
    "Noch 2 Mods und … Wochen".
  - Kind C: Avatar, Rang Uncommon, 6 Mods -> verdient und einlösbar; Wunsch an Papa gesendet.
- worker: Ereignisse verteilen (Pop-ups, Benachrichtigungen).
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nestwerk.settings.entwicklung")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from apps.avatar import services as avatar  # noqa: E402
from apps.avatar.models import ModBesitz  # noqa: E402
from apps.ereignisse import worker  # noqa: E402
from apps.kern import zeit  # noqa: E402
from apps.konten.models import Benutzer  # noqa: E402
from apps.punkte import services as punkte  # noqa: E402
from apps.punkte.models import Art  # noqa: E402
from apps.sondertag import selectors, services  # noqa: E402
from apps.spielregeln import services as spielregeln  # noqa: E402
from apps.spielregeln.models import Rang, RangAufstieg  # noqa: E402

SLOTS = ("hintergrund", "ruecken", "koerper", "kopf", "hand", "begleiter")


def rang_geben(kind, stufe):
    for rang in Rang.objects.filter(stufe__gt=1, stufe__lte=stufe):
        RangAufstieg.objects.get_or_create(
            kind=kind,
            rang=rang,
            defaults={
                "xp_bei_aufstieg": 0,
                "aktive_wochen_bei_aufstieg": 0,
                "schwelle_bei_aufstieg": 0,
            },
        )


def mods_bauen(kind, thema, seltenheit, anzahl, eltern):
    """Mods kaufen, sofort fertig, Wertungswochen in die Vergangenheit legen (Demo)."""
    punkte.buchen(
        kind,
        Art.AUFGABE,
        80 * anzahl,
        schluessel=f"demo-st:{kind.pk}:{seltenheit}",
        quelle_modul="aufgaben",
    )
    for i, slot in enumerate(SLOTS[:anzahl]):
        besitz = avatar.mod_kaufen(kind, f"{thema}-{slot}-{seltenheit}")
        avatar.bau_sofort_fertigstellen(besitz, von=eltern)
        w = zeit.aktuelle_woche()
        for _ in range(anzahl - i):  # je Mod eine frühere Wertungswoche (Zeitbremse)
            w = w.vorherige()
        ModBesitz.objects.filter(pk=besitz.pk).update(
            zaehlt_ab_iso_jahr=w.jahr, zaehlt_ab_iso_woche=w.woche
        )


def aufbau():
    kinder = {k.anzeigename: k for k in Benutzer.objects.filter(rolle="kind")}
    eltern = {e.anzeigename: e for e in Benutzer.objects.filter(rolle="eltern")}
    mama, papa = eltern["Mama"], eltern["Papa"]
    a, b, c = kinder["Kind A"], kinder["Kind B"], kinder["Kind C"]
    heute = zeit.heute()
    with transaction.atomic():
        services.manuell_erfassen(
            a, von=mama, datum=heute - timedelta(days=100), begleitung=papa.pk, notiz="Zoo"
        )
        services.manuell_erfassen(
            b, von=mama, datum=heute - timedelta(days=30), begleitung=mama.pk, notiz="Kino und Eis"
        )
        services.manuell_erfassen(
            c, von=papa, datum=heute - timedelta(days=260), begleitung=mama.pk, notiz="Freizeitpark"
        )
    if not hasattr(c, "avatar"):
        avatar.avatar_waehlen(
            c, "dschungel", {"haut": "haut4", "haar": "haar5", "frisur": "struppig"}
        )
    for kind, thema, anzahl in ((a, "ritter", 6), (b, "weltraum", 4), (c, "dschungel", 6)):
        rang_geben(kind, 2)
        mods_bauen(kind, thema, 2, anzahl, mama)
        with transaction.atomic():
            spielregeln.abzeichen_pruefen(kind)
    eintrag = selectors.aktueller(c)
    services.wunsch_senden(
        c, eintrag.anspruch, wunsch="Kletterhalle und danach Pizza", begleitung="papa"
    )
    for kind in (a, b, c):
        print(kind.anzeigename, selectors.fortschritt(kind).text)


def worker_runde():
    """Bis nichts mehr offen ist (Demo-Daten erzeugen viele Ereignisse)."""
    for _ in range(100):
        ergebnis = worker.runde(stapel=200)
        if not (ergebnis["verteilt"] or ergebnis["ok"] or ergebnis["nachlauf"]):
            break


if __name__ == "__main__":
    {"aufbau": aufbau, "worker": worker_runde}[sys.argv[1]]()
    worker_runde()
