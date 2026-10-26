"""Sitzungsdauer und Leerlauf (ARCHITECTURE 4.2-4.4). Zustand liegt in der Django-Session.

Session-Schlüssel (alle mit Präfix ``nestwerk_``):
- ``nestwerk_kiosk``: Sitzung wurde auf einem Kiosk-Gerät begonnen
- ``nestwerk_aktivitaet``: Zeitpunkt (Unix-Sekunden) der letzten **aktiven** Anfrage
- ``nestwerk_gleitend``: Sekunden, auf die eine gleitende Sitzung bei Nutzung verlängert wird
- ``nestwerk_verlaengert``: wann zuletzt verlängert wurde (Schreibzugriffe begrenzen)
- ``nestwerk_geraet_id``: registriertes Gerät, auf dem die Sitzung begann (oder ``None``). Wird es
  widerrufen (oder fehlt sein Cookie), endet die Sitzung beim nächsten Aufruf (Review AP19,
  B-06): ein verlorenes/abgegebenes Gerät lässt sich so abmelden, auch das Flur-Tablet.
"""

from django.contrib.auth import login, logout

from apps.kern import audit, einstellungen, zeit

from .models import Rolle

KIOSK = "nestwerk_kiosk"
AKTIVITAET = "nestwerk_aktivitaet"
GLEITEND = "nestwerk_gleitend"
VERLAENGERT = "nestwerk_verlaengert"
GERAET = "nestwerk_geraet_id"

# Gleitende Sitzungen werden höchstens so oft neu geschrieben (Sekunden)
VERLAENGERUNG_ABSTAND = 3600
# Aktivität wird höchstens so oft in die Session geschrieben (Sekunden)
AKTIVITAET_ABSTAND = 5


def sitzung_beginnen(request, benutzer, *, vertraut=False):
    """Meldet an, legt die Sitzungsrichtlinie fest und protokolliert. ``vertraut`` gilt nur
    für Eltern und nur auf nicht-Kiosk-Geräten."""
    geraet = getattr(request, "geraet", None)
    kiosk = bool(geraet and geraet.ist_kiosk)
    cfg = einstellungen.werte(
        "konten.sitzung_eltern_vertraut_tage",
        "konten.sitzung_eltern_stunden",
        "konten.sitzung_kind_persoenlich_tage",
    )
    gleitend = 0
    if kiosk:
        # Harte Obergrenze; der Leerlauf beendet die Sitzung viel früher
        dauer = cfg["konten.sitzung_eltern_stunden"] * 3600
    elif benutzer.rolle == Rolle.KIND:
        dauer = gleitend = cfg["konten.sitzung_kind_persoenlich_tage"] * 86400
    elif vertraut:
        dauer = gleitend = cfg["konten.sitzung_eltern_vertraut_tage"] * 86400
    else:
        dauer = cfg["konten.sitzung_eltern_stunden"] * 3600

    login(request, benutzer, backend=benutzer.backend)
    jetzt = zeit.jetzt().timestamp()
    request.session[KIOSK] = kiosk
    request.session[AKTIVITAET] = jetzt
    request.session[GLEITEND] = gleitend
    request.session[VERLAENGERT] = jetzt
    request.session[GERAET] = str(geraet.pk) if geraet else None
    request.session.set_expiry(dauer)
    audit.protokollieren(
        "konten.angemeldet",
        akteur=benutzer,
        geraet=geraet,
        details={"kiosk": kiosk, "vertrautes_geraet": bool(vertraut and not kiosk)},
    )


def ist_kiosk_sitzung(request):
    geraet = getattr(request, "geraet", None)
    return bool(request.session.get(KIOSK) or (geraet and geraet.ist_kiosk))


def leerlauf_abgelaufen(request, jetzt):
    """Kiosk-Sitzung: letzte aktive Anfrage länger her als der Leerlauf?"""
    letzte = request.session.get(AKTIVITAET)
    grenze = einstellungen.wert("konten.kiosk_leerlauf_sekunden")
    return letzte is None or jetzt - letzte > grenze


def aktivitaet_vermerken(request, jetzt):
    """Eine **aktive** Anfrage verlängert die Sitzung (Kiosk: Leerlauf; sonst gleitend)."""
    session = request.session
    letzte = session.get(AKTIVITAET)
    if letzte is None or jetzt - letzte >= AKTIVITAET_ABSTAND:
        session[AKTIVITAET] = jetzt
    gleitend = session.get(GLEITEND, 0)
    if gleitend and jetzt - session.get(VERLAENGERT, 0) >= VERLAENGERUNG_ABSTAND:
        session.set_expiry(gleitend)
        session[VERLAENGERT] = jetzt


def geraet_widerrufen(request):
    """Begann die Sitzung auf einem registrierten Gerät, das nicht mehr gültig ist?"""
    erwartet = request.session.get(GERAET)
    if not erwartet:
        return False
    geraet = getattr(request, "geraet", None)
    return geraet is None or str(geraet.pk) != erwartet


def wegen_leerlauf_abmelden(request, grund="leerlauf"):
    benutzer = request.user
    audit.protokollieren(
        "konten.sitzung_abgelaufen",
        akteur=benutzer,
        geraet=getattr(request, "geraet", None),
        details={"grund": grund},
    )
    logout(request)
