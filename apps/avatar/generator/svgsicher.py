"""Whitelist-Prüfung für SVG (Mod-Overrides, später Eltern-Uploads).

Es wird nie das Original weitergereicht: ``svg_bereinigen`` parst, prüft jedes Element und
Attribut gegen die Whitelist und serialisiert das Ergebnis neu (kanonisch, Attribute sortiert).
Alles Unbekannte wird abgewiesen (nicht stillschweigend entfernt): ``<script>``,
``on*``-Attribute, ``href``/``xlink:href``, ``foreignObject``, ``style``, Entities/DOCTYPE.

Zum Parsen dient ``xml.etree`` (keine externen Entities). Gegen Entity-Expansion werden DOCTYPE,
ENTITY und Verarbeitungsanweisungen schon vor dem Parsen abgewiesen; zusätzlich gelten Größen-,
Tiefen- und Elementgrenzen.
"""

import re
import xml.etree.ElementTree as ET  # noqa: S405  (DOCTYPE/ENTITY werden vorher abgewiesen)

SVG_NS = "http://www.w3.org/2000/svg"
MAX_ZEICHEN = 40_000
MAX_ELEMENTE = 400
MAX_TIEFE = 6
FLAECHE = (32, 48)

ELEMENTE = frozenset({"svg", "g", "rect", "path", "polygon", "circle"})
ATTRIBUTE = frozenset(
    {"fill", "x", "y", "width", "height", "d", "points", "transform", "opacity", "cx", "cy", "r"}
)
ROOT_ATTRIBUTE = frozenset({"viewBox", "shape-rendering"})

_ZAHL = r"-?\d{1,4}(?:\.\d{1,3})?"
_ZAHL_RE = re.compile(rf"^{_ZAHL}$")
_FILL_RE = re.compile(r"^(?:none|#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6})$")
_PFAD_RE = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s+\-]{0,8000}$")
_PUNKTE_RE = re.compile(r"^[0-9eE.,\s+\-]{0,1000}$")
_TRANSFORM_RE = re.compile(
    rf"^(?:(?:translate|scale|rotate)\(\s*{_ZAHL}(?:[\s,]+{_ZAHL}){{0,2}}\s*\)\s*){{1,4}}$"
)
_ZAHL_ATTRIBUTE = frozenset({"x", "y", "width", "height", "cx", "cy", "r"})


class SvgUnzulaessig(ValueError):
    """Das SVG enthält etwas, das nicht auf der Whitelist steht."""


def _lokal(name):
    """Lokaler Name eines Tags/Attributs; fremde Namensräume werden abgewiesen."""
    if name.startswith("{"):
        ns, _, lokal = name[1:].partition("}")
        if ns != SVG_NS:
            raise SvgUnzulaessig(f"Fremder Namensraum nicht erlaubt: {ns}")
        return lokal
    return name


def _attribut_pruefen(name, wert, root):
    if name.startswith("{") or ":" in name:
        raise SvgUnzulaessig(f"Attribut mit Namensraum nicht erlaubt: {name}")
    kleinschrift = name.lower()
    if kleinschrift.startswith("on"):
        raise SvgUnzulaessig(f"Ereignis-Attribut nicht erlaubt: {name}")
    if kleinschrift == "href":
        raise SvgUnzulaessig("href/Referenzen sind nicht erlaubt")
    if root:
        if name not in ROOT_ATTRIBUTE:
            raise SvgUnzulaessig(f"Attribut nicht erlaubt am svg-Element: {name}")
        if name == "viewBox" and wert.split() != ["0", "0", str(FLAECHE[0]), str(FLAECHE[1])]:
            raise SvgUnzulaessig(f"viewBox muss 0 0 {FLAECHE[0]} {FLAECHE[1]} sein")
        if name == "shape-rendering" and wert not in ("crispEdges", "auto", "optimizeSpeed"):
            raise SvgUnzulaessig("shape-rendering: nur crispEdges, auto oder optimizeSpeed")
        return
    if name not in ATTRIBUTE:
        raise SvgUnzulaessig(f"Attribut nicht erlaubt: {name}")
    if name == "fill":
        ok = _FILL_RE.match(wert)
    elif name in _ZAHL_ATTRIBUTE:
        ok = _ZAHL_RE.match(wert)
    elif name == "opacity":
        ok = _ZAHL_RE.match(wert) and 0 <= float(wert) <= 1
    elif name == "d":
        ok = _PFAD_RE.match(wert)
    elif name == "points":
        ok = _PUNKTE_RE.match(wert)
    else:  # transform
        ok = _TRANSFORM_RE.match(wert)
    if not ok:
        raise SvgUnzulaessig(f"Wert nicht erlaubt für {name}: {wert[:40]!r}")


def _vorab_pruefen(text):
    if not isinstance(text, str) or not text.strip():
        raise SvgUnzulaessig("Leeres SVG")
    if len(text) > MAX_ZEICHEN:
        raise SvgUnzulaessig(f"SVG zu groß (max. {MAX_ZEICHEN} Zeichen)")
    if "<?" in text:
        raise SvgUnzulaessig("Verarbeitungsanweisungen (<?...?>) nicht erlaubt")
    if re.search(r"<!(?!--)", text):
        raise SvgUnzulaessig("DOCTYPE/ENTITY/CDATA nicht erlaubt")
    if "&" in text.replace("&amp;", "").replace("&lt;", "").replace("&gt;", ""):
        raise SvgUnzulaessig("Entities nicht erlaubt")


def _knoten(element, tiefe, zaehler):
    zaehler[0] += 1
    if zaehler[0] > MAX_ELEMENTE:
        raise SvgUnzulaessig(f"Zu viele Elemente (max. {MAX_ELEMENTE})")
    if tiefe > MAX_TIEFE:
        raise SvgUnzulaessig(f"Zu tief verschachtelt (max. {MAX_TIEFE})")
    tag = _lokal(element.tag)
    if tag not in ELEMENTE:
        raise SvgUnzulaessig(f"Element nicht erlaubt: <{tag}>")
    if (element.text or "").strip() or (element.tail or "").strip():
        raise SvgUnzulaessig("Text im SVG nicht erlaubt")
    for name, wert in element.attrib.items():
        _attribut_pruefen(name, wert, root=tiefe == 0)
    if tiefe > 0 and tag == "svg":
        raise SvgUnzulaessig("Verschachteltes <svg> nicht erlaubt")
    return tag


def _serialisieren(element, tiefe, zaehler):
    tag = _knoten(element, tiefe, zaehler)
    kinder = [_serialisieren(k, tiefe + 1, zaehler) for k in element]
    attribute = "".join(f' {n}="{w.strip()}"' for n, w in sorted(element.attrib.items()))
    if tiefe == 0:
        return "".join(kinder)
    if kinder:
        return f"<{tag}{attribute}>{''.join(kinder)}</{tag}>"
    return f"<{tag}{attribute}/>"


def svg_bereinigen(text):
    """Prüft ``text`` (ein ``<svg>``-Dokument) und liefert den kanonisierten Inhalt (Kinder des
    Wurzelelements als Markup). Wirft ``SvgUnzulaessig`` bei jedem Verstoß."""
    _vorab_pruefen(text)
    try:
        wurzel = ET.fromstring(text)  # noqa: S314
    except ET.ParseError as exc:
        raise SvgUnzulaessig(f"Kein gültiges XML: {exc}") from exc
    if _lokal(wurzel.tag) != "svg":
        raise SvgUnzulaessig("Wurzelelement muss <svg> sein")
    return _serialisieren(wurzel, 0, [0])


def svg_pruefen(text):
    """``None`` wenn zulässig, sonst die Fehlermeldung (für Formulare/Befehle)."""
    try:
        svg_bereinigen(text)
    except SvgUnzulaessig as exc:
        return str(exc)
    return None
