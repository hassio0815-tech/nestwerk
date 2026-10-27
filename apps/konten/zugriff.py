"""Rollenschutz und aktuelle Person (ARCHITECTURE 4.5). Öffentliche API:

- Decorator ``nur_eltern``, ``nur_kind``, ``eigenes_kind(parameter="kind_id")``
- Mixins ``NurElternMixin``, ``NurKindMixin``, ``EigenesKindMixin``
- ``aktueller_elternteil(request)``, ``aktuelles_kind(request)`` (``None`` = nicht passend)
- ``passiv`` markiert Polling-Endpunkte: sie verlängern eine Tablet-Sitzung nicht

Nicht angemeldet -> Weiterleitung zur passenden Anmeldung (HTMX: 401 + ``HX-Redirect``).
Angemeldet mit falscher Rolle -> 403 (ein Kind öffnet nie eine Eltern-URL).
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import resolve_url

from .models import Rolle

PASSIV_ATTRIBUT = "nestwerk_passiv"


def aktueller_elternteil(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.rolle == Rolle.ELTERN:
        return user
    return None


def aktuelles_kind(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.rolle == Rolle.KIND:
        return user
    return None


def passiv(view):
    """Markiert eine View als passiv (Polling/Live-Aktualisierung): Aufrufe zählen nicht als
    Aktivität. Bei Klassen-Views ``passiv(Klasse.as_view())`` in der URL-Konfiguration."""
    setattr(view, PASSIV_ATTRIBUT, True)
    return view


def ist_passiv(view):
    return bool(getattr(view, PASSIV_ATTRIBUT, False))


def _nicht_angemeldet(request, anmelde_url):
    ziel = resolve_url(anmelde_url)
    if request.headers.get("HX-Request"):
        return HttpResponse(status=401, headers={"HX-Redirect": ziel})
    return redirect_to_login(request.get_full_path(), ziel)


def _rolle_verlangen(rollen, anmelde_url):
    def dekorator(view):
        @wraps(view)
        def umhuellung(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return _nicht_angemeldet(request, anmelde_url)
            if user.rolle not in rollen:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return umhuellung

    return dekorator


def nur_eltern(view):
    return _rolle_verlangen({Rolle.ELTERN}, "konten:eltern_login")(view)


def nur_kind(view):
    return _rolle_verlangen({Rolle.KIND}, "konten:start")(view)


def angemeldet(view):
    """Eltern und Kinder (z. B. eigene Einstellungen); sonst zurück zur Startseite."""
    return _rolle_verlangen({Rolle.ELTERN, Rolle.KIND}, "konten:start")(view)


def eigenes_kind(parameter="kind_id"):
    """Kind nur für das eigene Konto (URL-Parameter ``parameter`` = Benutzer-UUID); Eltern
    dürfen jedes Kind sehen."""

    def dekorator(view):
        @wraps(view)
        def umhuellung(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return _nicht_angemeldet(request, "konten:start")
            if user.rolle == Rolle.KIND and str(kwargs.get(parameter)) != str(user.pk):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return umhuellung

    return dekorator


class NurElternMixin:
    @classmethod
    def as_view(cls, **initkwargs):
        return nur_eltern(super().as_view(**initkwargs))


class NurKindMixin:
    @classmethod
    def as_view(cls, **initkwargs):
        return nur_kind(super().as_view(**initkwargs))


class EigenesKindMixin:
    kind_parameter = "kind_id"

    @classmethod
    def as_view(cls, **initkwargs):
        return eigenes_kind(cls.kind_parameter)(super().as_view(**initkwargs))
