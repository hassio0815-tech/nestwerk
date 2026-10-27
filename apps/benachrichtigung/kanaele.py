"""Eingebaute Kanäle: E-Mail, Pop-up (Web-Push: ``push.PushKanal``)."""

import logging

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_noop

from apps.kern import adressen
from apps.kern import sprache as kern_sprache
from apps.konten import selectors as konten_selectors

from . import mail, registry
from .models import Popup, SmtpKonto

logger = logging.getLogger("nestwerk.benachrichtigung")


def absolute_url(pfad):
    basis = adressen.basis_url()
    return f"{basis}{pfad}" if pfad else ""


class EmailKanal(registry.ZustellKanal):
    slug = "email"
    bezeichnung = gettext_noop("E-Mail")
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
        # Worker ohne Request: Mail in der Sprache des Empfängers
        with translation.override(kern_sprache.fuer(b.empfaenger)):
            text = render_to_string("benachrichtigung/email.txt", kontext)
            html = render_to_string("benachrichtigung/email.html", kontext)
        try:
            mail.senden(daten, adresse, f"Nestwerk: {b.titel}", text, html)
        except Exception as exc:
            raise mail.MailFehler(f"{type(exc).__name__}: {mail.bereinigen(exc, daten)}") from None


class PopupKanal(registry.ZustellKanal):
    slug = "popup"
    bezeichnung = gettext_noop("Pop-up in der App")
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


def eingebaute_registrieren():
    from .push import PushKanal  # push importiert absolute_url aus diesem Modul

    registry.kanal_registrieren(EmailKanal())
    registry.kanal_registrieren(PopupKanal())
    registry.kanal_registrieren(PushKanal())
