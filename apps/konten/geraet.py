"""Geräte-Erkennung (ARCHITECTURE 4.4). Öffentliche API für andere Apps:

- ``aktuelles_geraet(request)`` -> ``Geraet`` oder ``None``
- ``ist_kiosk(request)`` -> ``True``, wenn die Anfrage vom registrierten Kiosk-Gerät kommt

Das Gerät steckt als signiertes, httpOnly-Cookie ``nestwerk_geraet`` (nur die UUID) beim Client.
Ein gefälschtes oder fremd signiertes Cookie wird ignoriert; ein widerrufenes Gerät (aktiv =
False) gilt als unbekannt.
"""

from datetime import timedelta

from django.core import signing
from django.utils import timezone

from .models import Geraet

COOKIE_NAME = "nestwerk_geraet"
COOKIE_SALT = "konten.geraet"
COOKIE_MAX_AGE = 10 * 365 * 24 * 3600
GESEHEN_ABSTAND = timedelta(hours=1)


def aktuelles_geraet(request):
    return getattr(request, "geraet", None)


def ist_kiosk(request):
    geraet = aktuelles_geraet(request)
    return bool(geraet and geraet.ist_kiosk)


def geraet_aus_cookie(request):
    """Liest und prüft das Cookie. Aktualisiert ``zuletzt_gesehen`` höchstens stündlich."""
    try:
        geraete_id = request.get_signed_cookie(
            COOKIE_NAME, salt=COOKIE_SALT, max_age=COOKIE_MAX_AGE
        )
    except (KeyError, signing.BadSignature):
        return None
    geraet = Geraet.objects.filter(pk=geraete_id, aktiv=True).first()
    if geraet is None:
        return None
    jetzt = timezone.now()
    if geraet.zuletzt_gesehen is None or jetzt - geraet.zuletzt_gesehen > GESEHEN_ABSTAND:
        Geraet.objects.filter(pk=geraet.pk).update(zuletzt_gesehen=jetzt)
        geraet.zuletzt_gesehen = jetzt
    return geraet


def cookie_setzen(request, response, geraet):
    response.set_signed_cookie(
        COOKIE_NAME,
        str(geraet.pk),
        salt=COOKIE_SALT,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=request.is_secure(),
        samesite="Lax",
    )


def cookie_loeschen(response):
    response.delete_cookie(COOKIE_NAME)
