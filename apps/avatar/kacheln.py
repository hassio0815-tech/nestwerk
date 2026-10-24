"""Kachel "Mein Avatar" im Kinder-Dashboard (Registry ``kern.registry``): nur sichtbar, solange
das Kind noch keinen Avatar gewählt hat. Der Avatar selbst steht in der Konto-Kachel."""

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
