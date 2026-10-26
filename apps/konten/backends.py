"""Anmelde-Backends. Sie unterscheiden sich über ihre Schlüsselwörter, ``authenticate`` wählt
das passende: ``authenticate(request, eltern=<Benutzer>, passwort=...)`` bzw.
``authenticate(request, kind=<Benutzer>, pin=...)``.

Das Rate-Limit sitzt hier (nicht nur in den Views): wer ``authenticate`` aufruft, kann die
Sperre nicht umgehen. Bei aktiver Sperre wird das Geheimnis gar nicht erst geprüft und der
Versuch nicht gezählt (``PermissionDenied`` -> ``authenticate`` liefert ``None``).
"""

import re

from django.contrib.auth.hashers import check_password
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.kern import zeit

from . import netz, sperre
from .models import AnmeldeArt, AnmeldeVersuch, Benutzer, ElternZugang, KindProfil, Rolle

PIN_MUSTER = re.compile(r"^\d{4}$")


class _BasisBackend:
    def get_user(self, user_id):
        try:
            benutzer = Benutzer.objects.get(pk=user_id)
        except (Benutzer.DoesNotExist, ValueError, TypeError):
            return None
        return benutzer if benutzer.aktiv else None


def _versuch_festhalten(request, art, benutzer, ip, erfolgreich):
    AnmeldeVersuch.objects.create(
        zeit=zeit.jetzt(),
        art=art,
        benutzer=benutzer,
        ip=ip,
        geraet=getattr(request, "geraet", None),
        erfolgreich=erfolgreich,
    )


class ElternBackend(_BasisBackend):
    """Gemeinsames Eltern-Passwort + gewählter Elternteil."""

    def authenticate(self, request, eltern=None, passwort=None):
        if eltern is None or passwort is None:
            return None
        if eltern.rolle != Rolle.ELTERN or not eltern.aktiv:
            return None
        ip = netz.client_ip_text(request) if request is not None else None
        jetzt = zeit.jetzt()
        with transaction.atomic():
            if sperre.eltern_gesperrt_bis(ip, jetzt):
                raise PermissionDenied("Eltern-Login gesperrt")
            zugang = ElternZugang.objects.filter(pk=1).first()
            # Ohne gesetztes Passwort ist kein Login möglich
            ok = bool(zugang) and check_password(passwort, zugang.passwort_hash)
            _versuch_festhalten(request, AnmeldeArt.ELTERN, eltern, ip, ok)
        return eltern if ok else None


class KindBackend(_BasisBackend):
    """Persönliche vierstellige PIN, Zähler und Sperre je Kind."""

    def authenticate(self, request, kind=None, pin=None):
        if kind is None or pin is None:
            return None
        if kind.rolle != Rolle.KIND or not kind.aktiv:
            return None
        ip = netz.client_ip_text(request) if request is not None else None
        jetzt = zeit.jetzt()
        with transaction.atomic():
            profil = KindProfil.objects.select_for_update().filter(benutzer=kind).first()
            if profil is None:
                return None
            if sperre.kind_gesperrt_bis(profil, jetzt):
                raise PermissionDenied("PIN gesperrt")
            ok = bool(PIN_MUSTER.match(str(pin))) and check_password(str(pin), profil.pin_hash)
            if ok:
                sperre.kind_zuruecksetzen(profil)
            else:
                sperre.kind_fehlversuch_erfassen(profil, jetzt)
            _versuch_festhalten(request, AnmeldeArt.KIND, kind, ip, ok)
        return kind if ok else None
