"""E-Mail-Versand über das Django-Mail-Backend (``EMAIL_BACKEND``; in Tests locmem).

SMTP-Daten kommen aus ``SmtpKonto`` (Passwort entschlüsselt nur im Speicher, für den Versand)
oder als ``SmtpDaten`` (Einrichtungs-Assistent, Test vor dem Speichern).
"""

from dataclasses import dataclass, field

from django.core.mail import EmailMultiAlternatives, get_connection

from . import crypto
from .models import SmtpSicherheit

TIMEOUT_SEKUNDEN = 15


class MailFehler(Exception):
    """Versand fehlgeschlagen; der Text enthält nie das Passwort."""


@dataclass(frozen=True)
class SmtpDaten:
    host: str
    port: int
    sicherheit: str
    benutzername: str
    passwort: str = field(repr=False)
    absender: str


def daten_aus_konto(konto):
    return SmtpDaten(
        host=konto.host,
        port=konto.port,
        sicherheit=konto.sicherheit,
        benutzername=konto.benutzername,
        passwort=crypto.entschluesseln(konto.passwort_verschluesselt),
        absender=konto.absender,
    )


def verbindung(daten):
    return get_connection(
        host=daten.host,
        port=daten.port,
        username=daten.benutzername,
        password=daten.passwort,
        use_tls=daten.sicherheit == SmtpSicherheit.STARTTLS,
        use_ssl=daten.sicherheit == SmtpSicherheit.SSL,
        timeout=TIMEOUT_SEKUNDEN,
    )


def senden(daten, an, betreff, text, html=None):
    nachricht = EmailMultiAlternatives(
        subject=betreff,
        body=text,
        from_email=daten.absender,
        to=[an],
        connection=verbindung(daten),
    )
    if html:
        nachricht.attach_alternative(html, "text/html")
    nachricht.send(fail_silently=False)


def bereinigen(text, daten):
    """Entfernt das Passwort aus Fehlertexten (Logs, Zustellung, Anzeige)."""
    text = str(text)
    if daten is not None and daten.passwort:
        text = text.replace(daten.passwort, "***")
    return text
