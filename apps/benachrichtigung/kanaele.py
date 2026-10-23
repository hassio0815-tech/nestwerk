"""Eingebaute Kanäle: E-Mail, Pop-up und der Platzhalter für Web-Push."""

import logging

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.konten import selectors as konten_selectors

from . import mail, registry
from .models import Popup, SmtpKonto

logger = logging.getLogger("famko.benachrichtigung")


def absolute_url(pfad):
    basis = (getattr(settings, "BASIS_URL", "") or "").rstrip("/")
    return f"{basis}{pfad}" if pfad else ""


class EmailKanal(registry.ZustellKanal):
    slug = "email"
    bezeichnung = "E-Mail"
    rollen = ("eltern",)
    ruhezeit = registry.OPTIONAL  # läuft in Ruhezeiten weiter, außer die Ruhezeit verlangt es (K7)

    def senden(self, zustellung):
        konto = SmtpKonto.objects.first()
        if konto is None:
            raise registry.NichtKonfiguriert("E-Mail-Postausgang ist nicht eingerichtet")
        b = zustellung.benachrichtigung
        adresse = konten_selectors.eltern_email(b.empfaenger)
        if not adresse:
            raise registry.DauerhafterFehler("Keine E-Mail-Adresse hinterlegt")
        daten = mail.daten_aus_konto(konto)
        kontext = {
            "titel": b.titel,
            "text": b.text,
            "link": absolute_url(b.link),
            "einstellungen": absolute_url(reverse("benachrichtigung:einstellungen")),
            "empfaenger": b.empfaenger,
        }
        text = render_to_string("benachrichtigung/email.txt", kontext)
        html = render_to_string("benachrichtigung/email.html", kontext)
        try:
            mail.senden(daten, adresse, f"FamKo: {b.titel}", text, html)
        except Exception as exc:
            raise mail.MailFehler(f"{type(exc).__name__}: {mail.bereinigen(exc, daten)}") from None


class PopupKanal(registry.ZustellKanal):
    slug = "popup"
    bezeichnung = "Pop-up in der App"
    rollen = ("kind",)
    ruhezeit = registry.NIE

    def senden(self, zustellung):
        b = zustellung.benachrichtigung
        Popup.objects.get_or_create(
            benachrichtigung=b,
            defaults={
                "empfaenger_id": b.empfaenger_id,
                "art": b.ereignis.typ_id,
                "titel": b.titel,
                "text": b.text,
                "erstellt_am": timezone.now(),
            },
        )


class PushPlatzhalter(registry.ZustellKanal):
    """Schnittstelle für Web-Push. Die echte Umsetzung (VAPID, ``PushAbo`` verwalten, Versand)
    ersetzt diesen Kanal in AP08: ``kanal_registrieren(PushKanal(), ersetzen=True)``."""

    slug = "push"
    bezeichnung = "Push"

    def senden(self, zustellung):
        logger.warning(
            "Web-Push nicht konfiguriert: Zustellung %s (Benachrichtigung %s) nicht gesendet",
            zustellung.pk,
            zustellung.benachrichtigung_id,
        )
        raise registry.NichtKonfiguriert("Web-Push ist noch nicht eingerichtet")


def eingebaute_registrieren():
    registry.kanal_registrieren(EmailKanal())
    registry.kanal_registrieren(PopupKanal())
    registry.kanal_registrieren(PushPlatzhalter())
