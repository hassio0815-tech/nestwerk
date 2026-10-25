#!/usr/bin/env python
"""Baut alle Nestwerk-Logo-Dateien (SVG + PNG + ICO). Aufruf: .venv/bin/python branding/nestwerk/build.py
Eigene Neuzeichnung nach Nutzer-Vorlage. Schrift: Inter (OFL), als Pfade eingebettet."""
import io, math, pathlib
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
import uharfbuzz as hb

OUT = pathlib.Path(__file__).parent
FONTS = OUT.parent.parent / "static/fonts/inter"
TOP, BOT, MAIN = "#3AAFC6", "#0E6A80", "#1B8DA6"
PURPLE, ICE = "#33205A", "#DDF3F8"
DARKBG, LIGHTBG = "#0C2A33", "#F4F8F9"
SUB = ["the family hub for chores,", "rewards & learning"]


def load(name):
    f = TTFont(FONTS / name)
    f.flavor = None
    buf = io.BytesIO(); f.save(buf)
    face = hb.Face(buf.getvalue())
    return f, hb.Font(face), face.upem


FONT_CACHE = {n: load(n) for n in ("Inter-Bold.woff2", "Inter-Regular.woff2")}


def text_path(txt, font, size, track=0.0):
    """Gibt (d, breite) zurueck; Ursprung links auf Grundlinie y=0."""
    tt, hbf, upem = FONT_CACHE[font]
    buf = hb.Buffer(); buf.add_str(txt); buf.guess_segment_properties()
    hb.shape(hbf, buf, {"kern": True, "liga": False})
    order = tt.getGlyphOrder(); gs = tt.getGlyphSet()
    s = size / upem
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    x = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        g = order[info.codepoint]
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x + pos.x_offset * s, 0)))
        x += pos.x_advance * s + track * size
    return pen.getCommands(), x - track * size


def text_el(txt, font, size, x, y, fill, anchor="start", track=0.0):
    d, w = text_path(txt, font, size, track)
    dx = {"start": 0, "middle": -w / 2, "end": -w}[anchor]
    return f'<path transform="translate({x + dx:.1f} {y:.1f})" fill="{fill}" d="{d}"/>', w


def arc(cx, cy, r, start, sweep, w, op):
    a0, a1 = math.radians(start), math.radians(start + sweep)
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if sweep > 180 else 0
    return (f'<path d="M{x0:.1f} {y0:.1f}A{r} {r} 0 {large} 1 {x1:.1f} {y1:.1f}" fill="none" '
            f'stroke="#fff" stroke-opacity="{op}" stroke-width="{w}" stroke-linecap="round"/>')


# Winkel in SVG-Richtung (0=rechts, 90=unten, -50 = oben rechts). Oeffnung oben rechts.
RING_FULL = [
    (256, 256, 170, 8, 345, 7, 0.55),
    (254, 258, 150, -4, 322, 9, 0.8),
    (257, 256, 136, 40, 250, 4, 0.5),
    (258, 255, 124, -22, 302, 18, 1.0),
    (255, 257, 99, 12, 262, 6, 0.75),
]
RING_SMALL = [
    (256, 256, 160, -28, 308, 40, 1.0),
    (256, 256, 90, -8, 276, 34, 0.9),
]


def ring(items, scale=1.0):
    body = "".join(arc(*i) for i in items)
    if scale == 1.0:
        return body
    t = 256 * (1 - scale)
    return f'<g transform="translate({t:.1f} {t:.1f}) scale({scale})">{body}</g>'


def defs(uid):
    return (f'<linearGradient id="g{uid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{TOP}"/><stop offset="1" stop-color="{BOT}"/></linearGradient>')


def icon_group(uid, small=False, rx=116):
    r = ring(RING_SMALL if small else RING_FULL)
    return f'<rect width="512" height="512" rx="{rx}" fill="url(#g{uid})"/>{r}'


def svg(w, h, body, uid, title, bg=None, d=True):
    bgr = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{title}"><title>{title}</title><defs>{defs(uid)}</defs>{bgr}{body}</svg>\n')


def place_icon(uid, x, y, size, small=False):
    return f'<g transform="translate({x} {y}) scale({size / 512:.4f})">{icon_group(uid, small)}</g>'


def vertical(dark):
    name_c = ICE if dark else PURPLE
    sub_c = ICE if dark else PURPLE
    parts = [place_icon("v", 345, 120, 310)]
    n, _ = text_el("Nestwerk", "Inter-Bold.woff2", 160, 500, 690, name_c, "middle", -0.01)
    parts.append(n)
    for i, line in enumerate(SUB):
        e, _ = text_el(line, "Inter-Regular.woff2", 46, 500, 800 + i * 66, sub_c, "middle", 0.045)
        parts.append(e)
    return svg(1000, 1000, "".join(parts), "v", "Nestwerk – the family hub for chores, rewards &amp; learning",
               DARKBG if dark else None)


def horizontal(dark, sub=True):
    c = ICE if dark else PURPLE
    parts = [place_icon("h", 40, 40, 320)]
    n, w = text_el("Nestwerk", "Inter-Bold.woff2", 200, 410, 245, c, "start", -0.01)
    parts.append(n)
    e, w2 = text_el("the family hub for chores, rewards & learning", "Inter-Regular.woff2", 40, 416, 315, c, "start", 0.03)
    parts.append(e)
    W = int(max(410 + w, 416 + w2) + 60)
    return svg(W, 400, "".join(parts), "h", "Nestwerk – the family hub for chores, rewards &amp; learning",
               DARKBG if dark else None)


def wordmark():
    n, w = text_el("Nestwerk", "Inter-Bold.woff2", 200, 20, 170, PURPLE, "start", -0.01)
    return svg(int(w + 40), 230, n, "w", "Nestwerk")


def icon_svg(small=False, rx=116):
    return svg(512, 512, icon_group("i", small, rx), "i", "Nestwerk Icon")


def maskable():
    r = ring(RING_FULL, 0.78)
    return svg(512, 512, f'<rect width="512" height="512" fill="url(#gm)"/>{r}', "m", "Nestwerk Icon (maskable)")


def social():
    parts = []
    h = horizontal(False)
    # Logo horizontal zentriert auf 1280x640
    inner = h[h.index("</defs>") + 7:h.rindex("</svg>")]
    wv = int(h.split('viewBox="0 0 ')[1].split()[0])
    sc = 1080 / wv
    tx, ty = (1280 - wv * sc) / 2, (640 - 400 * sc) / 2
    body = f'<g transform="translate({tx:.1f} {ty:.1f}) scale({sc})">{inner}</g>'
    return svg(1280, 640, body, "h", "Nestwerk", LIGHTBG)


def main():
    files = {
        "icon.svg": icon_svg(), "icon-klein.svg": icon_svg(True, 100),
        "logo-vertikal.svg": vertical(False), "logo-vertikal-dunkel.svg": vertical(True),
        "logo-horizontal.svg": horizontal(False), "logo-horizontal-dunkel.svg": horizontal(True),
        "wortmarke.svg": wordmark(), "_maskable.svg": maskable(), "_social.svg": social(),
    }
    # social nutzt Gradient-ID h – bereits in defs; maskable-ID gm
    files["_maskable.svg"] = files["_maskable.svg"].replace('id="gm"', 'id="gm"').replace(
        "<defs>" + defs("m"), "<defs>" + defs("m"))
    for n, s in files.items():
        (OUT / n).write_text(s)
    from playwright.sync_api import sync_playwright
    from PIL import Image
    def shot(pg, name, svgfile, w, h, transparent=True):
        pg.set_viewport_size({"width": w, "height": h})
        s = (OUT / svgfile).read_text().replace(' width="', ' data-w="', 1).replace(' height="', ' data-h="', 1)
        pg.set_content(f'<body style="margin:0;background:transparent"><div style="width:{w}px;height:{h}px">'
                       f'{s.replace("<svg ", "<svg style=\"width:100%;height:100%\" ", 1)}</div></body>')
        pg.screenshot(path=str(OUT / name), omit_background=transparent)
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        for sz in (16, 32, 48):
            shot(pg, f"favicon-{sz}.png", "icon-klein.svg" if sz <= 32 else "icon.svg", sz, sz)
        shot(pg, "apple-touch-icon-180.png", "icon.svg", 180, 180)
        shot(pg, "icon-192.png", "icon.svg", 192, 192)
        shot(pg, "icon-512.png", "icon.svg", 512, 512)
        shot(pg, "icon-maskable-512.png", "_maskable.svg", 512, 512)
        shot(pg, "social-preview-1280x640.png", "_social.svg", 1280, 640, False)
        shot(pg, "logo-vertikal-1000.png", "logo-vertikal.svg", 1000, 1000)
        b.close()
    ims = [Image.open(OUT / f"favicon-{s}.png").convert("RGBA") for s in (16, 32, 48)]
    ims[2].save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=ims[:2])
    for n in ("_maskable.svg", "_social.svg"):
        (OUT / n).unlink()


if __name__ == "__main__":
    main()
