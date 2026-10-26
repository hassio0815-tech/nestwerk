"""Router: Ereignis -> Empfänger -> Benachrichtigung (Liste) -> Zustellung je Kanal.

Läuft als asynchroner Ereignis-Handler im Worker (``benachrichtigung.router``, für alle Typen)
in einer Transaktion mit dem Statuswechsel der Verarbeitung. Kein Netzwerk-I/O: Der Versand
übernimmt ``versand.zustellungen_senden``.

Regeln (ARCHITECTURE 5.3, 13.2 K7/K13):
- Die Benachrichtigung entsteht immer (Dashboard-Liste), unabhängig von Kanal und Ruhezeit.
- Je Empfänger und Kanal entsteht genau eine Zustellung (Unique-Constraints + ``get_or_create``).
- Präferenz aus: ``unterdrueckt_praeferenz``. Profil "Mail nur bei Entscheidungen": E-Mail für
  Nicht-Entscheidungen ebenfalls ``unterdrueckt_praeferenz``.
- Sonst Ruhezeit des Elternteils: Push stumm, E-Mail nur wenn die Ruhezeit es verlangt
  (``unterdrueckt_ruhezeit``); Pop-ups nie.
- Interne Typen und inaktive Typen erzeugen nichts. Kinder erhalten nur Kanäle mit Rolle "kind".
"""

import logging

from apps.ereignisse import selectors as ereignis_selectors
from apps.ereignisse.models import Zielgruppe
from apps.kern import zeit
from apps.konten import selectors as konten_selectors
from apps.konten.models import Rolle

from . import registry, ruhezeit, selectors, texte
from .models import (
    Benachrichtigung,
    BenachrichtigungsProfil,
    Kanal,
    Praeferenz,
    Ruhezeit,
    ZustellStatus,
    Zustellung,
)

logger = logging.getLogger("nestwerk.benachrichtigung")

ROUTER_NAME = "benachrichtigung.router"
EMAIL = "email"


def kanaele_synchronisieren(**_signal_kwargs):
    """Legt fehlende ``Kanal``-Zeilen für registrierte Kanäle an (``aktiv``, Name und Konfig
    bleiben editierbar). Gibt die Zahl neuer Zeilen zurück."""
    vorhanden = set(Kanal.objects.values_list("slug", flat=True))
    neu = [
        Kanal(slug=k.slug, bezeichnung=k.bezeichnung)
        for k in registry.kanaele()
        if k.slug not in vorhanden
    ]
    Kanal.objects.bulk_create(neu, ignore_conflicts=True)
    return len(neu)


def empfaenger_fuer(typ, ereignis):
    """Empfänger aus Zielgruppe des Typs: Eltern (alle aktiven) und/oder das betroffene Kind."""
    ergebnis = []
    if typ.zielgruppe in (Zielgruppe.ELTERN, Zielgruppe.BEIDE):
        ergebnis.extend(konten_selectors.aktive_eltern())
    if typ.zielgruppe in (Zielgruppe.KIND, Zielgruppe.BEIDE):
        kind = ereignis.kind
        if kind is None:
            logger.warning(
                "Ereignis %s (%s) ohne Kind, Kind-Empfang entfällt", ereignis.pk, typ.slug
            )
        elif kind.aktiv:
            ergebnis.append(kind)
    return ergebnis


def router(ereignis):
    """Ereignis-Handler. Idempotent: ein zweiter Lauf legt nichts Neues an."""
    typ = ereignis_selectors.ereignistyp(ereignis.typ_id)
    if not typ.aktiv or typ.zielgruppe == Zielgruppe.INTERN:
        return 0
    kanaele_synchronisieren()
    jetzt = zeit.jetzt()
    titel, text = texte.rendern(ereignis, typ.bezeichnung)
    link = texte.link_fuer(ereignis, typ.deep_link_muster)
    abgeschaltet = set(Kanal.objects.filter(aktiv=False).values_list("slug", flat=True))
    entscheidung = selectors.ist_entscheidung(typ)
    anzahl = 0
    for empfaenger in empfaenger_fuer(typ, ereignis):
        eintrag, _ = Benachrichtigung.objects.get_or_create(
            empfaenger=empfaenger,
            ereignis=ereignis,
            defaults={"titel": titel, "text": text, "link": link, "erstellt_am": jetzt},
        )
        praeferenzen = {
            k: a
            for k, a in Praeferenz.objects.filter(benutzer=empfaenger, ereignistyp=typ).values_list(
                "kanal_id", "aktiv"
            )
        }
        ruhezeiten = (
            list(Ruhezeit.objects.filter(benutzer=empfaenger))
            if empfaenger.rolle == Rolle.ELTERN
            else []
        )
        nur_entscheidungen = BenachrichtigungsProfil.objects.filter(
            benutzer=empfaenger, mail_nur_entscheidungen=True
        ).exists()
        for kanal in registry.kanaele():
            if empfaenger.rolle not in kanal.rollen or kanal.slug in abgeschaltet:
                continue
            status = zustellstatus(
                kanal,
                typ,
                praeferenzen.get(kanal.slug),
                ruhezeiten,
                jetzt,
                mail_nur_entscheidungen=nur_entscheidungen,
                entscheidung=entscheidung,
            )
            for ziel in kanal.ziele(empfaenger):
                _, neu = Zustellung.objects.get_or_create(
                    benachrichtigung=eintrag,
                    kanal_id=kanal.slug,
                    push_abo=ziel,
                    defaults={
                        "status": status,
                        "naechster_versuch": jetzt if status == ZustellStatus.OFFEN else None,
                    },
                )
                anzahl += neu
    return anzahl


def zustellstatus(
    kanal,
    typ,
    explizit,
    ruhezeiten,
    jetzt,
    *,
    mail_nur_entscheidungen=False,
    entscheidung=False,
):
    """Anfangsstatus einer Zustellung. ``explizit`` = Wert der Praeferenz-Zeile oder ``None``
    (dann gilt der Standard des Ereignistyps)."""
    an = explizit if explizit is not None else kanal.slug in (typ.standard_kanaele or [])
    if not an:
        return ZustellStatus.UNTERDRUECKT_PRAEFERENZ
    if kanal.slug == EMAIL and mail_nur_entscheidungen and not entscheidung:
        return ZustellStatus.UNTERDRUECKT_PRAEFERENZ
    if ruhezeit.unterdrueckt(ruhezeiten, kanal.slug, jetzt):
        return ZustellStatus.UNTERDRUECKT_RUHEZEIT
    return ZustellStatus.OFFEN
