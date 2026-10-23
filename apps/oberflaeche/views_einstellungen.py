"""Generischer Einstellungen-Editor (Eltern): alle Einstellungen der Registry, je Modul."""

from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.konten.zugriff import nur_eltern

from . import einstellungen_editor as editor


def _gruppen(*, modul=None, eingaben=None, fehler=None, geaendert=()):
    gruppen = []
    for name in editor.module():
        gruppen.append(
            {
                "modul": name,
                "titel": editor.modul_titel(name),
                "felder": editor.felder(
                    name,
                    eingaben=eingaben if name == modul else None,
                    fehler=fehler if name == modul else None,
                ),
                "geaendert": name == modul and bool(geaendert),
            }
        )
    return gruppen


@nur_eltern
@require_GET
def uebersicht(request):
    return render(
        request,
        "oberflaeche/einstellungen.html",
        {"gruppen": _gruppen(), "gespeichert": request.GET.get("ok", "")},
    )


@nur_eltern
@require_POST
def speichern(request, modul):
    if modul not in editor.module():
        raise Http404
    eingaben = editor.eingaben_aus_post(modul, request.POST)
    fehler, geaendert = editor.speichern(modul, eingaben)
    if fehler:
        return render(
            request,
            "oberflaeche/einstellungen.html",
            {"gruppen": _gruppen(modul=modul, eingaben=eingaben, fehler=fehler), "offen": modul},
            status=422,
        )
    return redirect(f"{reverse('oberflaeche:einstellungen')}?ok={modul}#modul-{modul}")
