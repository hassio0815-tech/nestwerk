"""SVG-Whitelist für Mod-Overrides und gerenderte Avatare.

Der Sanitizer liegt seit Review AP31 gemeinsam in ``apps.kern.svg`` (auch für Abzeichen); hier
nur die Avatar-Fläche ``viewBox 0 0 32 48`` ohne Verläufe.
"""

from apps.kern import svg as _svg
from apps.kern.svg import ATTRIBUTE, ELEMENTE, ROOT_ATTRIBUTE, SvgUnzulaessig  # noqa: F401

FLAECHE = (32, 48)
VIEWBOX = (0, 0, *FLAECHE)


def svg_bereinigen(text):
    return _svg.svg_bereinigen(text, viewbox=VIEWBOX)


def svg_pruefen(text):
    return _svg.svg_pruefen(text, viewbox=VIEWBOX)
