"""AP32: Screenshots der Eltern-Seite "Prognose & Kalibrierung" (Demo-Server wie screenshots.py).

    NESTWERK_DEMO_PORT=8769 NESTWERK_DEMO_DIR=/tmp/nestwerk-demo-p3b \
      .venv/bin/python tools/oberflaeche/prognose_screens.py --ziel docs/screenshots/phase3/prognose

Kind A: gleichmäßig fleißig, Kind B: jede 2. Woche aktiv (Mindestwochen bremsen),
Kind C: erst 2 Wochen Verlauf (Hinweis statt Zahl).
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import screenshots as s  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SEED = """
from datetime import timedelta
from apps.kern import zeit
from apps.konten import selectors as konten
from apps.spielregeln.models import Wochenauswertung
from apps.kern.zeit import IsoWoche

montag = IsoWoche.von(zeit.heute()).montag
plan = [(175, lambda i: True, 8), (350, lambda i: i % 2 == 0, 8), (200, lambda i: True, 2)]
for kind, (xp, aktiv, n) in zip(konten.aktive_kinder(), plan):
    for i in range(1, n + 1):
        tag = montag - timedelta(weeks=i)
        iso = tag.isocalendar()
        a = aktiv(i)
        Wochenauswertung.objects.update_or_create(
            kind=kind, iso_jahr=iso[0], iso_woche=iso[1],
            defaults=dict(montag=tag, aktiv=a, neutral=False, pausentage=0,
                          xp_woche=xp if a else 0, wochenserie_danach=0, aktive_wochen_gesamt=0),
        )
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ziel", default="docs/screenshots/phase3/prognose")
    args = ap.parse_args()
    ziel = (s.ROOT / args.ziel).resolve()
    ziel.mkdir(parents=True, exist_ok=True)
    for alt in ziel.glob("*.png"):
        alt.unlink()
    proc = None
    try:
        proc = s.server_starten()
        sammler = s.Sammler()
        aufn = s.Aufnahme(ziel, sammler)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
            page = ctx.new_page()
            sammler.anbinden(page)
            with tempfile.TemporaryDirectory() as tmp:
                s.einrichtung(page, s.Aufnahme(Path(tmp), sammler))
            s.demo_daten()
            subprocess.run(
                [sys.executable, "manage.py", "shell", "-c", SEED],
                cwd=s.ROOT,
                env=s._env(),
                check=True,
            )
            s.eltern_login(page, aufn)
            aufn.seite(page, "prognose-eltern", "/eltern/prognose/")
            ctx.close()
            browser.close()
        s.berichte(aufn, ziel)
        print(f"{len(aufn.dateien)} Screenshots in {ziel}")
    finally:
        s.server_stoppen(proc)


if __name__ == "__main__":
    main()
