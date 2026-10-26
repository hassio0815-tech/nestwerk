"""Startseite-Weiche, Kinder-/Eltern-Dashboard und Tablet-Startseite (SPEC 12).

Routing: ``/`` leitet je Rolle/Gerät weiter (Anmeldung bleibt bei ``konten``), ``/kind/`` und
``/eltern/`` sind die Dashboards, ``/tablet/`` die Live-Startseite des Flur-Tablets."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
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

from . import kacheln, module, ranking, selectors


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
    return konten_views.start(request)


# Dungeon (über den Avatar erreichbar): Figur, Mods, Shop, Ränge, Ruhmeshalle, Abzeichen.
DUNGEON = (
    "avatar.kind_werkstatt",
    "avatar.kind_ruhmeshalle",
    "spielregeln.kind_rang",
    "spielregeln.kind_abzeichen",
)
# Dashboard-Reihenfolge; unbekannte (neue) Kacheln folgen in Registry-Reihenfolge.
KIND_REIHENFOLGE = (
    "oberflaeche.kind_konto",
    "avatar.kind_avatar",  # nur sichtbar, solange noch keine Figur gewählt ist
    "oberflaeche.kind_laufende",
    "oberflaeche.kind_offene",
    "oberflaeche.kind_belohnungen",
    "familienziel.kind",
    "oberflaeche.kind_ranking",
    "sondertag.kind",
    "spielregeln.kind_serie",
)
NICHT_AUF_DASHBOARD = DUNGEON + ("oberflaeche.kind_akzent",)


def _kind_kacheln(request):
    alle = [e for e in kacheln.fuer(KIND, request) if e["kachel"].schluessel not in NICHT_AUF_DASHBOARD]

    def rang(e):
        try:
            return KIND_REIHENFOLGE.index(e["kachel"].schluessel)
        except ValueError:
            return len(KIND_REIHENFOLGE)

    return sorted(alle, key=rang)  # stabil: Registry-Reihenfolge bleibt innerhalb der Gruppen


@nur_kind
@require_GET
def kind_heim(request):
    return render(
        request,
        "oberflaeche/kind_heim.html",
        {"kacheln": _kind_kacheln(request)},
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
    eintraege = [e for e in kacheln.fuer(ELTERN, request) if e["kachel"].schluessel in ELTERN_DUNGEON]
    from apps.avatar.models import Avatar

    namen = Avatar.objects.exclude(name="").select_related("benutzer").order_by("benutzer__reihenfolge")
    return render(
        request,
        "oberflaeche/eltern_dungeon.html",
        {"kacheln": eintraege, "namen": list(namen)},
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
    return render(
        request,
        "oberflaeche/eltern_heim.html",
        {
            "kacheln": [
                e for e in kacheln.fuer(ELTERN, request) if e["kachel"].schluessel not in ELTERN_DUNGEON
            ],
            "gesperrte_kinder": konten_selectors.gesperrte_kinder(),
        },
    )


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
        return HttpResponseForbidden("Die Tablet-Ansicht gibt es nur im Heimnetz.")
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
        return HttpResponseForbidden("Die Tablet-Ansicht gibt es nur im Heimnetz.")
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
