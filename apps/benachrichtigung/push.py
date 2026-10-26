"""Web-Push-Kanal (AP08): Abos verwalten und Nachrichten über pywebpush senden.

Nutzlast im Declarative-Web-Push-Format (RFC 8030-Versand, ``web_push: 8030``): iOS 18.4+
zeigt sie ohne Service-Worker-Code an. Der Service Worker (``sw.js``) liest dasselbe JSON im
``push``-Ereignis und zeigt klassisch an (Android Chrome, Desktop). ``navigate`` ist immer eine
absolute URL der eigenen Origin (Basis-URL). Keine Aktions-Buttons (iOS unterstützt sie nicht).
"""

import hashlib
import ipaddress
import json
import logging
import socket
from urllib.parse import urlsplit

from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from pywebpush import WebPushException, webpush

from apps.kern import adressen, audit, einstellungen
from apps.konten.models import Rolle

from . import pushschluessel as vapid
from . import registry, selectors, texte
from .kanaele import absolute_url
from .models import PushAbo

logger = logging.getLogger("nestwerk.benachrichtigung")

SENDE_TIMEOUT = 10
TITEL_MAX = 120
TEXT_MAX = 400
URGENCY_ENTSCHEIDUNG = "high"
URGENCY_STANDARD = "normal"
ABGELAUFEN = (404, 410)


class UngueltigesAbo(ValueError):
    """Das vom Browser gesendete Abo ist unvollständig oder unzulässig."""


class NichtAufloesbar(UngueltigesAbo):
    """Der Host des Endpoints lässt sich gerade nicht auflösen (kann vorübergehend sein)."""


ERLAUBTE_HOSTS_SCHLUESSEL = "benachrichtigung.push_erlaubte_hosts"


def _host_erlaubt(host, suffixe):
    return any(host == s or host.endswith("." + s) for s in suffixe)


def endpoint_pruefen(endpoint):
    """Prüft den Push-Endpoint (SSRF-Schutz, B-14): nur https, Port 443, Host per Suffix in der
    Einstellung ``benachrichtigung.push_erlaubte_hosts`` (Label-Grenze). IP-Literale und Hosts,
    die auf nicht öffentliche Adressen auflösen, sind immer gesperrt."""
    try:
        teile = urlsplit(endpoint)
        port = teile.port
        host = (teile.hostname or "").lower().rstrip(".")
    except ValueError:
        raise UngueltigesAbo("Endpoint ungültig") from None
    if teile.scheme != "https" or not host or len(endpoint) > 2000:
        raise UngueltigesAbo("Endpoint ungültig")
    if teile.username is not None or teile.password is not None or port not in (None, 443):
        raise UngueltigesAbo("Endpoint nicht erlaubt (nur https, Port 443)")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UngueltigesAbo("Endpoint nicht erlaubt (IP-Adressen sind gesperrt)")
    suffixe = [str(x).lower().strip(".") for x in einstellungen.wert(ERLAUBTE_HOSTS_SCHLUESSEL)]
    if not _host_erlaubt(host, suffixe):
        raise UngueltigesAbo("Dieser Push-Dienst ist nicht erlaubt")
    try:
        adressen_ = {info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise NichtAufloesbar("Push-Dienst nicht erreichbar (Namensauflösung)") from None
    for adresse in adressen_:
        try:
            ip = ipaddress.ip_address(adresse.split("%")[0])
        except ValueError:
            raise UngueltigesAbo("Endpoint nicht erlaubt") from None
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise UngueltigesAbo("Endpoint nicht erlaubt (nicht öffentliche Adresse)")


# --- Abos ------------------------------------------------------------------------------------


def endpoint_hash(endpoint):
    return hashlib.sha256(endpoint.encode()).hexdigest()


def abo_speichern(benutzer, daten, *, geraet=None, user_agent="", bezeichnung=""):
    """Legt das Abo eines Geräts an oder aktualisiert es (Dedupe über den Endpoint-Hash; ein
    Gerät, das den Benutzer wechselt, gehört danach dem neuen Benutzer)."""
    try:
        endpoint = str(daten["endpoint"])
        p256dh = str(daten["keys"]["p256dh"])
        auth = str(daten["keys"]["auth"])
    except (KeyError, TypeError):
        raise UngueltigesAbo("Abo unvollständig") from None
    endpoint_pruefen(endpoint)
    if not p256dh or len(p256dh) > 200 or not auth or len(auth) > 100:
        raise UngueltigesAbo("Schlüssel ungültig")
    abo, _ = PushAbo.objects.update_or_create(
        endpoint_hash=endpoint_hash(endpoint),
        defaults={
            "benutzer": benutzer,
            "geraet": geraet,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
            "bezeichnung": bezeichnung[:60],
            "user_agent": user_agent[:300],
            "aktiv": True,
            "fehlerzaehler": 0,
        },
    )
    return abo


def abo_entfernen(benutzer, endpoint):
    """Meldet das Abo ab (nur eigene). Gibt die Zahl gelöschter Abos zurück."""
    return PushAbo.objects.filter(
        benutzer=benutzer, endpoint_hash=endpoint_hash(endpoint or "")
    ).delete()[0]


def aktive_abos(benutzer):
    return PushAbo.objects.filter(benutzer=benutzer, aktiv=True).order_by("id")


# --- Nutzlast und Versand --------------------------------------------------------------------


def nutzlast(titel, text, navigate, badge=None):
    """Declarative-Web-Push-Nachricht, zugleich vom Service Worker lesbar."""
    notification = {"title": titel[:TITEL_MAX], "navigate": navigate}
    if text:
        notification["body"] = text[:TEXT_MAX]
    if badge is not None:
        notification["app_badge"] = int(badge)
    return {"web_push": 8030, "notification": notification}


def topic(schluessel):
    """Topic (RFC 8030, max. 32 URL-sichere Zeichen): gleiche Ziele ersetzen ältere Meldungen."""
    return hashlib.sha256(schluessel.encode()).hexdigest()[:32]


def _eigene_origin_url(pfad):
    if not adressen.basis_url():
        raise registry.NichtKonfiguriert("Basis-URL fehlt: Push braucht absolute Links")
    if not texte.ist_interner_pfad(pfad):
        pfad = "/"
    return absolute_url(pfad)


def abo_senden(abo, payload, *, ttl, urgency=URGENCY_STANDARD, topic_wert=None):
    """Sendet an ein Abo (prüft den Endpoint vorher erneut). 404/410 -> Abo deaktiviert und
    ``DauerhafterFehler``; jeder andere Fehler wird weitergereicht (Retry der Zustell-Logik)."""
    try:
        endpoint_pruefen(abo.endpoint)
    except NichtAufloesbar:
        _fehler_zaehlen(abo)
        raise RuntimeError("Push-Endpoint nicht auflösbar") from None
    except UngueltigesAbo as exc:
        PushAbo.objects.filter(pk=abo.pk).update(aktiv=False)
        audit.protokollieren(
            "benachrichtigung.push_endpoint_abgewiesen",
            akteur=None,
            objekt=abo,
            details={"grund": str(exc)},
        )
        raise registry.DauerhafterFehler("Push-Endpoint nicht zulässig, Abo deaktiviert") from None
    headers = {"Urgency": urgency}
    if topic_wert:
        headers["Topic"] = topic_wert
    try:
        webpush(
            subscription_info={
                "endpoint": abo.endpoint,
                "keys": {"p256dh": abo.p256dh, "auth": abo.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid.schluessel(),
            vapid_claims={"sub": vapid.kontakt()},
            ttl=ttl,
            headers=headers,
            timeout=SENDE_TIMEOUT,
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in ABGELAUFEN:
            PushAbo.objects.filter(pk=abo.pk).update(aktiv=False)
            raise registry.DauerhafterFehler(
                f"Push-Abo abgelaufen (HTTP {status}), deaktiviert"
            ) from None
        _fehler_zaehlen(abo)
        raise RuntimeError(f"Push-Dienst lehnt ab (HTTP {status or '?'})") from None
    except Exception:
        _fehler_zaehlen(abo)
        raise
    PushAbo.objects.filter(pk=abo.pk).update(zuletzt_ok=timezone.now(), fehlerzaehler=0)


def _fehler_zaehlen(abo):
    PushAbo.objects.filter(pk=abo.pk).update(fehlerzaehler=F("fehlerzaehler") + 1)


class PushKanal(registry.ZustellKanal):
    slug = "push"
    bezeichnung = "Push"

    def ziele(self, benutzer):
        """Ein Ziel je aktivem Gerät. Ohne Gerät bleibt eine Zustellung ohne Ziel, damit die
        Liste „Push: nicht eingerichtet“ zeigt."""
        return list(aktive_abos(benutzer)) or [None]

    def senden(self, zustellung):
        abo = zustellung.push_abo
        if abo is None:
            raise registry.NichtKonfiguriert("Kein Gerät für Push angemeldet")
        if not abo.aktiv:
            raise registry.DauerhafterFehler("Push-Abo ist nicht mehr aktiv")
        b = zustellung.benachrichtigung
        typ = b.ereignis.typ
        ttl = typ.push_ttl_sekunden or einstellungen.wert(
            "benachrichtigung.push_ttl_standard_sekunden"
        )
        standard = "/eltern/benachrichtigungen/" if b.empfaenger.rolle == Rolle.ELTERN else "/"
        payload = nutzlast(
            b.titel,
            b.text,
            _eigene_origin_url(b.link or standard),
            badge=selectors.ungelesen(b.empfaenger),
        )
        abo_senden(
            abo,
            payload,
            ttl=ttl,
            urgency=URGENCY_ENTSCHEIDUNG if selectors.ist_entscheidung(typ) else URGENCY_STANDARD,
            topic_wert=topic(b.link or typ.slug),
        )


def probe_senden(benutzer):
    """Test-Push an alle aktiven Geräte des Benutzers. Gibt ``(gesendet, fehlgeschlagen)``
    zurück. ``NichtKonfiguriert`` (BASIS_URL fehlt) wird weitergereicht."""
    payload = nutzlast(
        "Nestwerk Test",
        "Benachrichtigungen funktionieren auf diesem Gerät.",
        _eigene_origin_url(reverse("benachrichtigung:push_geraet")),
        badge=selectors.ungelesen(benutzer),
    )
    gesendet = fehler = 0
    for abo in aktive_abos(benutzer):
        try:
            abo_senden(abo, payload, ttl=300, urgency="high", topic_wert=topic("test"))
        except Exception as exc:
            logger.warning("Test-Push an Abo %s fehlgeschlagen: %s", abo.pk, type(exc).__name__)
            fehler += 1
        else:
            gesendet += 1
    return gesendet, fehler
