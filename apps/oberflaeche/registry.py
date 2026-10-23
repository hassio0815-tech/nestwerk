"""Eingebaute Dashboard-Kacheln. Andere Module (Phase 2: Rang, Serie, Mods, Familienziel)
registrieren ihre Kacheln selbst über ``kern.registry.kachel_registrieren``; die Dashboards
zeigen alles, was die Registry alle die Zielgruppe liefert."""

from apps.kern.registry import ELTERN, KIND, Kachel, kachel_registrieren

from . import selectors

T = "oberflaeche/kacheln/"


def _kind_konto(request):
    return selectors.kind_konto(request.user)


def _kind_offene(request):
    return selectors.kind_offene_auszug(request.user)


def _kind_laufende(request):
    return {"laufende": selectors.kind_laufende(request.user)}


def _kind_akzent(request):
    from apps.konten import akzent

    return {"palette": list(akzent.PALETTE), "aktuell": akzent.akzent_name(request.user)}


def _eltern_entscheidungen(request):
    return selectors.eltern_entscheidungen()


def _eltern_kinder(request):
    return {"zeilen": selectors.kinder_uebersicht()}


def _eltern_ereignisse(request):
    from apps.benachrichtigung import selectors as benachrichtigung

    return {
        "eintraege": benachrichtigung.liste(request.user, 8),
        "ungelesen": benachrichtigung.ungelesen(request.user),
    }


def _eltern_system(request):
    return {"status": selectors.system_status()}


def kacheln_registrieren():
    alle = [
        Kachel(
            "oberflaeche.kind_konto",
            "oberflaeche",
            "Guthaben und XP",
            T + "kind_konto.html",
            {KIND},
            _kind_konto,
            reihenfolge=10,
        ),
        Kachel(
            "oberflaeche.kind_offene",
            "oberflaeche",
            "Offene Aufgaben",
            T + "kind_offene.html",
            {KIND},
            _kind_offene,
            reihenfolge=20,
        ),
        Kachel(
            "oberflaeche.kind_laufende",
            "oberflaeche",
            "Meine Aufgaben",
            T + "kind_laufende.html",
            {KIND},
            _kind_laufende,
            reihenfolge=30,
        ),
        Kachel(
            "oberflaeche.kind_belohnungen",
            "oberflaeche",
            "Belohnungen",
            T + "kind_belohnungen.html",
            {KIND},
            reihenfolge=40,
        ),
        Kachel(
            "oberflaeche.kind_akzent",
            "oberflaeche",
            "Meine Farbe",
            T + "kind_akzent.html",
            {KIND},
            _kind_akzent,
            reihenfolge=90,
        ),
        Kachel(
            "oberflaeche.eltern_entscheidungen",
            "oberflaeche",
            "Entscheidungen",
            T + "eltern_entscheidungen.html",
            {ELTERN},
            _eltern_entscheidungen,
            reihenfolge=10,
        ),
        Kachel(
            "oberflaeche.eltern_kinder",
            "oberflaeche",
            "Kinder",
            T + "eltern_kinder.html",
            {ELTERN},
            _eltern_kinder,
            reihenfolge=20,
        ),
        Kachel(
            "oberflaeche.eltern_ereignisse",
            "oberflaeche",
            "Ereignisse",
            T + "eltern_ereignisse.html",
            {ELTERN},
            _eltern_ereignisse,
            reihenfolge=30,
        ),
        Kachel(
            "oberflaeche.eltern_system",
            "oberflaeche",
            "Systemstatus",
            T + "eltern_system.html",
            {ELTERN},
            _eltern_system,
            reihenfolge=40,
        ),
        Kachel(
            "oberflaeche.eltern_schnellzugriff",
            "oberflaeche",
            "Schnellzugriff",
            T + "eltern_schnellzugriff.html",
            {ELTERN},
            reihenfolge=50,
        ),
    ]
    for kachel in alle:
        kachel_registrieren(kachel)
