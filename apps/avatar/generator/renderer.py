"""Deterministischer SVG-Renderer: gleiche Eingabe liefert ein byte-gleiches SVG.

Eingabe (``zustand``)::

    {"thema": "ritter",
     "figur": {"haut": "haut2", "haar": "haar3", "frisur": "kurz"},
     "mods": {"kopf": {"teile": [...], "svg_override": None}, ...},   # nur fertige Mods
     "thema_daten": {...}}     # optional: Thema aus der DB statt aus der Bibliothek

Ebenen von unten nach oben: Hintergrund, Rücken, Figur, Körper, Kopf, Hand, Begleiter. Ein
nicht belegter Slot zeigt die Grundausstattung des Themas. Alle Koordinaten sind ganze Zahlen
auf dem Raster 32 x 48; es gibt weder Skripte noch externe Referenzen noch ``style``.
"""

import hashlib
import json

from . import bibliothek, farben, svgsicher

RENDER_VERSION = 1
BREITE, HOEHE = 32, 48
MAX_RECHTECKE = 1500
MAX_TEILE = 6

WURZEL = (
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BREITE} {HOEHE}" '
    'shape-rendering="crispEdges">'
)


class RenderFehler(ValueError):
    """Eingabe oder Bibliothek sind inkonsistent (unbekannte Form, Farbe, Thema ...)."""


# --- Eingabe -----------------------------------------------------------------------------------


def zustand_normalisieren(zustand):
    """Kanonische Form der Eingabe (Standardwerte, sortierte Schlüssel, nur bekannte Slots)."""
    figur = {**bibliothek.STANDARD_FIGUR, **(zustand.get("figur") or {})}
    kanon = {
        "thema": zustand["thema"],
        "figur": {k: figur[k] for k in ("haut", "haar", "frisur")},
        "mods": {},
    }
    erlaubt = bibliothek.slot_schluessel()
    for slot, mod in sorted((zustand.get("mods") or {}).items()):
        if slot not in erlaubt:
            raise RenderFehler(f"Unbekannter Slot: {slot!r}")
        if mod:
            kanon["mods"][slot] = {
                "teile": list(mod.get("teile") or []),
                "svg_override": mod.get("svg_override") or None,
            }
    if zustand.get("thema_daten"):
        kanon["thema_daten"] = zustand["thema_daten"]
    return kanon


def hash_von(zustand):
    """SHA-256 über die kanonische Eingabe plus Renderer- und Bibliotheksversion."""
    text = json.dumps(
        {"r": RENDER_VERSION, "b": bibliothek.version(), "z": zustand_normalisieren(zustand)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(text.encode("ascii")).hexdigest()


# --- Primitive -> Rechtecke --------------------------------------------------------------------


class _Gruppe:
    """Sammelt Rechtecke einer Ebene: erst alle Umrisse, dann alle Füllungen."""

    def __init__(self, umriss):
        self.umriss_farbe = umriss
        self.umrisse = []
        self.fuellungen = []

    def rechtecke(self):
        return self.umrisse + self.fuellungen


def _prim_aufloesen(prim, scope, dx, dy, spiegeln, gruppe):
    try:
        typ, x, y, w, h, farbe, *rest = prim
    except ValueError:
        raise RenderFehler(f"Ungültiges Primitiv: {prim!r}") from None
    flags = rest[0] if rest else ""
    if typ not in ("r", "b") or not all(isinstance(v, int) for v in (x, y, w, h)):
        raise RenderFehler(f"Ungültiges Primitiv: {prim!r}")
    try:
        hexfarbe, deckung = farben.aufloesen(farbe, scope)
    except farben.FarbFehler as exc:
        raise RenderFehler(str(exc)) from exc
    varianten = [(x, y)]
    if "m" in flags:
        varianten.append((BREITE - x - w, y))
    for vx, vy in varianten:
        if spiegeln:
            vx = BREITE - vx - w
        vx, vy = vx + dx, vy + dy
        if "o" in flags:
            gruppe.umrisse.append((vx - 1, vy - 1, w + 2, h + 2, gruppe.umriss_farbe, 100))
        gruppe.fuellungen.append((vx, vy, w, h, hexfarbe, deckung))
        if typ == "b" and "n" not in flags and deckung == 100 and w >= 3 and h >= 3:
            hell, dunkel = farben.heller(hexfarbe, 22), farben.dunkler(hexfarbe, 22)
            gruppe.fuellungen.append((vx, vy, w, 1, hell, 100))
            gruppe.fuellungen.append((vx + w - 1, vy + 1, 1, h - 1, dunkel, 100))
            gruppe.fuellungen.append((vx, vy + h - 1, w - 1, 1, dunkel, 100))


def _muster(name, flaeche, farbe, deckung, gruppe):
    """Prozedurale Muster innerhalb der Fläche einer Form (kein Clip-Pfad nötig)."""
    fx, fy, fw, fh = flaeche
    ziel = gruppe.fuellungen
    start = len(ziel)

    def punkt(x, y, w=1, h=1, f=farbe, d=deckung):
        if len(ziel) - start < 160:
            ziel.append((x, y, w, h, f, d))

    if name == "kante":
        punkt(fx, fy, fw, 1)
        punkt(fx, fy + fh - 1, fw, 1)
        punkt(fx, fy + 1, 1, fh - 2)
        punkt(fx + fw - 1, fy + 1, 1, fh - 2)
    elif name == "streifen":
        for y in range(fy + 1, fy + fh, 2):
            punkt(fx, y, fw, 1)
    elif name == "punkte":
        for y in range(fy + 1, fy + fh, 3):
            for x in range(fx + 1, fx + fw, 3):
                punkt(x, y)
    elif name == "karo":
        for j, y in enumerate(range(fy, fy + fh, 2)):
            for i, x in enumerate(range(fx, fx + fw, 2)):
                if (i + j) % 2 == 0:
                    punkt(x, y, min(2, fx + fw - x), min(2, fy + fh - y))
    elif name == "glanz":
        for versatz in range(-fh, fw, 5):
            for i in range(fh):
                x = fx + versatz + i
                if fx <= x < fx + fw:
                    punkt(x, fy + i, 1, 1, "#ffffff", 38)
    elif name != "keins":
        raise RenderFehler(f"Unbekanntes Muster: {name!r}")


def _teil(teil, slot, scope, gruppe):
    """Ein Teil (Form + Parameter, oder Pixelbild) in die Gruppe zeichnen."""
    if not isinstance(teil, dict):
        raise RenderFehler(f"Teil muss ein Objekt sein: {teil!r}")
    dx, dy = teil.get("dx", 0), teil.get("dy", 0)
    if not all(isinstance(v, int) and -8 <= v <= 8 for v in (dx, dy)):
        raise RenderFehler("dx/dy müssen ganze Zahlen von -8 bis 8 sein")
    spiegeln = bool(teil.get("spiegeln"))
    try:
        if "bild" in teil:
            _bild(teil, scope, dx, dy, spiegeln, gruppe)
            return
        form = bibliothek.form(slot, teil["form"])
    except KeyError as exc:
        raise RenderFehler(str(exc.args[0])) from exc
    lokal = dict(scope)
    standard = {"a": "p1", "b": "p2", "c": "p3"}
    angaben = {**standard, **(teil.get("farben") or {})}
    for kurz, angabe in angaben.items():
        if kurz not in standard:
            raise RenderFehler(f"Unbekannter Farbplatzhalter: {kurz!r}")
        try:
            hexfarbe, deckung = farben.aufloesen(angabe, scope)
        except farben.FarbFehler as exc:
            raise RenderFehler(str(exc)) from exc
        if deckung != 100:
            raise RenderFehler(f"Platzhalter {kurz!r}: Deckkraft hier nicht erlaubt")
        lokal[kurz] = hexfarbe
    for prim in form["prims"]:
        _prim_aufloesen(prim, lokal, dx, dy, spiegeln, gruppe)
    muster = teil.get("muster", "keins")
    if muster != "keins":
        fx, fy, fw, fh = form["flaeche"]
        if spiegeln:
            fx = BREITE - fx - fw
        try:
            hexfarbe, deckung = farben.aufloesen(teil.get("muster_farbe", "b"), lokal)
        except farben.FarbFehler as exc:
            raise RenderFehler(str(exc)) from exc
        _muster(muster, (fx + dx, fy + dy, fw, fh), hexfarbe, deckung, gruppe)


def _bild(teil, scope, dx, dy, spiegeln, gruppe):
    zeilen = teil["bild"]
    palette = {}
    for zeichen, angabe in (teil.get("farben") or {}).items():
        try:
            palette[zeichen] = farben.aufloesen(angabe, scope)
        except farben.FarbFehler as exc:
            raise RenderFehler(str(exc)) from exc
    x0, y0 = teil.get("x", 0), teil.get("y", 0)
    breite = max((len(z) for z in zeilen), default=0)
    for j, zeile in enumerate(zeilen):
        for i, zeichen in enumerate(zeile):
            if zeichen == ".":
                continue
            if zeichen not in palette:
                raise RenderFehler(f"Pixelbild: Zeichen {zeichen!r} ohne Farbe")
            x = x0 + i
            if spiegeln:
                x = BREITE - x0 - breite + (breite - 1 - i)
            hexfarbe, deckung = palette[zeichen]
            gruppe.fuellungen.append((x + dx, y0 + j + dy, 1, 1, hexfarbe, deckung))


# --- Ausgabe -----------------------------------------------------------------------------------


def _pfade(rechtecke):
    """Rechtecke (am Raster beschnitten) zu ``<path>``-Läufen gleicher Farbe zusammenfassen.
    Die Reihenfolge bleibt erhalten, nur unmittelbar benachbarte Rechtecke werden vereint."""
    laeufe = []
    for x, y, w, h, farbe, deckung in rechtecke:
        x2, y2 = min(x + w, BREITE), min(y + h, HOEHE)
        x, y = max(x, 0), max(y, 0)
        if x2 <= x or y2 <= y:
            continue
        schluessel = (farbe, deckung)
        stueck = f"M{x} {y}h{x2 - x}v{y2 - y}h{x - x2}z"
        if laeufe and laeufe[-1][0] == schluessel:
            laeufe[-1][1].append(stueck)
        else:
            laeufe.append((schluessel, [stueck]))
    teile = []
    for (farbe, deckung), stuecke in laeufe:
        opak = "" if deckung == 100 else f' opacity="0.{deckung:02d}"'
        teile.append(f'<path fill="{farbe}"{opak} d="{"".join(stuecke)}"/>')
    return "".join(teile)


def _thema(zustand):
    daten = zustand.get("thema_daten")
    if daten:
        return daten
    try:
        return bibliothek.thema(zustand["thema"])
    except KeyError as exc:
        raise RenderFehler(str(exc.args[0])) from exc


def _scope(thema, figur):
    lib = bibliothek.figur()
    try:
        scope = {k: v for k, v in thema["palette"].items()}
        scope["haut"] = lib["hautfarben"][figur["haut"]]["farbe"]
        scope["haar"] = lib["haarfarben"][figur["haar"]]["farbe"]
    except KeyError as exc:
        raise RenderFehler(f"Unbekannte Figur-Option: {exc.args[0]!r}") from exc
    for nr, schluessel in enumerate(("oberteil", "hose", "schuhe"), 1):
        scope[f"kl{nr}"] = farben.aufloesen(thema["kleidung"][schluessel], scope)[0]
    return scope


def _figur_gruppe(figur, scope, umriss):
    lib = bibliothek.figur()
    gruppe = _Gruppe(umriss)
    for prim in lib["schatten"]:
        _prim_aufloesen(prim, scope, 0, 0, False, gruppe)
    # Schatten ohne Umriss zuerst, danach Umriss aller Körperteile, dann Füllungen.
    for prim in lib["koerper"]:
        _prim_aufloesen(prim, scope, 0, 0, False, gruppe)
    try:
        frisur = lib["frisuren"][figur["frisur"]]
    except KeyError as exc:
        raise RenderFehler(f"Unbekannte Frisur: {figur['frisur']!r}") from exc
    for prim in frisur["prims"]:
        _prim_aufloesen(prim, scope, 0, 0, False, gruppe)
    for prim in lib["gesicht"]:
        _prim_aufloesen(prim, scope, 0, 0, False, gruppe)
    return gruppe


def _slot_gruppe(slot, mod, thema, scope, umriss):
    gruppe = _Gruppe(umriss)
    if mod is not None:
        if mod.get("svg_override"):
            try:
                return svgsicher.svg_bereinigen(mod["svg_override"])
            except svgsicher.SvgUnzulaessig as exc:
                raise RenderFehler(f"SVG-Override abgewiesen: {exc}") from exc
        teile = mod.get("teile") or []
    else:
        teile = (thema.get("grundausstattung") or {}).get(slot, [])
    if len(teile) > MAX_TEILE:
        raise RenderFehler(f"Zu viele Teile im Slot {slot!r} (max. {MAX_TEILE})")
    for teil in teile:
        _teil(teil, slot, scope, gruppe)
    return gruppe


def rendern(zustand):
    """Rendert den Zustand zu einem SVG-String (deterministisch)."""
    zustand = zustand_normalisieren(zustand)
    thema = _thema(zustand)
    scope = _scope(thema, zustand["figur"])
    umriss = bibliothek.figur()["outline"]
    teile = [WURZEL]
    zaehler = 0
    ebenen = [(s["ebene"], s["schluessel"]) for s in bibliothek.slots()]
    ebenen.append((bibliothek.figur_ebene(), None))
    for _, slot in sorted(ebenen, key=lambda e: e[0]):
        if slot is None:
            gruppe = _figur_gruppe(zustand["figur"], scope, umriss)
        else:
            gruppe = _slot_gruppe(slot, zustand["mods"].get(slot), thema, scope, umriss)
        if isinstance(gruppe, str):  # bereinigter Override: fertiges Markup
            teile.append(gruppe)
            continue
        rechtecke = gruppe.rechtecke()
        zaehler += len(rechtecke)
        if zaehler > MAX_RECHTECKE:
            raise RenderFehler("Zu viele Rechtecke")
        teile.append(_pfade(rechtecke))
    teile.append("</svg>")
    return "".join(teile)
