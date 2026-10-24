"""Mod-Baupläne: Format, Prüfung und Hilfsfunktionen zum Erzeugen (Grundlage für AP25).

Bauplan (JSON-Objekt, eine Datei ``daten/bauplaene/<thema>.json`` enthält
``{"format": 1, "bauplaene": [...]}``)::

    {"schluessel": "ritter-kopf-1",       # eindeutig, [a-z0-9-], max. 60 Zeichen
     "name": "Lederkappe",                # max. 60 Zeichen
     "beschreibung": "",                  # optional, max. 200 Zeichen
     "thema": "ritter",                   # Schlüssel aus themen.json (kein Eltern-Thema)
     "slot": "kopf",                      # hintergrund|ruecken|koerper|kopf|hand|begleiter
     "seltenheit": 1,                     # 1 Common .. 6 God Mode
     "preis": null,                       # Punkte; null = Standardpreis des Rangs
     "bauzeit_stunden": null,             # null = Standard des Rangs
     "teile": [                           # 1 bis 6 Teile
        {"form": "kappe",                 # Form aus schablonen/<slot>.json
         "muster": "keins",               # keins | kante | streifen | punkte | karo | glanz
         "muster_farbe": "b",             # optional
         "farben": {"a": "p4", "b": "p5", "c": "#ffd23f"},   # a/b/c: Token (p1-p6) oder #rrggbb
         "dx": 0, "dy": 0,                # optional, Versatz -8..8
         "spiegeln": false}],             # optional
     "svg_override": null}                # optional: handgemachtes SVG (Whitelist-geprüft)
"""

import re

from . import bibliothek, farben, renderer, svgsicher

FORMAT = 1
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
SELTENHEITEN = {
    1: ("Common", "#9ca3af"),
    2: ("Uncommon", "#34d670"),
    3: ("Rare", "#3b82f6"),
    4: ("Epic", "#a855f7"),
    5: ("Legendary", "#facc15"),
    6: ("God Mode", "#ff6bd6"),
}
# Farben (a, b, c) je Slot als Palette-Token; c ist die Zierfarbe (ab Rare: Seltenheitsfarbe)
SLOT_FARBEN = {
    "hintergrund": ("p4", "p6", "p3"),
    "ruecken": ("p2", "p1", "p3"),
    "koerper": ("p1", "p4", "p3"),
    "kopf": ("p4", "p5", "p3"),
    "hand": ("p4", "p5", "p3"),
    "begleiter": ("p6", "p5", "p3"),
}
MUSTER_NACH_SELTENHEIT = {1: "keins", 2: "kante", 3: "streifen", 4: "punkte", 5: "karo", 6: "glanz"}
NAMENSZUSATZ = {1: "", 2: " Plus", 3: " Pro", 4: " Elite", 5: " der Legenden", 6: " (God Mode)"}


def teil(
    form, a=None, b=None, c=None, *, muster="keins", muster_farbe=None, dx=0, dy=0, spiegeln=False
):
    """Ein Teil für ``bauplan['teile']`` bauen (nur gesetzte Angaben landen im Ergebnis)."""
    ergebnis = {"form": form}
    farbwahl = {k: v for k, v in (("a", a), ("b", b), ("c", c)) if v}
    if farbwahl:
        ergebnis["farben"] = farbwahl
    if muster != "keins":
        ergebnis["muster"] = muster
    if muster_farbe:
        ergebnis["muster_farbe"] = muster_farbe
    if dx:
        ergebnis["dx"] = dx
    if dy:
        ergebnis["dy"] = dy
    if spiegeln:
        ergebnis["spiegeln"] = True
    return ergebnis


def bauplan(
    thema,
    slot,
    seltenheit,
    name,
    teile,
    *,
    beschreibung="",
    preis=None,
    bauzeit_stunden=None,
    schluessel=None,
    svg_override=None,
):
    """Bauplan-Objekt im Standardformat zusammensetzen."""
    return {
        "schluessel": schluessel or f"{thema}-{slot}-{seltenheit}",
        "name": name,
        "beschreibung": beschreibung,
        "thema": thema,
        "slot": slot,
        "seltenheit": seltenheit,
        "preis": preis,
        "bauzeit_stunden": bauzeit_stunden,
        "teile": teile,
        "svg_override": svg_override,
    }


def bauplan_erzeugen(thema, slot, seltenheit, *, variante=0):
    """Vorschlag für einen Bauplan aus Themenregeln (Form-Vorlieben, Palette, Seltenheit).

    Deterministisch. Die Form wechselt mit Seltenheit und ``variante``; das Muster wird mit der
    Seltenheit reicher; ab Rare ist die Zierfarbe die Seltenheitsfarbe. Ergebnis ist
    Ausgangspunkt für die Handarbeit (Name, Beschreibung, einzelne Farben)."""
    daten = bibliothek.thema(thema)
    liste = daten["formen"][slot]
    form = liste[(seltenheit - 1 + variante) % len(liste)]
    a, b, c = SLOT_FARBEN[slot]
    if seltenheit >= 3:
        c = SELTENHEITEN[seltenheit][1]
    teil_ = teil(form, a, b, c, muster=MUSTER_NACH_SELTENHEIT[seltenheit])
    name = bibliothek.form(slot, form)["name"] + NAMENSZUSATZ[seltenheit]
    return bauplan(thema, slot, seltenheit, f"{name} ({daten['name']})", [teil_])


def teile_probe(form, muster="keins"):
    """Ein Teil mit Standardfarben für Prüfungen (``avatar_pruefen``)."""
    return teil(form, "p1", "p2", "p3", muster=muster)


def zustand_fuer_vorschau(bauplan_):
    """Render-Zustand: Grundfigur des Themas mit genau diesem Mod angelegt."""
    return {
        "thema": bauplan_["thema"],
        "mods": {
            bauplan_["slot"]: {
                "teile": bauplan_.get("teile") or [],
                "svg_override": bauplan_.get("svg_override"),
            }
        },
    }


def _ganzzahl_oder_none(wert, name, fehler, minimum=0):
    if wert is not None and (isinstance(wert, bool) or not isinstance(wert, int) or wert < minimum):
        fehler.append(f"{name}: ganze Zahl >= {minimum} oder null erwartet")


def bauplan_pruefen(bauplan_):
    """Liste der Fehlermeldungen (leer = Bauplan formal in Ordnung). Rendert nicht."""
    fehler = []
    if not isinstance(bauplan_, dict):
        return ["Bauplan muss ein Objekt sein"]
    schluessel = bauplan_.get("schluessel")
    if not isinstance(schluessel, str) or not SLUG_RE.match(schluessel):
        fehler.append(f"schluessel ungültig: {schluessel!r}")
    name = bauplan_.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 60:
        fehler.append("name: 1-60 Zeichen erwartet")
    beschreibung = bauplan_.get("beschreibung") or ""
    if not isinstance(beschreibung, str) or len(beschreibung) > 200:
        fehler.append("beschreibung: max. 200 Zeichen")
    thema_ = bibliothek.themen().get(bauplan_.get("thema"))
    if thema_ is None or thema_["nur_eltern"]:
        fehler.append(f"thema unbekannt oder nicht für Mods: {bauplan_.get('thema')!r}")
    slot = bauplan_.get("slot")
    if slot not in bibliothek.slot_schluessel():
        fehler.append(f"slot unbekannt: {slot!r}")
        slot = None
    seltenheit = bauplan_.get("seltenheit")
    if isinstance(seltenheit, bool) or seltenheit not in SELTENHEITEN:
        fehler.append("seltenheit: 1 bis 6 erwartet")
    _ganzzahl_oder_none(bauplan_.get("preis"), "preis", fehler)
    _ganzzahl_oder_none(bauplan_.get("bauzeit_stunden"), "bauzeit_stunden", fehler)
    teile = bauplan_.get("teile")
    override = bauplan_.get("svg_override")
    if override:
        meldung = svgsicher.svg_pruefen(override)
        if meldung:
            fehler.append(f"svg_override: {meldung}")
    if not isinstance(teile, list) or not 1 <= len(teile) <= renderer.MAX_TEILE:
        fehler.append(f"teile: Liste mit 1-{renderer.MAX_TEILE} Einträgen erwartet")
    elif slot:
        for nr, t in enumerate(teile, 1):
            fehler += [f"teil {nr}: {m}" for m in _teil_pruefen(t, slot)]
    return fehler


def _teil_pruefen(t, slot):
    fehler = []
    if not isinstance(t, dict):
        return ["muss ein Objekt sein"]
    bekannt = {"form", "muster", "muster_farbe", "farben", "dx", "dy", "spiegeln"}
    fehler += [f"unbekannter Schlüssel {k!r}" for k in t if k not in bekannt]
    if t.get("form") not in bibliothek.formen(slot):
        fehler.append(f"form {t.get('form')!r} gibt es im Slot {slot!r} nicht")
    if t.get("muster", "keins") not in bibliothek.MUSTER:
        fehler.append(f"muster unbekannt: {t.get('muster')!r}")
    scope = {f"p{i}": "#000000" for i in range(1, 7)}
    scope.update(haut="#000000", haar="#000000", a="#000000", b="#000000", c="#000000")
    angaben = dict(t.get("farben") or {})
    if t.get("muster_farbe"):
        angaben["muster_farbe"] = t["muster_farbe"]
    for kurz, wert in angaben.items():
        if kurz not in ("a", "b", "c", "muster_farbe"):
            fehler.append(f"farben: unbekannter Platzhalter {kurz!r}")
            continue
        try:
            farben.aufloesen(wert, scope)
        except farben.FarbFehler as exc:
            fehler.append(f"farben.{kurz}: {exc}")
    for k in ("dx", "dy"):
        v = t.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, int) or not -8 <= v <= 8:
            fehler.append(f"{k}: ganze Zahl -8..8 erwartet")
    return fehler
