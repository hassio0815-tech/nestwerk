"""Startseite-Weiche, Kinder-/Eltern-Dashboard und Tablet-Startseite (SPEC 12).

Routing: ``/`` leitet je Rolle/Gerät weiter (Anmeldung bleibt bei ``konten``), ``/kind/`` und
``/eltern/`` sind die Dashboards, ``/tablet/`` die Live-Startseite des Flur-Tablets."""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.kern import einstellungen, zeit
from apps.kern.registry import ELTERN, KIND, TABLET
from apps.konten import akzent, begruessung, netz, sperre
from apps.konten import selectors as konten_selectors
from apps.konten import services as konten_services
from apps.konten import views as konten_views
from apps.konten.geraet import ist_kiosk
from apps.konten.models import Rolle
from apps.konten.zugriff import nur_eltern, nur_kind, passiv

from . import kacheln, module, ranking, selectors, uebernehmen, wechseltext

logger = logging.getLogger(__name__)


@require_GET
def styleguide(request):
    """Entwicklungsansicht aller Komponenten. Ohne DEBUG nicht erreichbar."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "oberflaeche/styleguide.html")


@require_GET
def startseite(request):
    """``/``: angemeldet -> eigenes Dashboard, Kiosk-Gerät -> Tablet-Startseite, sonst die
    Anmeldeauswahl von ``konten``."""
    if request.user.is_authenticated:
        return redirect(
            "oberflaeche:eltern_heim"
            if request.user.rolle == Rolle.ELTERN
            else "oberflaeche:kind_heim"
        )
    if ist_kiosk(request):
        return redirect("oberflaeche:tablet")
    try:
        infozeile = selectors.start_infozeile()
    except einstellungen.EinstellungFehlt:  # z. B. vor der Einrichtung: Anmeldung geht vor
        logger.warning("Infozeile der Startseite ohne Zeitzone nicht verfügbar")
        infozeile = None
    try:
        woche = selectors.start_woche()
    except einstellungen.EinstellungFehlt:
        logger.warning("Wochenvorschau der Startseite ohne Zeitzone nicht verfügbar")
        woche = None
    try:
        texte = wechseltext.wechseltexte()
    except Exception:  # der Wechseltext ist Beiwerk: nie die Anmeldeauswahl kippen
        logger.exception("Wechseltext der Startseite konnte nicht gebaut werden")
        texte = []
    return konten_views.start(
        request,
        extra={
            "infozeile": infozeile,
            "woche": woche,
            "uebernehmen": _absicht(request),
            "wechseltexte": texte,
        },
    )


def _absicht(request):
    """Vorgemerkte Aufgabe fürs Banner der Anmeldeseite (nur wenn sie noch gültig ist)."""
    gemerkt = uebernehmen.gemerkt(request)
    if gemerkt is None:
        return None
    try:
        aufgabe = selectors.uebernehmen_absicht(*gemerkt)
    except einstellungen.EinstellungFehlt:
        return None
    if aufgabe is None:
        uebernehmen.verwerfen(request)
        return None
    return {"aufgabe": aufgabe, "datum": gemerkt[1]}


@require_POST
def uebernehmen_vormerken(request):
    """Popup der Wochenvorschau: Aufgabe vormerken, dann zur normalen Kind-Anmeldung."""
    if request.user.is_authenticated:
        return redirect("konten:start")
    try:
        uebernehmen.vormerken(request, request.POST.get("aufgabe"), request.POST.get("datum"))
    except einstellungen.EinstellungFehlt:
        uebernehmen.verwerfen(request)
    return redirect("konten:start")


@require_POST
def uebernehmen_abbrechen(request):
    uebernehmen.verwerfen(request)
    return redirect("konten:start")


# Dungeon (über den Avatar erreichbar): Figur, Mods, Shop, Ränge, Ruhmeshalle, Abzeichen.
DUNGEON = (
    "avatar.kind_werkstatt",
    "avatar.kind_ruhmeshalle",
    "spielregeln.kind_rang",
    "spielregeln.kind_abzeichen",
)
# Untermenüs der Kinder-Startseite: Kacheln, die dort nicht mehr stehen, liegen auf diesen Seiten.
KIND_BEREICH = ("oberflaeche.kind_konto", "oberflaeche.kind_belohnungen")
KIND_ZIELE = (
    "spielregeln.kind_serie",
    "sondertag.kind",
    "familienziel.kind",
    "oberflaeche.kind_ranking",
)
# "Meine Aufgaben" steht schon auf der Aufgaben-Seite, Schnell-Knöpfe liegen dort ebenfalls.
KIND_ANDERSWO = ("oberflaeche.kind_laufende", "oberflaeche.kind_schnellknoepfe")
NICHT_AUF_DASHBOARD = (
    DUNGEON
    + KIND_BEREICH
    + KIND_ZIELE
    + KIND_ANDERSWO
    + (
        "oberflaeche.kind_offene",
        "oberflaeche.kind_akzent",
    )
)


def _kind_kacheln(request, schluessel=None):
    """Kacheln für Startseite (``schluessel=None``: nur Unbekanntes wie "Figur wählen") oder für
    ein Untermenü (``schluessel`` = Tupel der Kachel-Schlüssel, in dieser Reihenfolge)."""
    alle = kacheln.fuer(KIND, request)
    if schluessel is None:
        return [e for e in alle if e["kachel"].schluessel not in NICHT_AUF_DASHBOARD]
    nach_schluessel = {e["kachel"].schluessel: e for e in alle}
    return [nach_schluessel[s] for s in schluessel if s in nach_schluessel]


@nur_kind
@require_GET
def kind_heim(request):
    """Kinder-Startseite: Avatar, Mini-Übersicht, Lernen, Aufgaben; der Rest in Untermenüs."""
    kind = request.user
    hinweis, hinweis_art = uebernehmen.hinweis_entnehmen(request)
    return render(
        request,
        "oberflaeche/kind_heim.html",
        {
            "hinweis": hinweis,
            "hinweis_art": hinweis_art,
            "kacheln": _kind_kacheln(request),
            "mood": konten_selectors.mood_text(kind),
            "guthaben": _oder(lambda: selectors.kind_konto(kind)["guthaben"], 0),
            "balken": selectors.kind_balken(kind),
            **_oder(
                lambda: selectors.kind_offene_auszug(kind, anzahl=START_AUFGABEN),
                {"aufgaben": [], "gesamt": 0},
            ),
        },
    )


START_AUFGABEN = 3


def _oder(funktion, ersatz):
    """Ein Block der Startseite darf sie nicht kippen (wie bei ``kacheln.fuer``)."""
    try:
        return funktion()
    except Exception:
        logger.exception("Startseiten-Block konnte nicht berechnet werden")
        return ersatz


@nur_kind
@require_GET
def kind_bereich(request):
    """Untermenü "Mein Bereich": Dungeon, Einstellungen, Guthaben und Belohnungen."""
    return render(
        request,
        "oberflaeche/kind_unterseite.html",
        {
            "titel": _("Mein Bereich"),
            "bereich": True,
            "kacheln": _kind_kacheln(request, KIND_BEREICH),
        },
    )


@nur_kind
@require_GET
def kind_ziele(request):
    """Untermenü "Serie & Ziele": Serie, Sondertage, Familienziel, Ranking."""
    return render(
        request,
        "oberflaeche/kind_unterseite.html",
        {"titel": _("Serie & Ziele"), "kacheln": _kind_kacheln(request, KIND_ZIELE)},
    )


@nur_kind
@require_GET
def dungeon(request):
    eintraege = [e for e in kacheln.fuer(KIND, request) if e["kachel"].schluessel in DUNGEON]
    from apps.avatar import charakter

    return render(
        request,
        "oberflaeche/kind_dungeon.html",
        {"kacheln": eintraege, "charakter": charakter.charakter(request.user)},
    )


@nur_kind
@require_POST
def akzent_setzen(request):
    name = request.POST.get("akzent", "")
    if name in akzent.PALETTE:
        konten_services.akzentfarben_setzen(request.user, [akzent.name_zu_hex(name)])
    ziel = request.POST.get("next", "")
    if ziel.startswith("/") and not ziel.startswith("//"):
        return redirect(ziel)
    return redirect("oberflaeche:kind_heim")


@nur_eltern
@require_GET
def module_launcher(request):
    """Nach der Eltern-Anmeldung: große Karten je Modul/Bereich (module.MODULE)."""
    return render(
        request,
        "oberflaeche/module.html",
        {"module": module.fuer(request.user), "gruss": begruessung.gruss()},
    )


# Spiel-Kacheln der Eltern: wandern in den Dungeon-Bereich (/eltern/dungeon/).
ELTERN_DUNGEON = (
    "oberflaeche.eltern_ranking",
    "spielregeln.eltern_raenge",
    "spielregeln.eltern_abzeichen",
    "avatar.eltern_mods",
    "avatar.eltern_ruhmeshalle",
    "sondertag.eltern",
)


@nur_eltern
@require_GET
def eltern_dungeon(request):
    eintraege = [
        e for e in kacheln.fuer(ELTERN, request) if e["kachel"].schluessel in ELTERN_DUNGEON
    ]
    from apps.avatar import selectors as avatar_selectors

    return render(
        request,
        "oberflaeche/eltern_dungeon.html",
        {"kacheln": eintraege, "namen": avatar_selectors.benannte_avatare()},
    )


@nur_eltern
@require_POST
def dungeon_anzeige_setzen(request):
    request.user.dungeon_anzeigen = request.POST.get("dungeon_anzeigen") == "1"
    request.user.save(update_fields=["dungeon_anzeigen"])
    return redirect("oberflaeche:einstellungen")


@nur_eltern
@require_POST
def wappen_setzen(request):
    """Eigenes Wappen wählen (HTMX: Karte neu rendern, sonst zurück zu den Einstellungen)."""
    kontext = {}
    try:
        post = request.POST
        konten_services.wappen_setzen(
            request.user,
            post.get("wappen"),
            post.get("wappen_rolle"),
            post.get("wappen_rolle_eigen"),
        )
        kontext["wappen_gespeichert"] = True
    except ValidationError as exc:
        kontext["wappen_fehler"] = " ".join(exc.messages)
    if request.headers.get("HX-Request"):
        return render(request, "oberflaeche/_wappen_karte.html", kontext)
    return redirect("oberflaeche:einstellungen")


@nur_eltern
@require_GET
def eltern_heim(request):
    eintraege = [
        e
        for e in kacheln.fuer(ELTERN, request)
        if e["kachel"].schluessel not in ELTERN_DUNGEON
        and e["kachel"].schluessel not in kacheln.ELTERN_EINSTELLUNGEN
    ]
    return render(
        request,
        "oberflaeche/eltern_heim.html",
        {
            "kacheln": eintraege,
            "zahlen": _eltern_zahlen(request, eintraege),
            "gesperrte_kinder": konten_selectors.gesperrte_kinder(),
        },
    )


def _eltern_zahlen(request, eintraege):
    """Kennzahlen für die Zahlen-Kacheln oben auf /eltern/: offene Entscheidungen, heute
    Erledigtes (aus der Kachel, keine zweite Abfrage), ungelesene Benachrichtigungen und der
    Fortschritt des Familienziels (``None`` = nicht verfügbar, die Kachel entfällt)."""
    from apps.benachrichtigung import selectors as benachrichtigung
    from apps.familienziel import selectors as familienziel

    erledigt = next(
        (e["k"] for e in eintraege if e["kachel"].schluessel == "oberflaeche.eltern_pruefen"),
        None,
    )
    try:
        prozent = familienziel.ansicht().stand.prozent
    except Exception:  # Zahlen-Kachel entfällt, die Übersicht bleibt nutzbar
        prozent = None
    return {
        "offen": selectors.eltern_entscheidungen()["gesamt"],
        "erledigt": erledigt["gesamt"] if erledigt else 0,
        "ungelesen": benachrichtigung.ungelesen(request.user),
        "ziel_prozent": prozent,
    }


# --- Tablet ----------------------------------------------------------------------------------


def _tablet_kontext(request):
    jetzt = zeit.jetzt()
    kinder = []
    for kind in konten_selectors.aktive_kinder():
        kinder.append(
            {
                "benutzer": kind,
                "akzent": akzent.akzent_name(kind),
                "gesperrt": bool(sperre.kind_gesperrt_bis(kind.kindprofil, jetzt)),
                "guthaben": selectors.kind_konto(kind)["guthaben"],
                "offen": selectors.offene_anzahl(kind),
            }
        )
    return {"kinder": kinder, "slots": kacheln.fuer(TABLET, request)}


def _tablet_erlaubt(request):
    return netz.kind_login_erlaubt(request)


@require_GET
def tablet(request):
    """Tablet-Startseite ohne Anmeldung (nur Lesen, nur aus dem Heimnetz)."""
    if not _tablet_erlaubt(request):
        return HttpResponseForbidden(_("Die Tablet-Ansicht gibt es nur im Heimnetz."))
    werte = einstellungen.werte(
        "oberflaeche.tablet_aktualisierung_sekunden", "oberflaeche.tablet_neuladen_stunden"
    )
    kontext = _tablet_kontext(request)
    kontext["intervall"] = werte["oberflaeche.tablet_aktualisierung_sekunden"]
    kontext["neuladen_sekunden"] = werte["oberflaeche.tablet_neuladen_stunden"] * 3600
    return render(request, "oberflaeche/tablet.html", kontext)


@passiv
@require_GET
def tablet_teil(request):
    """Polling-Ausschnitt der Tablet-Startseite. ``@passiv``: verlängert keine Sitzung."""
    if not _tablet_erlaubt(request):
        return HttpResponseForbidden(_("Die Tablet-Ansicht gibt es nur im Heimnetz."))
    return render(request, "oberflaeche/_tablet_teil.html", _tablet_kontext(request))


# --- Familien-Ranking (AP30) -----------------------------------------------------------------


@nur_eltern
@require_POST
def ranking_modus(request):
    """Eltern schalten die Ranking-Ansicht für Tablet und Kinder-Seite um."""
    gewaehlt = request.POST.get("modus", "")
    if gewaehlt in ranking.RANKING_MODI:
        einstellungen.setzen("oberflaeche.ranking_modus", gewaehlt)
    return redirect("oberflaeche:eltern_heim")
