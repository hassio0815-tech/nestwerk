"""Gemeinsamer Whitelist-Sanitizer für SVG (Review AP31; vorher ``avatar.generator.svgsicher``).

Nutzer: Avatar/Mods (``viewBox 0 0 32 48``, Overrides der Eltern) und Abzeichen-Grafiken
(``viewBox 0 0 64 64``, Repo-Assets mit optionalen Verläufen). Später z. B. Eltern-Uploads.

Es wird nie das Original weitergereicht: ``svg_bereinigen`` parst, prüft jedes Element und
Attribut gegen die Whitelist und serialisiert das Ergebnis neu (kanonisch, Attribute sortiert).
Alles Unbekannte wird abgewiesen (nicht stillschweigend entfernt): ``<script>``, ``on*``-Attribute,
``href``/``xlink:href``, ``foreignObject``, ``style``, Entities/DOCTYPE, Animationen.

- ``viewbox``: erlaubte Wurzel-viewBox als Tupel ``(x, y, breite, hoehe)`` oder ``None`` (keine
  viewBox-Prüfung, nur Zahlen).
- ``verlaeufe=True``: zusätzlich ``defs``, ``linearGradient``, ``radialGradient``, ``stop`` mit
  ``id``, Koordinaten, ``offset``, ``stop-color``, ``stop-opacity``, ``gradientUnits``; ``fill``
  darf dann ``url(#id)`` auf einen **im selben Dokument definierten** Verlauf zeigen (keine
  externen Referenzen).

Zum Parsen dient ``xml.etree`` (keine externen Entities). Gegen Entity-Expansion werden DOCTYPE,
ENTITY und Verarbeitungsanweisungen schon vor dem Parsen abgewiesen; zusätzlich gelten Größen-,
Tiefen- und Elementgrenzen.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # noqa: S405  (DOCTYPE/ENTITY werden vorher abgewiesen)

SVG_NS = "http://www.w3.org/2000/svg"
MAX_ZEICHEN = 40_000
MAX_ELEMENTE = 400
MAX_TIEFE = 6

ELEMENTE = frozenset({"svg", "g", "rect", "path", "polygon", "circle"})
ATTRIBUTE = frozenset(
    {"fill", "x", "y", "width", "height", "d", "points", "transform", "opacity", "cx", "cy", "r"}
)
ROOT_ATTRIBUTE = frozenset({"viewBox", "shape-rendering"})

VERLAUF_ELEMENTE = frozenset({"defs", "linearGradient", "radialGradient", "stop"})
VERLAUF_ATTRIBUTE = frozenset(
    {
        "id",
        "x1",
        "y1",
        "x2",
        "y2",
        "fx",
        "fy",
        "offset",
        "stop-color",
        "stop-opacity",
        "gradientUnits",
    }
)

_ZAHL = r"-?\d{1,4}(?:\.\d{1,3})?"
_ZAHL_RE = re.compile(rf"^{_ZAHL}$")
_PROZENT_RE = re.compile(rf"^{_ZAHL}%?$")
_FARBE_RE = re.compile(r"^(?:none|#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6})$")
_URL_RE = re.compile(r"^url\(#([A-Za-z][A-Za-z0-9_-]{0,40})\)$")
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,40}$")
_PFAD_RE = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s+\-]{0,8000}$")
_PUNKTE_RE = re.compile(r"^[0-9eE.,\s+\-]{0,1000}$")
_TRANSFORM_RE = re.compile(
    rf"^(?:(?:translate|scale|rotate)\(\s*{_ZAHL}(?:[\s,]+{_ZAHL}){{0,2}}\s*\)\s*){{1,4}}$"
)
_ZAHL_ATTRIBUTE = frozenset({"x", "y", "width", "height", "cx", "cy", "r"})
_PROZENT_ATTRIBUTE = frozenset({"x1", "y1", "x2", "y2", "fx", "fy", "offset"})

AVATAR_VIEWBOX = (0, 0, 32, 48)


class SvgUnzulaessig(ValueError):
    """Das SVG enthält etwas, das nicht auf der Whitelist steht."""


class _Pruefung:
    def __init__(self, viewbox, verlaeufe):
        self.viewbox = viewbox
        self.verlaeufe = verlaeufe
        self.elemente = ELEMENTE | VERLAUF_ELEMENTE if verlaeufe else ELEMENTE
        self.attribute = ATTRIBUTE | VERLAUF_ATTRIBUTE if verlaeufe else ATTRIBUTE
        self.zaehler = 0
        self.ids = set()
        self.verweise = set()

    def _lokal(self, name):
        """Lokaler Name eines Tags/Attributs; fremde Namensräume werden abgewiesen."""
        if name.startswith("{"):
            ns, _, lokal = name[1:].partition("}")
            if ns != SVG_NS:
                raise SvgUnzulaessig(f"Fremder Namensraum nicht erlaubt: {ns}")
            return lokal
        return name

    def _wurzel_attribut(self, name, wert):
        if name not in ROOT_ATTRIBUTE:
            raise SvgUnzulaessig(f"Attribut nicht erlaubt am svg-Element: {name}")
        if name == "viewBox":
            teile = wert.split()
            if len(teile) != 4 or not all(_ZAHL_RE.match(t) for t in teile):
                raise SvgUnzulaessig("viewBox: vier Zahlen erwartet")
            if self.viewbox is not None and [float(t) for t in teile] != [
                float(v) for v in self.viewbox
            ]:
                soll = " ".join(str(v) for v in self.viewbox)
                raise SvgUnzulaessig(f"viewBox muss {soll} sein")
        elif wert not in ("crispEdges", "auto", "optimizeSpeed", "geometricPrecision"):
            raise SvgUnzulaessig("shape-rendering: crispEdges, auto, optimizeSpeed o. ä.")

    def _attribut(self, name, wert, root):
        if name.startswith("{") or ":" in name:
            raise SvgUnzulaessig(f"Attribut mit Namensraum nicht erlaubt: {name}")
        kleinschrift = name.lower()
        if kleinschrift.startswith("on"):
            raise SvgUnzulaessig(f"Ereignis-Attribut nicht erlaubt: {name}")
        if kleinschrift == "href":
            raise SvgUnzulaessig("href/Referenzen sind nicht erlaubt")
        if root:
            return self._wurzel_attribut(name, wert)
        if name not in self.attribute:
            raise SvgUnzulaessig(f"Attribut nicht erlaubt: {name}")
        if name in ("fill", "stop-color"):
            treffer = _URL_RE.match(wert) if self.verlaeufe and name == "fill" else None
            if treffer:
                self.verweise.add(treffer.group(1))
                ok = True
            else:
                ok = _FARBE_RE.match(wert)
        elif name in _ZAHL_ATTRIBUTE:
            ok = _ZAHL_RE.match(wert)
        elif name in _PROZENT_ATTRIBUTE:
            ok = _PROZENT_RE.match(wert)
        elif name in ("opacity", "stop-opacity"):
            ok = _ZAHL_RE.match(wert) and 0 <= float(wert) <= 1
        elif name == "d":
            ok = _PFAD_RE.match(wert)
        elif name == "points":
            ok = _PUNKTE_RE.match(wert)
        elif name == "id":
            ok = _ID_RE.match(wert) and wert not in self.ids
            self.ids.add(wert)
        elif name == "gradientUnits":
            ok = wert in ("userSpaceOnUse", "objectBoundingBox")
        else:  # transform
            ok = _TRANSFORM_RE.match(wert)
        if not ok:
            raise SvgUnzulaessig(f"Wert nicht erlaubt für {name}: {wert[:40]!r}")

    def _knoten(self, element, tiefe):
        self.zaehler += 1
        if self.zaehler > MAX_ELEMENTE:
            raise SvgUnzulaessig(f"Zu viele Elemente (max. {MAX_ELEMENTE})")
        if tiefe > MAX_TIEFE:
            raise SvgUnzulaessig(f"Zu tief verschachtelt (max. {MAX_TIEFE})")
        tag = self._lokal(element.tag)
        if tag not in self.elemente:
            raise SvgUnzulaessig(f"Element nicht erlaubt: <{tag}>")
        if (element.text or "").strip() or (element.tail or "").strip():
            raise SvgUnzulaessig("Text im SVG nicht erlaubt")
        for name, wert in element.attrib.items():
            self._attribut(name, wert, root=tiefe == 0)
        if tiefe > 0 and tag == "svg":
            raise SvgUnzulaessig("Verschachteltes <svg> nicht erlaubt")
        return tag

    def serialisieren(self, element, tiefe=0):
        tag = self._knoten(element, tiefe)
        kinder = [self.serialisieren(k, tiefe + 1) for k in element]
        attribute = "".join(f' {n}="{w.strip()}"' for n, w in sorted(element.attrib.items()))
        if tiefe == 0:
            fehlend = self.verweise - self.ids
            if fehlend:
                raise SvgUnzulaessig(f"Verweis auf unbekannten Verlauf: {sorted(fehlend)[0]}")
            return "".join(kinder)
        if kinder:
            return f"<{tag}{attribute}>{''.join(kinder)}</{tag}>"
        return f"<{tag}{attribute}/>"


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


def svg_bereinigen(text, *, viewbox=AVATAR_VIEWBOX, verlaeufe=False):
    """Prüft ``text`` (ein ``<svg>``-Dokument) und liefert den kanonisierten Inhalt (Kinder des
    Wurzelelements als Markup). Wirft ``SvgUnzulaessig`` bei jedem Verstoß."""
    _vorab_pruefen(text)
    try:
        wurzel = ET.fromstring(text)  # noqa: S314
    except ET.ParseError as exc:
        raise SvgUnzulaessig(f"Kein gültiges XML: {exc}") from exc
    pruefung = _Pruefung(viewbox, verlaeufe)
    if pruefung._lokal(wurzel.tag) != "svg":
        raise SvgUnzulaessig("Wurzelelement muss <svg> sein")
    return pruefung.serialisieren(wurzel)


def svg_pruefen(text, **optionen):
    """``None`` wenn zulässig, sonst die Fehlermeldung (für Formulare/Befehle)."""
    try:
        svg_bereinigen(text, **optionen)
    except SvgUnzulaessig as exc:
        return str(exc)
    return None
