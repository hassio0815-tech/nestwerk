"""Geschützte Auslieferung der Nachweis-Fotos (AP13): nur Eltern, das meldende Kind nur solange
die Meldung offen ist. Immer ``Cache-Control: no-store``, nie ein direkter Dateipfad."""

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, resolve_url
from django.views.decorators.http import require_GET

from apps.konten.models import Rolle

from . import nachweise
from .models import MELDUNG_LAUFEND, Meldung


@require_GET
def nachweis_bild(request, meldung_id, name):
    user = request.user
    if not user.is_authenticated:
        return redirect_to_login(request.get_full_path(), resolve_url("konten:start"))
    if user.rolle == Rolle.ELTERN:
        meldung = get_object_or_404(Meldung, pk=meldung_id)
    elif user.rolle == Rolle.KIND:
        meldung = Meldung.objects.filter(pk=meldung_id).first()
        if meldung is None or meldung.kind_id != user.pk or meldung.status not in MELDUNG_LAUFEND:
            raise PermissionDenied
    else:
        raise PermissionDenied
    pfad = nachweise.datei_pfad(meldung.pk, name)
    if pfad is None:
        raise Http404
    antwort = FileResponse(open(pfad, "rb"), content_type="image/jpeg")  # noqa: SIM115
    antwort["Cache-Control"] = "private, no-store, max-age=0"
    antwort["X-Content-Type-Options"] = "nosniff"
    antwort["Content-Disposition"] = 'inline; filename="nachweis.jpg"'
    return antwort
