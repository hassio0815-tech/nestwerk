"""Ruhmeshalle (P3-A): Kind sieht und stiftet eigene Helden, Eltern schreiben Widmungen."""

from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.konten.zugriff import nur_eltern, nur_kind

from . import ruhmeshalle, selectors, services

MELDUNGEN = {
    "gestellt": "Dein Held steht jetzt in der Ruhmeshalle! Such dir ein neues Thema aus.",
    "widmung": "Widmung gespeichert.",
}


def _meldung(request):
    return MELDUNGEN.get(request.GET.get("ok", ""), "")


@nur_kind
@require_GET
def kind(request):
    return render(
        request,
        "avatar/ruhmeshalle.html",
        {
            "eintraege": ruhmeshalle.mit_bild(ruhmeshalle.eintraege(request.user)),
            "stand": ruhmeshalle.bereitschaft(request.user),
            "meldung": _meldung(request),
        },
    )


@nur_kind
@require_http_methods(["GET", "POST"])
def stellen(request):
    """Bestätigungsdialog: Held ansehen, neues Thema wählen, bestätigen."""
    kind_ = request.user
    avatar = selectors.avatar_von(kind_)
    if avatar is None:
        return redirect("avatar:kind_wahl")
    stand = ruhmeshalle.bereitschaft(kind_)
    fehler = ""
    quelle = request.POST if request.method == "POST" else request.GET
    gewaehlt = quelle.get("thema", "")
    if request.method == "POST":
        try:
            _, neu = services.in_ruhmeshalle_stellen(
                kind_, gewaehlt, bau_start=request.POST.get("bau_start", "")
            )
        except services.ModFehler as exc:
            fehler = str(exc)
        else:
            return redirect(f"{reverse('avatar:halle_kind')}?ok=gestellt")
    if not stand.bereit and not fehler:
        return redirect("avatar:halle_kind")
    _, svg = services.svg_fuer(kind_)
    karten = [
        {
            "thema": t,
            "svg": services.vorschau_svg(t.schluessel, avatar.figur),
            "gewaehlt": t.schluessel == gewaehlt,
        }
        for t in selectors.waehlbare_themen()
    ]
    kontext = {
        "avatar": avatar,
        "stand": stand,
        "svg": svg,
        "karten": karten,
        "gewaehlt": gewaehlt,
        "fehler": fehler,
    }
    return render(
        request, "avatar/ruhmeshalle_stellen.html", kontext, status=409 if fehler else 200
    )


@nur_eltern
@require_GET
def eltern(request):
    return render(
        request,
        "avatar/ruhmeshalle_eltern.html",
        {"gruppen": ruhmeshalle.je_kind(), "meldung": _meldung(request), "fehler": ""},
    )


@nur_eltern
@require_POST
def widmung(request, pk):
    if not selectors.ruhmeshalle_eintraege().filter(pk=pk).exists():
        raise Http404
    try:
        services.widmung_setzen(pk, request.POST.get("widmung", ""), von=request.user)
    except services.ModFehler as exc:
        kontext = {"gruppen": ruhmeshalle.je_kind(), "meldung": "", "fehler": str(exc)}
        return render(request, "avatar/ruhmeshalle_eltern.html", kontext, status=400)
    return redirect(f"{reverse('avatar:halle_eltern')}?ok=widmung#eintrag-{pk}")
