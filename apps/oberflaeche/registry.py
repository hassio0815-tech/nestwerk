"""Eingebaute Dashboard-Kacheln. Andere Module (Phase 2: Rang, Serie, Mods, Familienziel)
registrieren ihre Kacheln selbst über ``kern.registry.kachel_registrieren``; die Dashboards
zeigen alles, was die Registry alle die Zielgruppe liefert."""

from apps.kern.registry import ELTERN, KIND, TABLET, Kachel, kachel_registrieren

from . import ranking, selectors

T = "oberflaeche/kacheln/"


def _kind_konto(request):
    from apps.spielregeln import selectors as spielregeln

    konto = selectors.kind_konto(request.user)
    try:
        konto["rang"] = spielregeln.rang_fortschritt(request.user).rang
        konto["serie"] = spielregeln.stand(request.user).wochenserie
    except Exception:  # Kopfkarte bleibt auch ohne Spielregeln nutzbar
        konto["rang"], konto["serie"] = None, 0
    return konto


def _kind_belohnungen(request):
    from apps.belohnung import views as belohnung

    return belohnung._kind_kontext(request.user)


def _kind_offene(request):
    return selectors.kind_offene_auszug(request.user)


def _kind_laufende(request):
    return {"laufende": selectors.kind_laufende(request.user)}


def _kind_akzent(request):
    from apps.konten import akzent

    return {"palette": list(akzent.PALETTE), "aktuell": akzent.akzent_name(request.user)}


def _eltern_pruefen(request):
    from apps.aufgaben import services as aufgaben

    return {"liste": list(aufgaben.zu_pruefen())}


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


def _ranking(request):
    return {"a": ranking.ansicht()}


def _ranking_eltern(request):
    return {"a": ranking.ansicht()} | ranking.eltern_zusatz()


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
            "Punkte einlösen",
            T + "kind_belohnungen.html",
            {KIND},
            _kind_belohnungen,
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
        Kachel(
            "oberflaeche.tablet_ranking",
            "oberflaeche",
            "Ranking",
            T + "tablet_ranking.html",
            {TABLET},
            _ranking,
            reihenfolge=50,
        ),
        Kachel(
            "oberflaeche.kind_ranking",
            "oberflaeche",
            "Familie",
            T + "kind_ranking.html",
            {KIND},
            _ranking,
            reihenfolge=60,
        ),
        Kachel(
            "oberflaeche.eltern_pruefen",
            "oberflaeche",
            "Erledigt – kurz prüfen",
            "aufgaben/kacheln/eltern_pruefen.html",
            {ELTERN},
            _eltern_pruefen,
            reihenfolge=5,
        ),
        Kachel(
            "oberflaeche.eltern_ranking",
            "oberflaeche",
            "Familien-Ranking",
            T + "eltern_ranking.html",
            {ELTERN},
            _ranking_eltern,
            reihenfolge=25,
        ),
    ]
    for kachel in alle:
        kachel_registrieren(kachel)
