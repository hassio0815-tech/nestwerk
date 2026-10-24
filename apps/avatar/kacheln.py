"""Dashboard-Kacheln von avatar (Registry ``kern.registry``).

- "Mein Avatar": nur sichtbar, solange das Kind noch keinen Avatar gewählt hat.
- "Meine Werkstatt" (AP26): laufende Bauaufträge und Ausbaustufe "4/6 im Rang Rare".
- Eltern "Mods und Bauaufträge" (AP26): laufende Bauaufträge je Kind.
"""

from . import selectors, services

BEISPIEL_THEMEN = ("ritter", "weltraum", "pirat")


def kind_sichtbar(request):
    return not selectors.hat_avatar(request.user)


def kind_kontext(request):
    themen = selectors.waehlbare_themen()
    beispiele = [
        services.vorschau_svg(schluessel, {"haut": "haut3", "haar": "haar2", "frisur": "kurz"})
        for schluessel in BEISPIEL_THEMEN
    ]
    return {"anzahl_themen": len(themen), "beispiele": beispiele}


def werkstatt_sichtbar(request):
    return selectors.hat_avatar(request.user)


def werkstatt_kontext(request):
    kind = request.user
    avatar = selectors.avatar_von(kind)
    ort, _ = selectors.inszenierung(avatar.thema if avatar else None)
    return {
        "stufe": selectors.ausbaustufe(kind),
        "bau": selectors.bauauftraege(kind),
        "ort": ort,
    }


def eltern_kontext(request):
    zeilen = selectors.eltern_uebersicht()
    return {
        "zeilen": zeilen,
        "im_bau": sum(len(z["bau"]) for z in zeilen),
    }
