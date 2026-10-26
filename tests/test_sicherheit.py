"""Querschnitt Sicherheit (Review AP19): CSP-Header und CSP-taugliche Templates."""

import re
from pathlib import Path

import pytest
from django.conf import settings

from nestwerk.sicherheit import CSP

WURZEL = Path(settings.BASE_DIR)
INLINE_SKRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
INLINE_STYLE = re.compile(r"\sstyle\s*=|<style", re.IGNORECASE)
# Ausnahmen: E-Mail-HTML (kein Browser-Kontext der App), Offline-Seite (eigene CSP)
STYLE_AUSNAHMEN = {"email.html", "offline.html"}


def _templates():
    for ordner in [WURZEL / "templates", *sorted((WURZEL / "apps").glob("*/templates"))]:
        yield from ordner.rglob("*.html")


@pytest.mark.django_db
def test_csp_header_auf_seiten(client):
    """Regression B-03: ARCHITECTURE 4.5 verlangt CSP ohne Inline-Skripte; es gab keinen Header."""
    antwort = client.get("/anmelden/eltern/")
    csp = antwort["Content-Security-Policy"]
    assert csp == CSP
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.django_db
def test_offline_seite_hat_eigene_policy_ohne_skript(client):
    antwort = client.get("/offline/")
    assert antwort.status_code == 200
    assert "script-src" not in antwort["Content-Security-Policy"]
    html = antwort.content.decode()
    assert not INLINE_HANDLER.search(html) and "<script" not in html


def test_templates_ohne_inline_skripte_und_handler():
    verstoesse = []
    for pfad in _templates():
        text = pfad.read_text(encoding="utf-8")
        if INLINE_SKRIPT.search(text) or INLINE_HANDLER.search(text):
            verstoesse.append(str(pfad.relative_to(WURZEL)))
        if pfad.name not in STYLE_AUSNAHMEN and INLINE_STYLE.search(text):
            verstoesse.append(f"{pfad.relative_to(WURZEL)} (style)")
    assert verstoesse == []


# htmx wertet diese Formen per eval/Function aus: Trigger-Filter "[...]", hx-on*, "js:"/
# "javascript:" in hx-vals/hx-vars/hx-headers. Mit CSP ohne 'unsafe-eval' scheitern sie (Review
# AP31: Tablet-Polling mit Sichtbarkeitsfilter erzeugte EvalError auf jeder Tablet-Seite).
HTMX_EVAL = re.compile(
    r"""hx-trigger\s*=\s*["'][^"']*\[|\shx-on[:\-]|\shx-vars\s*=|["']\s*(?:js|javascript):""",
    re.IGNORECASE,
)


def test_templates_ohne_htmx_eval():
    verstoesse = [
        str(pfad.relative_to(WURZEL))
        for pfad in _templates()
        if HTMX_EVAL.search(pfad.read_text(encoding="utf-8"))
    ]
    assert verstoesse == []


def test_htmx_eval_ist_abgeschaltet_und_csp_ohne_unsafe_eval():
    basis = (WURZEL / "templates/basis/basis.html").read_text(encoding="utf-8")
    assert '"allowEval": false' in basis
    assert "unsafe-eval" not in CSP


def test_polling_pausiert_per_skript_statt_filter():
    """Die Sichtbarkeitspause liegt in nestwerk.js (``data-nur-sichtbar``), nicht im Trigger."""
    tablet = (WURZEL / "apps/oberflaeche/templates/oberflaeche/tablet.html").read_text("utf-8")
    assert "data-nur-sichtbar" in tablet
    js = (WURZEL / "static/js/nestwerk.js").read_text(encoding="utf-8")
    assert "data-nur-sichtbar" in js and "htmx:beforeRequest" in js
