"""Dashboard-Kachel "Benachrichtigungen" für Eltern (Registry von kern)."""

from apps.kern.registry import ELTERN, Kachel

from . import selectors


def _kontext(request):
    benutzer = request.user
    return {
        "ungelesen": selectors.ungelesen(benutzer),
        "neueste": selectors.liste(benutzer, limit=5),
    }


def eltern_kachel():
    return Kachel(
        schluessel="benachrichtigung.liste",
        modul="benachrichtigung",
        titel="Benachrichtigungen",
        template="benachrichtigung/_kachel.html",
        zielgruppen={ELTERN},
        kontext=_kontext,
        reihenfolge=20,
    )
