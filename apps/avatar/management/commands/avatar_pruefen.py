"""Prüft die gesamte Avatar-Bibliothek: rendert alles und meldet Fehler (Exit-Code 1 bei Fehlern).

* alle Themen mit Grundfigur (alle Frisuren, Haut- und Haarfarben),
* alle Formen jedes Slots mit den Farben jedes Themas,
* alle Baupläne aus den Dateien und aus der Datenbank (Format, Render, SVG-Whitelist).
"""

import time

from django.core.management.base import BaseCommand, CommandError

from apps.avatar.generator import bauplaene, bibliothek, renderer, svgsicher
from apps.avatar.models import ModDefinition

LIMIT_MS = 50


class Command(BaseCommand):
    help = "Rendert alle Themen, Formen und Baupläne und meldet Fehler."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ohne-db", action="store_true", help="Baupläne der Datenbank auslassen."
        )

    def handle(self, *args, **opts):
        self.fehler = []
        self.anzahl = 0
        self.langsam = 0
        self.laengster = 0.0
        self._themen()
        self._formen()
        plaene = [(f"datei:{p['schluessel']}", p) for p in bibliothek.bauplaene_aus_dateien()]
        if not opts["ohne_db"]:
            plaene += [
                (f"db:{m.schluessel}", self._aus_db(m))
                for m in ModDefinition.objects.select_related("thema", "slot")
            ]
        schluessel = set()
        for herkunft, plan in plaene:
            self._bauplan(herkunft, plan)
            if herkunft.startswith("datei:"):
                if plan["schluessel"] in schluessel:
                    self.fehler.append(f"{herkunft}: Schlüssel doppelt")
                schluessel.add(plan["schluessel"])
        self._eindeutig(plaene)
        for meldung in self.fehler:
            self.stderr.write(self.style.ERROR(meldung))
        self.stdout.write(
            f"{self.anzahl} Bilder gerendert, {len(plaene)} Baupläne geprüft, "
            f"längster Render {self.laengster:.1f} ms, {len(self.fehler)} Fehler"
        )
        if self.fehler:
            raise CommandError(f"{len(self.fehler)} Fehler in der Avatar-Bibliothek")
        self.stdout.write(self.style.SUCCESS("avatar_pruefen: alles in Ordnung"))

    @staticmethod
    def _aus_db(mod):
        return {
            "schluessel": mod.schluessel,
            "name": mod.name,
            "beschreibung": mod.beschreibung,
            "thema": mod.thema.schluessel,
            "slot": mod.slot.schluessel,
            "seltenheit": mod.seltenheit,
            "preis": mod.preis,
            "bauzeit_stunden": mod.bauzeit_stunden,
            "teile": (mod.bauplan or {}).get("teile", []),
            "svg_override": mod.svg_override or None,
        }

    def _rendern(self, name, zustand):
        start = time.perf_counter()
        try:
            svg = renderer.rendern(zustand)
        except renderer.RenderFehler as exc:
            self.fehler.append(f"{name}: {exc}")
            return
        dauer = (time.perf_counter() - start) * 1000
        self.laengster = max(self.laengster, dauer)
        self.anzahl += 1
        if dauer > LIMIT_MS:
            self.fehler.append(f"{name}: Render dauert {dauer:.0f} ms (Limit {LIMIT_MS} ms)")
        meldung = svgsicher.svg_pruefen(svg)
        if meldung:
            self.fehler.append(f"{name}: erzeugtes SVG verletzt die Whitelist: {meldung}")

    def _themen(self):
        figur = bibliothek.figur()
        for t in bibliothek.themen():
            for frisur in figur["frisuren"]:
                for haut in figur["hautfarben"]:
                    self._rendern(
                        f"thema {t}/{frisur}/{haut}",
                        {"thema": t, "figur": {"haut": haut, "frisur": frisur}},
                    )
            for haar in figur["haarfarben"]:
                self._rendern(f"thema {t}/{haar}", {"thema": t, "figur": {"haar": haar}})

    def _formen(self):
        for slot in bibliothek.slot_schluessel():
            for form_name in bibliothek.formen(slot):
                for muster in bibliothek.MUSTER:
                    teil = bauplaene.teile_probe(form_name, muster)
                    for t in ("ritter", "weltraum", "dschungel"):
                        self._rendern(
                            f"form {slot}/{form_name}/{muster}/{t}",
                            {"thema": t, "mods": {slot: {"teile": [teil]}}},
                        )

    def _bauplan(self, herkunft, plan):
        meldungen = bauplaene.bauplan_pruefen(plan)
        if meldungen:
            self.fehler += [f"{herkunft}: {m}" for m in meldungen]
            return
        self._rendern(herkunft, bauplaene.zustand_fuer_vorschau(plan))

    def _eindeutig(self, plaene):
        belegt = {}
        for herkunft, plan in plaene:
            if not herkunft.startswith("datei:"):
                continue
            schluessel = (plan.get("thema"), plan.get("slot"), plan.get("seltenheit"))
            if schluessel in belegt:
                self.fehler.append(
                    f"{herkunft}: Thema/Slot/Seltenheit {schluessel} "
                    f"schon durch {belegt[schluessel]} belegt"
                )
            belegt[schluessel] = herkunft
