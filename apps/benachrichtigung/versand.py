"""Versand fälliger Zustellungen (Worker-Nachlauf, ARCHITECTURE 5.3).

Jede Zustellung wird kurz per bedingtem UPDATE beansprucht (Lease), dann **außerhalb** einer
Transaktion gesendet (kein DB-Lock während SMTP) und das Ergebnis gebucht. Stürzt der Worker
dazwischen ab, wird nach Ablauf der Lease erneut gesendet (mindestens einmal).
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import F

from apps.kern import einstellungen, zeit

from . import registry, ruhezeit
from .models import Ruhezeit, ZustellStatus, Zustellung

logger = logging.getLogger("nestwerk.benachrichtigung")

OFFENE = (ZustellStatus.OFFEN, ZustellStatus.FEHLER)
LEASE = timedelta(minutes=5)
BACKOFF_BASIS = timedelta(minutes=1)
BACKOFF_MAX = timedelta(hours=1)
FEHLER_MAX_ZEICHEN = 1000


def backoff(versuche):
    return min(BACKOFF_MAX, BACKOFF_BASIS * 2 ** max(versuche - 1, 0))


def zustellungen_senden(stapel=20):
    """Sendet fällige Zustellungen. Gibt die Anzahl bearbeiteter zurück (Worker-Nachlauf)."""
    faellig = list(
        Zustellung.objects.filter(status__in=OFFENE, naechster_versuch__lte=zeit.jetzt())
        .order_by("naechster_versuch", "id")
        .values_list("id", flat=True)[:stapel]
    )
    return sum(1 for zid in faellig if zustellung_senden(zid) is not None)


def zustellung_senden(zid):
    """Sendet eine Zustellung; Rückgabe: neuer Status oder ``None`` (nicht fällig/übernommen)."""
    jetzt = zeit.jetzt()
    with transaction.atomic():
        beansprucht = Zustellung.objects.filter(
            pk=zid, status__in=OFFENE, naechster_versuch__lte=jetzt
        ).update(versuche=F("versuche") + 1, naechster_versuch=jetzt + LEASE)
        if not beansprucht:
            return None
        zustellung = Zustellung.objects.select_related(
            "benachrichtigung__empfaenger", "benachrichtigung__ereignis", "kanal"
        ).get(pk=zid)

    max_versuche = einstellungen.wert("benachrichtigung.zustellung_max_versuche")
    felder = {"fehler": "", "naechster_versuch": None}
    if _jetzt_ruhezeit(zustellung):
        # B-19: Wiederholung (oder verspäteter Versand) fällt in die Ruhezeit des Empfängers ->
        # stumm wie beim Routing, nicht nachholen (ARCHITECTURE 5.3)
        felder.update(status=ZustellStatus.UNTERDRUECKT_RUHEZEIT)
        Zustellung.objects.filter(pk=zid).update(**felder)
        return felder["status"]
    try:
        registry.kanal(zustellung.kanal_id).senden(zustellung)
    except registry.NichtKonfiguriert as exc:
        felder.update(status=ZustellStatus.NICHT_KONFIGURIERT, fehler=str(exc))
    except registry.DauerhafterFehler as exc:
        felder.update(status=ZustellStatus.AUFGEGEBEN, fehler=str(exc))
    except registry.UnbekannterEintrag as exc:
        felder.update(status=ZustellStatus.AUFGEGEBEN, fehler=str(exc))
    except Exception as exc:
        # Nur die Ausnahmeklasse und der (bereinigte) Text, nie ein Traceback mit Zugangsdaten
        logger.warning("Zustellung %s fehlgeschlagen: %s: %s", zid, type(exc).__name__, exc)
        text = f"{type(exc).__name__}: {exc}"[:FEHLER_MAX_ZEICHEN]
        if zustellung.versuche >= max_versuche:
            felder.update(status=ZustellStatus.AUFGEGEBEN, fehler=text)
        else:
            felder.update(
                status=ZustellStatus.FEHLER,
                fehler=text,
                naechster_versuch=zeit.jetzt() + backoff(zustellung.versuche),
            )
    else:
        felder.update(status=ZustellStatus.GESENDET, gesendet_am=zeit.jetzt())
    Zustellung.objects.filter(pk=zid).update(**felder)
    return felder["status"]


def _jetzt_ruhezeit(zustellung) -> bool:
    empfaenger = zustellung.benachrichtigung.empfaenger
    if empfaenger.rolle != "eltern":
        return False
    try:
        return ruhezeit.unterdrueckt(
            list(Ruhezeit.objects.filter(benutzer=empfaenger)), zustellung.kanal_id, zeit.jetzt()
        )
    except registry.UnbekannterEintrag:
        return False
