"""Querschnitt Sicherheit (Review AP19): CSP-Header und CSP-taugliche Templates."""

import re
from pathlib import Path

import pytest
from django.conf import settings

from famko.sicherheit import CSP

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
