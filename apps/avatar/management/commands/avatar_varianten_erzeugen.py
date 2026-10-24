"""Baupläne eines Themas aus Themenregeln erzeugen (Vorlage für AP25, danach von Hand verfeinern).

    manage.py avatar_varianten_erzeugen --thema ritter [--seltenheit 1 2] [--slot kopf]

Schreibt/ergänzt ``apps/avatar/daten/bauplaene/<thema>.json``. Vorhandene Einträge bleiben
unverändert (außer mit ``--ueberschreiben``): handgemachte Namen gehen nicht verloren.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.avatar.generator import bauplaene, bibliothek


class Command(BaseCommand):
    help = "Erzeugt Baupläne (Slot x Seltenheit) für ein Thema als JSON-Datei."

    def add_arguments(self, parser):
        parser.add_argument("--thema", required=True)
        parser.add_argument("--seltenheit", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6])
        parser.add_argument("--slot", nargs="+", default=list(bibliothek.slot_schluessel()))
        parser.add_argument("--ueberschreiben", action="store_true")
        parser.add_argument("--stdout", action="store_true", help="Nur ausgeben, nichts schreiben.")

    def handle(self, *args, **opts):
        thema = bibliothek.themen().get(opts["thema"])
        if thema is None or thema["nur_eltern"]:
            raise CommandError(f"Unbekanntes Thema: {opts['thema']}")
        pfad = bibliothek.DATEN / "bauplaene" / f"{opts['thema']}.json"
        vorhanden = (
            json.loads(pfad.read_text(encoding="utf-8"))["bauplaene"] if pfad.exists() else []
        )
        nach_schluessel = {p["schluessel"]: p for p in vorhanden}
        neu = 0
        for slot in opts["slot"]:
            for stufe in opts["seltenheit"]:
                plan = bauplaene.bauplan_erzeugen(opts["thema"], slot, stufe)
                if plan["schluessel"] in nach_schluessel and not opts["ueberschreiben"]:
                    continue
                nach_schluessel[plan["schluessel"]] = plan
                neu += 1
        ergebnis = sorted(
            nach_schluessel.values(),
            key=lambda p: (p["seltenheit"], bibliothek.slot_schluessel().index(p["slot"])),
        )
        fehler = [m for p in ergebnis for m in bauplaene.bauplan_pruefen(p)]
        if fehler:
            raise CommandError("; ".join(fehler))
        text = json.dumps(
            {"format": bauplaene.FORMAT, "bauplaene": ergebnis}, ensure_ascii=False, indent=1
        )
        if opts["stdout"]:
            self.stdout.write(text)
            return
        pfad.write_text(text + "\n", encoding="utf-8")
        self.stdout.write(f"{pfad}: {neu} neu, {len(ergebnis)} gesamt")
