"""Seiten der Lernmappe (SPEC 21.5): Kinder laden Material hoch und sehen nur ihre eigene Mappe;
Eltern prüfen, geben frei, lehnen ab, bearbeiten und löschen.

Dateien gehen nie über einen öffentlichen Pfad hinaus: ``datei`` liefert mit festem Typ, ``nosniff``
und ``no-store``; alles außer Bildern als Download. Fremdes Material (anderes Kind) ist für Kinder
ein 404. Jeder Text aus Upload oder KI wird von den Vorlagen escaped.
"""

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.kern.einstellungen import wert
from apps.konten import selectors as konten
from apps.konten.zugriff import aktueller_elternteil, aktuelles_kind, nur_eltern, nur_kind

from . import ki_selectors, material_selectors, material_services
from .material_dateien import UploadFehler, anzeigename_bereinigen, erlaubte_endungen
from .models import Fach, FrageTyp, KiAufgabe
from .speicher import SpeicherVoll

MAX_DATEIEN = 5
_MIME = {
    "image/jpeg": "image/jpeg",
    "application/pdf": "application/pdf",
    "text/plain": "text/plain; charset=utf-8",
}


def _mb(bytes_):
    return round(bytes_ / (1024 * 1024), 1)


# --- Kind ------------------------------------------------------------------------------------


def _kind_kontext(kind, *, fehler=None, neu=0):
    belegt, limit = material_services.verbrauch(kind)
    liste = [
        (m, material_selectors.KIND_PHASE[m.status]) for m in material_selectors.materialien(kind)
    ]
    return {
        "eintraege": liste,
        "fehler": fehler or [],
        "neu": neu,
        "belegt_mb": _mb(belegt),
        "limit_mb": _mb(limit),
        "max_mb": wert("lernen.upload_max_mb"),
        "endungen": ", ".join(erlaubte_endungen()),
        "accept": ",".join(f".{e}" for e in erlaubte_endungen()),
        "ki_bereit": ki_selectors.status_von(ki_selectors.zuordnung_fuer(KiAufgabe.AUSLESEN))
        is ki_selectors.KiStatus.BEREIT,
    }


@nur_kind
def mappe(request):
    kind = aktuelles_kind(request)
    neu = int(request.GET["neu"]) if request.GET.get("neu", "").isdigit() else 0
    return render(request, "lernen/material.html", _kind_kontext(kind, neu=min(neu, MAX_DATEIEN)))


@nur_kind
@require_POST
def hochladen(request):
    kind = aktuelles_kind(request)
    dateien = request.FILES.getlist("datei")
    if not dateien:
        kontext = _kind_kontext(kind, fehler=[_("Bitte wähle zuerst eine Datei aus.")])
        return render(request, "lernen/material.html", kontext, status=400)
    maximal = wert("lernen.upload_max_mb") * 1024 * 1024
    fehler, angenommen = [], 0
    for datei in dateien[:MAX_DATEIEN]:
        try:
            if datei.size > maximal:
                raise UploadFehler(
                    _("Die Datei ist zu groß (höchstens %(mb)s MB).")
                    % {"mb": wert("lernen.upload_max_mb")}
                )
            material_services.aufnehmen(kind, datei.name, datei.read(maximal + 1))
            angenommen += 1
        except (UploadFehler, material_services.MaterialFehler) as exc:
            fehler.append(f"{anzeigename_bereinigen(datei.name)}: {exc}")
        except SpeicherVoll:
            fehler.append(
                _("Die Mappe ist voll. Sag deinen Eltern Bescheid, sie können aufräumen.")
            )
            break
    if len(dateien) > MAX_DATEIEN:
        fehler.append(_("Pro Mal höchstens %(n)s Dateien.") % {"n": MAX_DATEIEN})
    if fehler:
        return render(
            request,
            "lernen/material.html",
            _kind_kontext(kind, fehler=fehler, neu=angenommen),
            status=400,
        )
    return redirect(f"{resolve_url('lernen:material')}?neu={angenommen}")


@nur_kind
def eigenes(request, pk):
    kind = aktuelles_kind(request)
    material = material_selectors.material_von(kind, pk)
    if material is None:
        raise Http404
    return render(
        request,
        "lernen/material_kind.html",
        {"m": material, "phase": material_selectors.KIND_PHASE[material.status]},
    )


# --- Datei -----------------------------------------------------------------------------------


def _antwort_datei(material):
    pfad = material_services.datei_oeffnen(material)
    if pfad is None or material.mime not in _MIME:
        raise Http404
    ext = material.name.rpartition(".")[2]
    antwort = FileResponse(open(pfad, "rb"), content_type=_MIME[material.mime])  # noqa: SIM115
    bild = material.mime == "image/jpeg"
    antwort["Content-Disposition"] = (
        f'{"inline" if bild else "attachment"}; filename="material-{material.pk}.{ext}"'
    )
    antwort["Cache-Control"] = "private, no-store, max-age=0"
    antwort["X-Content-Type-Options"] = "nosniff"
    antwort["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return antwort


@require_GET
def datei(request, pk):
    """Original oder Bild: Eltern jedes, Kinder nur das eigene."""
    eltern = aktueller_elternteil(request)
    kind = aktuelles_kind(request)
    if eltern is None and kind is None:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), resolve_url("konten:start"))
        raise PermissionDenied
    material = (
        material_selectors.material(pk) if eltern else material_selectors.material_von(kind, pk)
    )
    if material is None:
        raise Http404
    return _antwort_datei(material)


# --- Eltern ----------------------------------------------------------------------------------


def _eltern_liste_kontext(*, fehler="", vorwahl=""):
    kinder = list(konten.aktive_kinder())
    zeilen = []
    for kind in kinder:
        belegt, limit = material_services.verbrauch(kind)
        zeilen.append(
            {
                "kind": kind,
                "material": list(material_selectors.materialien(kind)),
                "belegt_mb": _mb(belegt),
                "limit_mb": _mb(limit),
                "sofort": material_services.sofort_nutzbar(kind),
            }
        )
    return {
        "zeilen": zeilen,
        "wartend": material_selectors.warten_auf_eltern().filter(kind__in=kinder),
        "vorwahl": vorwahl,  # Kind aus dem Push-Link: seine wartenden Einträge sind angehakt
        "fehler": fehler,
    }


@nur_eltern
def eltern_liste(request):
    return render(
        request,
        "lernen/eltern_material.html",
        _eltern_liste_kontext(vorwahl=request.GET.get("kind", "")),
    )


def _detail_kontext(material, *, fehler=""):
    return {
        "m": material,
        "fragen": list(material_selectors.fragen_von(material)),
        "faecher": Fach.objects.filter(aktiv=True),
        "typen": FrageTyp.choices,
        "text_gekuerzt": material.text[:6000],
        "fehler": fehler,
        "fehlertext": material_services.fehlertext(material),
        "ki_bereit": ki_selectors.status_von(ki_selectors.zuordnung_fuer(KiAufgabe.AUSLESEN))
        is ki_selectors.KiStatus.BEREIT,
    }


def _detail_seite(request, material, *, fehler="", status=200):
    return render(
        request,
        "lernen/eltern_material_detail.html",
        _detail_kontext(material, fehler=fehler),
        status=status,
    )


def _material_oder_404(pk):
    material = material_selectors.material(pk)
    if material is None:
        raise Http404
    return material


@nur_eltern
def eltern_detail(request, pk):
    return _detail_seite(request, _material_oder_404(pk))


@nur_eltern
@require_POST
def eltern_aktion(request, pk, aktion):
    material = _material_oder_404(pk)
    p = request.POST
    ids = [int(x) for x in p.getlist("frage") if x.isdigit()]
    try:
        if aktion == "freigeben":
            material_services.freigeben(material, ids or None)
        elif aktion == "ablehnen":
            material_services.ablehnen(material, ids or None)
        elif aktion == "neu":
            material_services.neu_starten(material)
        elif aktion == "fach":
            fach = get_object_or_404(Fach, pk=int(p["fach"]) if p.get("fach", "").isdigit() else 0)
            material_services.fach_aendern(material, fach, p.get("thema", ""))
        elif aktion == "frage_neu":
            material_services.manuelle_frage(
                material, p.get("typ", ""), p.get("frage", ""), p.get("antwort", "")
            )
        elif aktion == "loeschen":
            material_services.loeschen(material)
            return redirect("lernen:eltern_material")
        else:
            raise Http404
    except material_services.MaterialFehler as exc:
        material.refresh_from_db()
        return _detail_seite(request, material, fehler=str(exc), status=400)
    return redirect("lernen:eltern_material_detail", pk=material.pk)


@nur_eltern
@require_POST
def eltern_frage(request, pk, frage_pk):
    material = _material_oder_404(pk)
    try:
        material_services.frage_bearbeiten(
            material, frage_pk, request.POST.get("frage", ""), request.POST.get("antwort", "")
        )
    except material_services.MaterialFehler as exc:
        return _detail_seite(request, material, fehler=str(exc), status=400)
    return redirect("lernen:eltern_material_detail", pk=material.pk)


@nur_eltern
@require_POST
def eltern_sammel(request):
    """Mehrere Materialien auf einmal freigeben oder ablehnen (nur wartende Fragen)."""
    aktion = request.POST.get("aktion")
    if aktion not in ("freigeben", "ablehnen"):
        raise Http404
    ids = [int(x) for x in request.POST.getlist("material") if x.isdigit()]
    funktion = material_services.freigeben if aktion == "freigeben" else material_services.ablehnen
    for material in material_selectors.alle_materialien().filter(
        pk__in=ids, kind__in=konten.aktive_kinder()
    ):
        funktion(material)
    return redirect("lernen:eltern_material")


@nur_eltern
@require_POST
def eltern_regel(request):
    try:
        kind = get_object_or_404(konten.aktive_kinder(), pk=request.POST.get("kind"))
    except (ValueError, ValidationError):
        raise Http404 from None
    material_services.sofort_nutzbar_setzen(kind, request.POST.get("sofort") == "1")
    return redirect("lernen:eltern_material")
