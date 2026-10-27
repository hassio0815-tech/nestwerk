"""Kinder- und Elternverwaltung nach der Einrichtung (Eltern)."""

from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_POST

from apps.konten import selectors, services
from apps.konten.models import ElternLabel, Rolle
from apps.konten.zugriff import nur_eltern

MELDUNGEN = {
    "kind_neu": gettext_lazy("Kind angelegt."),
    "umbenannt": gettext_lazy("Name geändert."),
    "pin": gettext_lazy("PIN zurückgesetzt."),
    "entsperrt": gettext_lazy("PIN-Sperre aufgehoben."),
    "deaktiviert": gettext_lazy("Kind deaktiviert."),
    "eltern": gettext_lazy("Angaben gespeichert."),
    "passwort": gettext_lazy("Familien-Passwort geändert."),
}


def _seite(request, *, fehler=None, status=200):
    eltern = []
    for e in selectors.aktive_eltern().select_related("elternprofil"):
        eltern.append({"benutzer": e, "profil": e.elternprofil})
    gesperrt = set(selectors.gesperrte_kinder())
    kinder = [
        {"benutzer": k, "gesperrt": k in gesperrt}
        for k in selectors.aktive_kinder().order_by("reihenfolge", "anzeigename")
    ]
    kontext = {
        "kinder": kinder,
        "eltern": eltern,
        "labels": ElternLabel.choices,
        "fehler": fehler or {},
        "ok": MELDUNGEN.get(request.GET.get("ok", ""), ""),
    }
    return render(request, "oberflaeche/familie.html", kontext, status=status)


def _fertig(code, anker=""):
    return redirect(f"{reverse('oberflaeche:familie')}?ok={code}{anker}")


def _meldung(exc):
    return " ".join(exc.messages)


@nur_eltern
@require_GET
def uebersicht(request):
    return _seite(request)


@nur_eltern
@require_POST
def kind_neu(request):
    name = request.POST.get("anzeigename", "").strip()
    try:
        with transaction.atomic():
            naechste = selectors.aktive_kinder().count() + 1
            services.kind_anlegen(name, request.POST.get("pin", ""), reihenfolge=naechste)
    except ValidationError as exc:
        return _seite(request, fehler={"kind_neu": _meldung(exc)}, status=422)
    return _fertig("kind_neu")


def _kind(kind_id):
    return get_object_or_404(selectors.aktive_kinder(), pk=kind_id)


@nur_eltern
@require_POST
def kind_umbenennen(request, kind_id):
    kind = _kind(kind_id)
    try:
        services.kind_umbenennen(kind, request.POST.get("anzeigename", "").strip())
    except ValidationError as exc:
        return _seite(request, fehler={f"kind_{kind.pk}": _meldung(exc)}, status=422)
    return _fertig("umbenannt")


@nur_eltern
@require_POST
def kind_pin(request, kind_id):
    kind = _kind(kind_id)
    try:
        services.pin_setzen(kind, request.POST.get("pin", ""))
    except ValidationError as exc:
        return _seite(request, fehler={f"kind_{kind.pk}": _meldung(exc)}, status=422)
    return _fertig("pin")


@nur_eltern
@require_POST
def kind_entsperren(request, kind_id):
    services.kind_entsperren(_kind(kind_id))
    return _fertig("entsperrt")


@nur_eltern
@require_POST
def kind_deaktivieren(request, kind_id):
    services.benutzer_deaktivieren(_kind(kind_id))
    return _fertig("deaktiviert")


@nur_eltern
@require_POST
def eltern_aendern(request, eltern_id):
    elternteil = get_object_or_404(selectors.aktive_eltern(), pk=eltern_id, rolle=Rolle.ELTERN)
    try:
        services.eltern_aendern(
            elternteil,
            request.POST.get("anzeigename", "").strip(),
            rolle_label=request.POST.get("rolle_label", ""),
            email=request.POST.get("email", "").strip(),
        )
    except ValidationError as exc:
        return _seite(request, fehler={f"eltern_{elternteil.pk}": _meldung(exc)}, status=422)
    return _fertig("eltern")


@nur_eltern
@require_POST
def passwort(request):
    neu = request.POST.get("passwort", "")
    if neu != request.POST.get("passwort2", ""):
        return _seite(
            request, fehler={"passwort": _("Die beiden Eingaben sind verschieden.")}, status=422
        )
    try:
        services.eltern_passwort_setzen(neu)
    except ValidationError as exc:
        return _seite(request, fehler={"passwort": _meldung(exc)}, status=422)
    # Andere Eltern-Sitzungen enden (Prüfsumme enthält das Passwort), die eigene bleibt
    update_session_auth_hash(request, request.user)
    return _fertig("passwort")
