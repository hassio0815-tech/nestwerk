"""Obergrenze für Upload-Anfragen (Review AP19, B-07).

Django begrenzt hochgeladene Dateien nicht: Ein beliebig großer Upload landet komplett in einer
temporären Datei, bevor eine View (oder schon die CSRF-Prüfung, die ``request.POST`` liest) ihn
abweisen kann. Diese Middleware steht deshalb **vor** ``CsrfViewMiddleware`` und lehnt Anfragen
ab, deren ``Content-Length`` größer ist als die größte zulässige Meldung
(``aufgaben.nachweis_max_anzahl`` × ``aufgaben.nachweis_max_upload_mb`` + 1 MB Puffer). Die
App kennt keine anderen Uploads; normale Formulare sind um Größenordnungen kleiner.
"""

from django.http import HttpResponse
from django.utils.translation import gettext_lazy

from apps.kern.einstellungen import EinstellungFehlt

from . import nachweise

MELDUNG = gettext_lazy("Die Fotos sind zu groß. Bitte ein kleineres Foto nehmen.")


class UploadGrenze:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        laenge = request.META.get("CONTENT_LENGTH")
        if request.method == "POST" and laenge and laenge != "0":
            try:
                zu_gross = nachweise.anfrage_zu_gross(laenge)
            except EinstellungFehlt:  # vor der Einrichtung: keine Grenze bekannt
                zu_gross = False
            if zu_gross:
                return HttpResponse(
                    str(MELDUNG), status=413, content_type="text/plain; charset=utf-8"
                )
        return self.get_response(request)
