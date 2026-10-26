# ruff: noqa: E501  (eingebettetes JavaScript in PRUEF_JS)
"""Screenshots und Browser-Prüfung der Nestwerk-Oberfläche (Python-Playwright, kein MCP).

Startet eine Demo-Instanz (eigene DB unter /tmp/nestwerk-demo, Entwicklungs-Settings,
127.0.0.1:8765; änderbar über NESTWERK_DEMO_DIR und NESTWERK_DEMO_PORT), durchläuft den Einrichtungs-Assistenten per Browser, erzeugt Demo-Daten,
macht Screenshots in zwei Viewports und sammelt je Seite Konsolenfehler, CSP-Verstöße,
fehlgeschlagene Requests und externe Requests. Am Ende wird der Server gestoppt und die
Demo-DB gelöscht.

    .venv/bin/python tools/oberflaeche/screenshots.py [--ziel docs/screenshots/phase1]

Siehe README.md im selben Ordner (neue Seiten ergänzen: Liste ``SEITEN`` unten).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
# Parallele Läufe: eigener Port und eigenes Demo-Verzeichnis per Umgebungsvariable
# (NESTWERK_DEMO_PORT, NESTWERK_DEMO_DIR); Standard unverändert.
DEMO_DIR = Path(os.environ.get("NESTWERK_DEMO_DIR", "/tmp/nestwerk-demo"))
PORT = int(os.environ.get("NESTWERK_DEMO_PORT", "8765"))
BASIS = f"http://127.0.0.1:{PORT}"
PASSWORT = "Sonnenblume-4711-Demo"
KINDER = [("Kind A", "1111"), ("Kind B", "2222"), ("Kind C", "3333")]
VIEWPORTS = {"handy": (390, 844), "tablet": (1280, 800)}

# Init-Skript: CSP-Verstöße der Seite einsammeln
CSP_SKRIPT = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => {
  window.__csp.push(e.violatedDirective + ' blockiert ' + (e.blockedURI || 'inline') +
                    ' (' + (e.sourceFile || '') + ':' + (e.lineNumber || 0) + ')');
});
"""


class Sammler:
    """Sammelt Browser-Ereignisse; ``neu(label)`` startet einen neuen Seiten-Abschnitt."""

    def __init__(self):
        self.seiten = {}
        self.aktuell = self.seiten.setdefault("_start", self._leer())

    @staticmethod
    def _leer():
        return {"konsole": [], "csp": [], "fehl_requests": [], "extern": []}

    def neu(self, label):
        self.aktuell = self.seiten.setdefault(label, self._leer())

    def anbinden(self, page):
        page.add_init_script(CSP_SKRIPT)
        page.on("console", self._konsole)
        page.on("pageerror", lambda e: self.aktuell["konsole"].append(f"pageerror: {e}"))
        page.on("requestfailed", self._req_fehl)
        page.on("response", self._antwort)
        page.on("request", self._request)

    def _konsole(self, m):
        if m.type in ("error", "warning"):
            text = f"{m.type}: {m.text}"
            ziel = "csp" if "Content Security Policy" in m.text else "konsole"
            self.aktuell[ziel].append(text)

    def _req_fehl(self, r):
        fehler = r.failure or ""
        if "ERR_ABORTED" in fehler:  # Navigation/Abbruch durch Folge-Request, kein Fehler
            return
        self.aktuell["fehl_requests"].append(f"{r.method} {r.url}: {fehler}")

    def _antwort(self, r):
        if r.status >= 400:
            self.aktuell["fehl_requests"].append(f"{r.status} {r.request.method} {r.url}")

    def _request(self, r):
        if not r.url.startswith((BASIS, "data:", "blob:", "about:")):
            self.aktuell["extern"].append(r.url)

    def csp_holen(self, page):
        try:
            for eintrag in page.evaluate("window.__csp || []"):
                if eintrag not in self.aktuell["csp"]:
                    self.aktuell["csp"].append(eintrag)
        except Exception:
            pass


# --- Demo-Instanz -------------------------------------------------------------------------


def _env():
    env = dict(os.environ)
    env.update(
        DJANGO_SETTINGS_MODULE="nestwerk.settings.entwicklung",
        NESTWERK_DATA_DIR=str(DEMO_DIR),
        NESTWERK_ALLOWED_HOSTS="127.0.0.1,localhost",
        NESTWERK_BASIS_URL=BASIS,
    )
    env.pop("NESTWERK_SETUP_TOKEN", None)
    return env


def server_starten():
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    (DEMO_DIR / "db").mkdir(parents=True)
    env = _env()
    py = sys.executable
    subprocess.run(
        [py, "manage.py", "migrate", "--noinput"],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    log = open(DEMO_DIR / "server.log", "w")
    proc = subprocess.Popen(
        [py, "manage.py", "runserver", f"127.0.0.1:{PORT}", "--noreload"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{BASIS}/gesundheit/", timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"Demo-Server startet nicht, siehe {DEMO_DIR}/server.log")


def server_stoppen(proc):
    if proc:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    shutil.rmtree(DEMO_DIR, ignore_errors=True)


def demo_daten():
    subprocess.run(
        [sys.executable, str(ROOT / "tools/oberflaeche/demo_daten.py")],
        cwd=ROOT,
        env=_env(),
        check=True,
    )
    subprocess.run(
        [sys.executable, "manage.py", "aufgaben_erzeugen"],
        cwd=ROOT,
        env=_env(),
        check=True,
        stdout=subprocess.DEVNULL,
    )


# --- Aufnahme -----------------------------------------------------------------------------


class Aufnahme:
    def __init__(self, ziel, sammler):
        self.ziel = ziel
        self.s = sammler
        self.dateien = []
        self.seiten = []  # [{"label", "url", "dateien", "html_probleme"}]

    def foto(self, page, label, voll=True):
        """Screenshot in allen Viewports der aktuell geladenen Seite."""
        dateien = []
        pruefung = {}
        for name, (b, h) in VIEWPORTS.items():
            page.set_viewport_size({"width": b, "height": h})
            page.wait_for_timeout(250)
            datei = self.ziel / f"{label}__{name}.png"
            page.screenshot(path=str(datei), full_page=voll)
            dateien.append(datei.name)
            pruefung[name] = pruefen(page)
        self.s.csp_holen(page)
        self.seiten.append(
            {
                "label": label,
                "url": page.url.replace(BASIS, ""),
                "dateien": dateien,
                "pruefung": pruefung,
            }
        )
        self.dateien += dateien

    def seite(self, page, label, pfad):
        self.s.neu(label)
        antwort = page.goto(BASIS + pfad, wait_until="networkidle")
        if antwort and antwort.status >= 400:
            self.s.aktuell["fehl_requests"].append(f"{antwort.status} GET {pfad}")
        self.foto(page, label)


PRUEF_JS = """
() => {
  const probleme = [];
  const kl = [];
  for (const el of document.querySelectorAll('a, button, input:not([type=hidden]), select, summary, [role=button]')) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (r.height < 44 || r.width < 44) {
      if (el.matches('input[type=checkbox], input[type=radio], .sprung-link') || el.closest('[aria-hidden=true]')) continue;
      kl.push((el.innerText || el.getAttribute('aria-label') || el.name || el.tagName).trim().slice(0, 30)
              + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
    }
  }
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1) probleme.push('Horizontaler Überlauf: ' + de.scrollWidth + ' > ' + de.clientWidth);
  const ohneName = [...document.querySelectorAll('button, a')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && !e.closest('[aria-hidden=true]') && !e.closest('details:not([open]) > :not(summary)') && !(e.innerText || '').trim() && !e.getAttribute('aria-label') && !e.getAttribute('title');
  }).map(e => e.outerHTML.slice(0, 90));
  if (ohneName.length) probleme.push(ohneName.length + ' Knöpfe/Links ohne Text oder aria-label: ' + ohneName.join(' | '));
  const kleinText = [...document.querySelectorAll('p, span, label, li, td, small, a, button')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && e.childElementCount === 0 && (e.innerText||'').trim() && parseFloat(getComputedStyle(e).fontSize) < 14;
  }).length;
  if (kleinText) probleme.push(kleinText + ' Textelemente unter 14px');
  return {probleme, kleine_ziele: kl.slice(0, 8), kleine_ziele_gesamt: kl.length, titel: document.title};
}
"""


def pruefen(page):
    """DOM-Heuristiken im aktuellen Viewport (Überlauf, Zielgrößen, Beschriftung)."""
    try:
        return page.evaluate(PRUEF_JS)
    except Exception as exc:  # pragma: no cover
        return {"probleme": [f"Prüfung fehlgeschlagen: {exc}"]}


# --- Einrichtungs-Assistent ---------------------------------------------------------------


def weiter(page, text=None):
    """Sendet das Formular des aktuellen Schritts (Hauptknopf)."""
    knopf = page.locator("#assistent form button[type=submit]:not(.einrichtung-standard)")
    if text:
        knopf = page.get_by_role("button", name=text)
    knopf.last.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def einrichtung(page, aufn):
    s = aufn.s
    s.neu("einrichtung-1")
    page.goto(BASIS + "/einrichtung/", wait_until="networkidle")
    aufn.foto(page, "einrichtung-1-name")
    page.fill("[name=app_name]", "Nestwerk Demo")
    weiter(page)

    s.neu("einrichtung-2")
    page.fill("[name=passwort]", PASSWORT)
    page.fill("[name=passwort2]", PASSWORT)
    page.fill("[name=eltern1_name]", "Mama")
    page.fill("[name=eltern1_email]", "demo@example.invalid")
    page.fill("[name=eltern2_name]", "Papa")
    page.fill("[name=eltern2_email]", "demo@example.invalid")
    aufn.foto(page, "einrichtung-2-eltern")
    weiter(page)

    s.neu("einrichtung-3")
    for nr, (name, pin) in enumerate(KINDER):
        page.fill(f"[name=kind-{nr}-name]", name)
        page.fill(f"[name=kind-{nr}-pin]", pin)
        page.fill(f"[name=kind-{nr}-pin2]", pin)
    aufn.foto(page, "einrichtung-3-kinder")
    weiter(page)

    s.neu("einrichtung-4")
    aufn.foto(page, "einrichtung-4-mail")
    page.get_by_role("button", name="Ohne E-Mail fortfahren").first.click()
    page.wait_for_load_state("networkidle")

    s.neu("einrichtung-5")
    page.fill("[name=basis_url]", BASIS)
    if not page.input_value("[name=kind_netze]").strip():
        page.fill("[name=kind_netze]", "127.0.0.0/8\n192.168.0.0/16")
    weiter(page)

    s.neu("einrichtung-6")
    page.fill("[name=go_live_datum]", date.today().isoformat())
    weiter(page)

    s.neu("einrichtung-7")
    weiter(page)

    s.neu("einrichtung-8")
    aufn.foto(page, "einrichtung-8-abschluss")
    weiter(page)
    page.wait_for_timeout(500)
    aufn.foto(page, "einrichtung-9-fertig")


# --- Seiten nach der Einrichtung ----------------------------------------------------------

# (Label, Pfad) je Sitzungsart. Neue Seiten hier ergänzen.
SEITEN_KIND = [
    ("kinder-dashboard", "/kind/"),
    ("kinder-aufgaben", "/kind/aufgaben/"),
    ("kinder-belohnungen", "/kind/belohnungen/"),
    ("kinder-sondertag-wunsch", "/kind/sondertag/wunsch/"),  # AP27 (ohne offenen Anspruch)
]
SEITEN_ELTERN = [
    ("eltern-dashboard", "/eltern/"),
    ("eltern-module", "/module/"),
    ("eltern-meldungen", "/eltern/meldungen/"),
    ("wochenplan", "/eltern/wochenplan/"),
    ("aufgabenformular", "/eltern/aufgaben/neu/"),
    ("aufgabenliste", "/eltern/aufgaben/"),
    ("bibliothek", "/eltern/bibliothek/"),
    ("belohnungs-antraege", "/eltern/belohnungen/"),
    ("einstellungen-editor", "/eltern/einstellungen/"),
    ("familie", "/eltern/familie/"),
    ("benachrichtigungen", "/eltern/benachrichtigungen/"),
    ("push-seite", "/push/"),
    ("styleguide", "/styleguide/"),
    ("abzeichen-galerie", "/abzeichen/galerie/"),  # AP28: alle Abzeichen-Grafiken (nur DEBUG)
    # Phase 2 (Review AP31: alle Eltern-Seiten der Spielebene auf CSP/Konsole prüfen)
    ("eltern-dungeon", "/eltern/dungeon/"),
    ("eltern-pausen", "/eltern/pausen/"),
    ("eltern-raenge", "/eltern/raenge/"),
    ("eltern-abzeichen", "/eltern/abzeichen/"),
    ("eltern-meilensteine", "/eltern/meilensteine/"),
    ("eltern-sondertage", "/eltern/sondertage/"),
]


def kind_login(page, aufn, name, pin, fotos=True):
    aufn.s.neu("tablet-startseite")
    page.goto(BASIS + "/", wait_until="networkidle")
    if fotos:
        aufn.foto(page, "tablet-startseite")
    page.get_by_text(name, exact=False).first.click()
    page.wait_for_load_state("networkidle")
    aufn.s.neu("pin-eingabe")
    if fotos:
        aufn.foto(page, "pin-eingabe")
    for ziffer in pin:
        page.get_by_role("button", name=ziffer, exact=True).click()
    page.wait_for_timeout(300)
    if "/anmelden/kind/" in page.url:  # kein Auto-Absenden: OK drücken
        page.get_by_role("button", name="OK").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def eltern_login(page, aufn):
    aufn.s.neu("eltern-login")
    page.goto(BASIS + "/anmelden/eltern/", wait_until="networkidle")
    aufn.foto(page, "eltern-login")
    page.select_option("[name=eltern]", index=0)
    page.fill("[name=passwort]", PASSWORT)
    page.locator("form button[type=submit]").first.click()
    page.wait_for_load_state("networkidle")


MOD_THEMEN = (
    "ritter",
    "weltraum",
    "ninja",
    "roboter",
    "pirat",
    "wikinger",
    "fussballer",
    "basketballer",
    "rennfahrer",
    "dschungel",
)  # AP25: je Thema die 36 Mods in der Entwickler-Galerie


def avatar_ablauf(browser, aufn):
    """AP24: Kind C hat noch keinen Avatar. Aufruf-Kachel, Erstwahl mit Vorschau, danach das
    Dashboard mit Figur; dazu die Entwickler-Galerie (AP25: je Thema ein Raster mit 36 Mods)."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    page = ctx.new_page()
    aufn.s.anbinden(page)
    kind_login(page, aufn, "Kind C", "3333", fotos=False)
    aufn.seite(page, "avatar-aufruf-dashboard", "/kind/")
    aufn.seite(page, "avatar-wahl", "/kind/avatar/")
    page.locator("input[name=haut][value=haut4]").check()
    page.locator("input[name=haar][value=haar5]").check()
    page.locator("input[name=frisur][value=struppig]").check()
    page.locator("input[name=thema][value=dschungel]").check()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)
    aufn.s.neu("avatar-wahl-getroffen")
    aufn.foto(page, "avatar-wahl-getroffen")
    page.get_by_role("button", name="Das bin ich!").click()
    page.wait_for_load_state("networkidle")
    aufn.s.neu("avatar-dashboard-neu")
    aufn.foto(page, "avatar-dashboard-neu")
    aufn.seite(page, "avatar-galerie", "/avatar/galerie/")
    for thema in MOD_THEMEN:
        aufn.seite(page, f"mods-{thema}", f"/avatar/galerie/?thema={thema}")
    ctx.close()


def familienziel_zustand(modus):
    subprocess.run(
        [sys.executable, str(ROOT / "tools/oberflaeche/familienziel_demo.py"), modus],
        cwd=ROOT,
        env=_env(),
        check=True,
    )


def familienziel_ablauf(browser, aufn):
    """AP29: Tablet-Leiste (Fortschritt, Abstimmung, Erfolg), Kinder-Abstimmung, Eltern-Seite."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    tablet = ctx.new_page()
    aufn.s.anbinden(tablet)
    familienziel_zustand("fortschritt")
    aufn.seite(tablet, "tablet-familienziel", "/tablet/")
    familienziel_zustand("abstimmung")
    aufn.seite(tablet, "tablet-familienziel-abstimmung", "/tablet/")
    ctx.close()

    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    kind = ctx.new_page()
    aufn.s.anbinden(kind)
    kind_login(kind, aufn, "Kind A", "1111", fotos=False)
    aufn.seite(kind, "kind-familienziel-abstimmung", "/kind/")
    kind.locator("input[name=belohnung]").nth(2).check()
    kind.get_by_role("button", name="Abstimmen").click()
    kind.wait_for_load_state("networkidle")
    aufn.s.neu("kind-familienziel-abgestimmt")
    aufn.foto(kind, "kind-familienziel-abgestimmt")
    ctx.close()

    familienziel_zustand("erreicht")
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    seite = ctx.new_page()
    aufn.s.anbinden(seite)
    aufn.seite(seite, "tablet-familienziel-erreicht", "/tablet/")
    eltern_login(seite, aufn)
    aufn.seite(seite, "eltern-familienziel", "/eltern/familienziel/")
    ctx.close()


def ranking_ablauf(browser, aufn):
    """AP30: Familien-Ranking in allen drei Modi. Eltern schalten über das Dashboard um; Tablet
    (ohne Anmeldung), Kinder-Seite und Eltern-Dashboard zeigen den Modus."""
    subprocess.run(
        [sys.executable, str(ROOT / "tools/oberflaeche/ranking_demo.py")],
        cwd=ROOT,
        env=_env(),
        check=True,
    )
    ctx_e = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    eltern = ctx_e.new_page()
    aufn.s.anbinden(eltern)
    eltern_login(eltern, aufn)
    ctx_t = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    tablet = ctx_t.new_page()
    aufn.s.anbinden(tablet)
    ctx_k = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    kind = ctx_k.new_page()
    aufn.s.anbinden(kind)
    kind_login(kind, aufn, "Kind A", "1111", fotos=False)
    for modus, text in (
        ("schaufenster", "Schaufenster"),
        ("held", "Held der Woche"),
        ("rohpunkte", "Rohpunkte"),
    ):
        eltern.goto(BASIS + "/eltern/", wait_until="networkidle")
        eltern.locator("[data-eltern-ranking]").get_by_role("button", name=text).click()
        eltern.wait_for_load_state("networkidle")
        aufn.s.neu(f"ranking-{modus}-eltern")
        aufn.foto(eltern, f"ranking-{modus}-eltern")
        aufn.seite(tablet, f"ranking-{modus}-tablet", "/tablet/")
        aufn.seite(kind, f"ranking-{modus}-kind", "/kind/")
    ctx_e.close()
    ctx_t.close()
    ctx_k.close()


def ruhmeshalle_ablauf(browser, aufn):
    """P3-A: Ruhmeshalle. Kind B hat zwei Helden, Kind A stellt seinen im Browser selbst hinein
    (Dialog, Bestätigung); Tablet-Kachel, Eltern-Seite mit Widmungen."""
    subprocess.run(
        [sys.executable, str(ROOT / "tools/oberflaeche/ruhmeshalle_demo.py")],
        cwd=ROOT,
        env=_env(),
        check=True,
    )
    ctx_t = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    tablet = ctx_t.new_page()
    aufn.s.anbinden(tablet)
    aufn.seite(tablet, "ruhmeshalle-tablet-vorher", "/tablet/")
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    kind = ctx.new_page()
    aufn.s.anbinden(kind)
    kind_login(kind, aufn, "Kind A", "1111", fotos=False)
    aufn.seite(kind, "ruhmeshalle-kind-dashboard", "/kind/")
    aufn.seite(kind, "ruhmeshalle-kind-bereit", "/kind/ruhmeshalle/")
    aufn.seite(kind, "ruhmeshalle-dialog", "/kind/ruhmeshalle/stellen/")
    aufn.seite(kind, "ruhmeshalle-dialog-gewaehlt", "/kind/ruhmeshalle/stellen/?thema=pirat")
    kind.get_by_role("button", name="Ja, in die Ruhmeshalle stellen").click()
    kind.wait_for_load_state("networkidle")
    aufn.s.neu("ruhmeshalle-kind-danach")
    aufn.foto(kind, "ruhmeshalle-kind-danach")
    aufn.seite(kind, "ruhmeshalle-shop-danach", "/kind/mods/")
    ctx.close()
    aufn.seite(tablet, "ruhmeshalle-tablet", "/tablet/")
    ctx_e = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    eltern = ctx_e.new_page()
    aufn.s.anbinden(eltern)
    eltern_login(eltern, aufn)
    aufn.seite(eltern, "ruhmeshalle-eltern-dashboard", "/eltern/")
    aufn.seite(eltern, "ruhmeshalle-eltern", "/eltern/ruhmeshalle/")
    ctx_e.close()
    ctx_t.close()


def seiten_ablauf(browser, aufn):
    avatar_ablauf(browser, aufn)
    familienziel_ablauf(browser, aufn)
    ctx_kind = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    kind = ctx_kind.new_page()
    aufn.s.anbinden(kind)
    kind_login(kind, aufn, "Kind A", "1111")
    for label, pfad in SEITEN_KIND:
        aufn.seite(kind, label, pfad)
    ctx_kind.close()

    ctx_e = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    eltern = ctx_e.new_page()
    aufn.s.anbinden(eltern)
    eltern_login(eltern, aufn)
    for label, pfad in SEITEN_ELTERN:
        aufn.seite(eltern, label, pfad)
    ctx_e.close()
    shop_ablauf(browser, aufn)
    ranking_ablauf(browser, aufn)  # Review AP31: Ranking gehört zum Gesamtlauf


def shop_ablauf(browser, aufn):
    """AP26: Mod-Shop (Kind A: 4 fertige Mods, 1 im Bau), Detail mit Vorschau, Kauf, Werkstatt,
    Themenwechsel-Warnung mit Zahlen; Eltern-Bauaufträge."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
    page = ctx.new_page()
    aufn.s.anbinden(page)
    kind_login(page, aufn, "Kind A", "1111", fotos=False)
    aufn.seite(page, "shop", "/kind/mods/")
    aufn.seite(page, "shop-mod-detail", "/kind/mods/ritter-hintergrund-1/")
    page.get_by_role("button", name="Kaufen für").click()
    page.wait_for_load_state("networkidle")
    aufn.s.neu("shop-nach-kauf")
    aufn.foto(page, "shop-nach-kauf")
    aufn.seite(page, "shop-gesperrt-detail", "/kind/mods/ritter-kopf-3/")
    aufn.seite(page, "shop-werkstatt-dashboard", "/kind/")
    aufn.seite(page, "themenwechsel-auswahl", "/kind/avatar/thema/")
    aufn.seite(page, "themenwechsel-warnung", "/kind/avatar/thema/?thema=pirat")
    ctx.close()
    ctx_e = browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    eltern = ctx_e.new_page()
    aufn.s.anbinden(eltern)
    eltern_login(eltern, aufn)
    aufn.seite(eltern, "eltern-mods", "/eltern/mods/")
    ctx_e.close()


# --- Ausgabe ------------------------------------------------------------------------------


def berichte(aufn, ziel):
    daten = {"seiten": aufn.seiten, "ereignisse": aufn.s.seiten}
    (ziel / "ergebnisse.json").write_text(json.dumps(daten, indent=2, ensure_ascii=False))
    zeilen = [
        "# Automatische Prüfung (Rohdaten)",
        "",
        "| Seite | Konsole | CSP | Requests | Extern | Weitere Hinweise |",
        "|---|---|---|---|---|---|",
    ]
    for s in aufn.seiten:
        e = aufn.s.seiten.get(s["label"], {})
        hinweise = []
        for vp, p in s["pruefung"].items():
            hinweise += [f"{vp}: {x}" for x in p.get("probleme", [])]
            if p.get("kleine_ziele_gesamt"):
                hinweise.append(f"{vp}: {p['kleine_ziele_gesamt']} Ziele <44px")
        zeilen.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                s["label"],
                len(e.get("konsole", [])),
                len(e.get("csp", [])),
                len(e.get("fehl_requests", [])),
                len(e.get("extern", [])),
                "; ".join(hinweise) or "-",
            )
        )
    zeilen += ["", "## Details", ""]
    for label, e in aufn.s.seiten.items():
        for art in ("konsole", "csp", "fehl_requests", "extern"):
            for eintrag in e[art]:
                zeilen.append(f"- `{label}` [{art}] {eintrag}")
    (ziel / "ergebnisse.md").write_text("\n".join(zeilen) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ziel", default="docs/screenshots/phase1")
    ap.add_argument(
        "--nur",
        choices=["ranking", "ruhmeshalle"],
        help="Nur diesen Ablauf aufnehmen (Einrichtung ohne Fotos)",
    )
    ap.add_argument("--sichtbar", action="store_true", help="Browser mit Fenster (Debug)")
    args = ap.parse_args()
    ziel = (ROOT / args.ziel).resolve()
    ziel.mkdir(parents=True, exist_ok=True)
    for alt in ziel.glob("*.png"):
        alt.unlink()
    proc = None
    try:
        proc = server_starten()
        sammler = Sammler()
        aufn = Aufnahme(ziel, sammler)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.sichtbar)
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
            page = ctx.new_page()
            sammler.anbinden(page)
            if args.nur:  # Einrichtung ohne Fotos im Zielordner
                import tempfile

                with tempfile.TemporaryDirectory() as tmp:
                    einrichtung(page, Aufnahme(Path(tmp), sammler))
            else:
                einrichtung(page, aufn)
            ctx.close()
            demo_daten()
            if args.nur == "ranking":
                ranking_ablauf(browser, aufn)
            elif args.nur == "ruhmeshalle":
                ruhmeshalle_ablauf(browser, aufn)
            else:
                seiten_ablauf(browser, aufn)
            browser.close()
        berichte(aufn, ziel)
        print(f"{len(aufn.dateien)} Screenshots in {ziel}")
    finally:
        server_stoppen(proc)


if __name__ == "__main__":
    main()
