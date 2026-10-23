from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def styleguide(request):
    """Entwicklungsansicht aller Komponenten. Ohne DEBUG nicht erreichbar."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "oberflaeche/styleguide.html")
