"""Screenshots Sondertag (AP27): Pop-up, Kind-Kachel, Eltern-Übersicht, Meilensteine.

Nutzt die Bausteine aus ``screenshots.py`` mit eigenem Port/Verzeichnis (parallel zu anderen
Läufen):

    NESTWERK_DEMO_PORT=8767 NESTWERK_DEMO_DIR=/tmp/nestwerk-demo-ap27 \\
        .venv/bin/python tools/oberflaeche/sondertag_screens.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("NESTWERK_DEMO_PORT", "8767")
os.environ.setdefault("NESTWERK_DEMO_DIR", "/tmp/nestwerk-demo-ap27")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import screenshots as s  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ZIEL = s.ROOT / "docs/screenshots/phase2/sondertag"


def demo(modus):
    subprocess.run(
        [sys.executable, str(s.ROOT / "tools/oberflaeche/sondertag_demo.py"), modus],
        cwd=s.ROOT,
        env=s._env(),
        check=True,
    )


def kind_seite(browser, aufn, name, pin):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    page = ctx.new_page()
    aufn.s.anbinden(page)
    s.kind_login(page, aufn, name, pin, fotos=False)
    return ctx, page


def ablauf(browser, aufn):
    # Kind A: festliches Pop-up mit Wunsch-Formular (einlösbar erst später, K6)
    ctx, page = kind_seite(browser, aufn, "Kind A", "1111")
    aufn.s.neu("sondertag-popup")
    # Pop-ups holt schon die Startseite nach der Anmeldung (danach gelten sie als gesehen)
    page.wait_for_selector(".st-popup [data-st-wunsch] textarea", timeout=10000)
    page.wait_for_timeout(600)
    aufn.foto(page, "sondertag-popup", voll=False)
    page.fill(".st-popup textarea[name=wunsch]", "Übernachtung im Zelt im Garten")
    page.locator(".st-popup input[name=begleitung][value=egal]").check()
    page.locator(".st-popup").get_by_role("button", name="Wunsch abschicken").click()
    page.wait_for_selector(".st-wunsch__danke", timeout=10000)
    aufn.s.neu("sondertag-popup-gesendet")
    aufn.foto(page, "sondertag-popup-gesendet", voll=False)
    aufn.seite(page, "sondertag-kind-kachel-verdient", "/kind/")
    ctx.close()

    # Kind B: Fortschritt "Noch 2 Mods und … Wochen"
    ctx, page = kind_seite(browser, aufn, "Kind B", "2222")
    aufn.seite(page, "sondertag-kind-kachel-fortschritt", "/kind/")
    ctx.close()

    # Eltern: Übersicht, Wunsch von Kind C annehmen, Übergabe, Meilensteine
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    eltern = ctx.new_page()
    aufn.s.anbinden(eltern)
    s.eltern_login(eltern, aufn)
    aufn.seite(eltern, "sondertag-eltern-dashboard", "/eltern/")
    aufn.seite(eltern, "sondertag-eltern-uebersicht", "/eltern/sondertage/")
    karte = eltern.locator("[data-st-wunsch]").filter(has_text="Kind C")
    karte.get_by_role("button", name="Wunsch angenommen").click()
    eltern.wait_for_load_state("networkidle")
    aufn.s.neu("sondertag-eltern-angenommen")
    aufn.foto(eltern, "sondertag-eltern-angenommen")
    aufn.seite(eltern, "meilensteine-verwaltung", "/eltern/meilensteine/")
    ctx.close()

    # Kind C: Bestätigung (Pop-up + Kachel)
    demo("worker")
    ctx, page = kind_seite(browser, aufn, "Kind C", "3333")
    aufn.s.neu("sondertag-bestaetigung")
    page.wait_for_selector(".st-popup", timeout=10000)
    page.wait_for_timeout(800)
    aufn.foto(page, "sondertag-bestaetigung", voll=False)
    ctx.close()


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    for alt in ZIEL.glob("*.png"):
        alt.unlink()
    proc = None
    try:
        proc = s.server_starten()
        sammler = s.Sammler()
        aufn = s.Aufnahme(ZIEL, sammler)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
            page = ctx.new_page()
            sammler.anbinden(page)
            with tempfile.TemporaryDirectory() as tmp:
                s.einrichtung(page, s.Aufnahme(Path(tmp), sammler))
            ctx.close()
            s.demo_daten()
            demo("aufbau")
            ablauf(browser, aufn)
            browser.close()
        s.berichte(aufn, ZIEL)
        print(f"{len(aufn.dateien)} Screenshots in {ZIEL}")
    finally:
        s.server_stoppen(proc)


if __name__ == "__main__":
    main()
