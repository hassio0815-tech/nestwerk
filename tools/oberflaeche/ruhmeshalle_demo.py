"""Ruhmeshallen-Zustand für die Screenshots (P3-A), gegen die Demo-DB.

    python tools/oberflaeche/ruhmeshalle_demo.py

Kind B bekommt zwei Helden direkt (Rang 4 mit Widmung, Rang 6 = höchste Seltenheit), Kind A
bekommt alle sechs Slots ausgebaut und kann den Helden im Browser selbst in die Ruhmeshalle
stellen (echter Ablauf, Bestätigungsdialog).
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nestwerk.settings.entwicklung")

import django  # noqa: E402

django.setup()

from apps.avatar import services  # noqa: E402
from apps.avatar.models import BesitzStatus, ModBesitz, ModDefinition, RuhmeshallenEintrag, Thema  # noqa: E402
from apps.kern import einstellungen, zeit  # noqa: E402
from apps.konten.models import Benutzer  # noqa: E402

SLOTS = ("kopf", "koerper", "ruecken", "hand", "begleiter", "hintergrund")
RAENGE = {4: ("Epic", "epic"), 6: ("God", "god")}


def held_direkt(kind, thema_schluessel, rang, widmung="", figur=None):
    thema = Thema.objects.get(schluessel=thema_schluessel)
    mods = {
        m.slot.schluessel: {"schluessel": m.schluessel, "name": m.name, "seltenheit": m.seltenheit}
        | m.render_mod()
        for m in ModDefinition.objects.filter(
            thema=thema, seltenheit=rang, modset__isnull=True
        ).select_related("slot")
    }
    name, selten = RAENGE[rang]
    start = zeit.jetzt() - timedelta(weeks=14 + rang)
    eintrag = RuhmeshallenEintrag.objects.create(
        kind=kind,
        thema=thema,
        thema_daten=thema.als_dict(),
        mods=mods,
        figur=figur or {"haut": "haut5", "haar": "haar7", "frisur": "lang"},
        rang_stufe=rang,
        rang_name=name,
        rang_selten=selten,
        themenstart=start,
        erstellt_am=zeit.jetzt() - timedelta(days=rang * 3),
        bauzeit_wochen=14 + rang,
        anzahl_mods=6,
        aufgaben_anzahl=40 + rang * 7,
    )
    if widmung:
        eltern = Benutzer.objects.filter(rolle="eltern").first()
        services.widmung_setzen(eintrag, widmung, von=eltern)


def main():
    einstellungen.setzen("avatar.max_zaehlende_mods_woche", 6, akteur=None)
    eltern = Benutzer.objects.filter(rolle="eltern").first()
    a = Benutzer.objects.get(anzeigename="Kind A")
    b = Benutzer.objects.get(anzeigename="Kind B")
    held_direkt(b, "weltraum", 4, "Für unseren Sternenfahrer: Du hast den Mond erobert!")
    held_direkt(
        b,
        "ritter",
        6,
        "Legendär. Wir sind so stolz auf dich.",
        {"haut": "haut5", "haar": "haar7", "frisur": "lang"},
    )
    # Kind A: alle sechs Slots fertig, angelegt und zählend
    from apps.punkte import services as punkte
    from apps.punkte.models import Art

    punkte.buchen(a, Art.AUFGABE, 3000, schluessel="demo-halle:a", quelle_modul="demo", von=None)
    for slot in SLOTS:
        schluessel = f"ritter-{slot}-1"
        if not ModBesitz.objects.filter(
            kind=a, mod__schluessel=schluessel, status__in=("im_bau", "fertig")
        ).exists():
            services.mod_kaufen(a, schluessel)
    for besitz in ModBesitz.objects.filter(kind=a, status=BesitzStatus.IM_BAU):
        services.bau_sofort_fertigstellen(besitz, von=eltern)
    woche = zeit.aktuelle_woche()
    ModBesitz.objects.filter(kind=a).update(
        zaehlt_ab_iso_jahr=woche.jahr, zaehlt_ab_iso_woche=woche.woche
    )
    for slot in SLOTS:
        services.mod_anlegen(a, f"ritter-{slot}-1")


main()
