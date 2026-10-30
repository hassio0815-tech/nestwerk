"""Schnell-Knöpfe: Aufgaben mit Wiederholungsart "bei Bedarf" (SPEC Schnell-Knöpfe).

Eine solche Aufgabe schläft, bis jemand ihren Knopf drückt. Der Druck legt genau **eine** offene
Instanz an; solange sie läuft (offen bis Rückfrage, Nachbessern), bewirkt jeder weitere Druck
nichts ("läuft schon"). Zwei Modi:

- "Ich mach's" (``kind`` gesetzt): die Instanz wird für dieses Kind reserviert (wie bei einem
  Kind, das die Aufgabe wählt: gleiche Regeln, Frist, Limit, Ereignis an die Eltern).
- "Nur melden" (``kind=None``): die Instanz bleibt offen für alle Kinder; jedes erlaubte aktive
  Kind bekommt eine Mitteilung ("{Aufgabe}: wer macht's?").

Race-sicher: Transaktion mit Sperre auf der Aufgabe plus das Teil-Unique "höchstens eine laufende
ungebundene Instanz je Aufgabe" (``aufgaben_instanz_ungebunden_ein_laufend``).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import audit, zeit
from apps.konten import selectors as konten_selectors

from . import ablauf, events, wiederholung
from .models import (
    LAUFENDE_STATUS,
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    SchnellknopfWer,
    Status,
)
from .zustand import AblaufFehler

# Läuft noch: alles bis zum Endzustand (inkl. "zum Nachbessern")
OFFEN_STATUS = (*LAUFENDE_STATUS, InstanzStatus.NACHBESSERN)


def laufende_instanz(aufgabe) -> AufgabenInstanz | None:
    return (
        AufgabenInstanz.objects.filter(aufgabe=aufgabe, status__in=OFFEN_STATUS)
        .select_related("kind")
        .order_by("-id")
        .first()
    )


def darf_druecken(aufgabe, benutzer) -> bool:
    """``benutzer=None`` = Flur-Tablet (nur Kinder-Knöpfe)."""
    if aufgabe.schnellknopf_wer == SchnellknopfWer.ELTERN:
        return getattr(benutzer, "rolle", None) == "eltern"
    return True


def erlaubte_kinder(aufgabe):
    """Aktive Kinder, die die Aufgabe machen dürfen (``zugewiesen_an`` leer = alle)."""
    kinder = konten_selectors.aktive_kinder()
    if aufgabe.zugewiesen_an_id:
        kinder = kinder.filter(pk=aufgabe.zugewiesen_an_id)
    return kinder


def _pruefen(aufgabe, von, kind):
    if not aufgabe.schnellknopf or aufgabe.status != Status.AKTIV:
        raise AblaufFehler(_("Dieser Knopf ist gerade nicht aktiv."))
    if not darf_druecken(aufgabe, von):
        raise ablauf.NichtErlaubt(_("Diesen Knopf dürfen nur Eltern drücken."))
    if kind is None:
        return
    if getattr(kind, "rolle", None) != "kind" or not kind.aktiv:
        raise ablauf.NichtErlaubt(_("Nur Kinder können Aufgaben übernehmen."))
    if getattr(von, "rolle", None) == "kind" and von.pk != kind.pk:
        raise ablauf.NichtErlaubt(_("Du kannst nur für dich selbst übernehmen."))
    if aufgabe.zugewiesen_an_id and aufgabe.zugewiesen_an_id != kind.pk:
        raise ablauf.NichtErlaubt(_("Diese Aufgabe ist für ein anderes Kind."))


def _anlegen(aufgabe, jetzt) -> AufgabenInstanz | None:
    heute = zeit.heute(jetzt)
    try:
        with transaction.atomic():
            return AufgabenInstanz.objects.create(
                aufgabe=aufgabe,
                faellig_am=heute,
                fenster_start=zeit.tag_beginn(heute),
                titel_snapshot=aufgabe.titel,
                punkte_snapshot=aufgabe.punkte,
                freigabeart_snapshot=aufgabe.freigabeart,
            )
    except IntegrityError:
        return None


@transaction.atomic
def druecken(aufgabe, *, von=None, kind=None, jetzt=None) -> tuple[AufgabenInstanz, bool]:
    """Knopf drücken. Rückgabe ``(instanz, neu)``; ``neu`` ist ``False``, wenn schon eine läuft.

    ``von``: der drückende Benutzer (``None`` = Flur-Tablet, dort ohne Anmeldung).
    ``kind``: Kind für "Ich mach's"; ``None`` = "Nur melden".
    """
    jetzt = jetzt or zeit.jetzt()
    aufgabe = Aufgabe.objects.select_for_update().get(pk=aufgabe.pk)
    _pruefen(aufgabe, von, kind)
    vorhandene = laufende_instanz(aufgabe)
    if vorhandene is not None:
        return vorhandene, False
    instanz = _anlegen(aufgabe, jetzt)
    if instanz is None:  # parallel von jemand anderem angelegt
        return laufende_instanz(aufgabe), False

    if kind is not None:
        instanz = ablauf.interesse_zeigen(instanz, kind, jetzt=jetzt)
    else:
        daten = {
            "instanz_id": instanz.pk,
            "aufgabe_id": aufgabe.pk,
            "aufgabe": instanz.titel_snapshot,
            "punkte": instanz.punkte_snapshot,
        }
        for empfaenger in erlaubte_kinder(aufgabe):
            if von is not None and empfaenger.pk == von.pk:
                continue  # wer drückt, weiß es schon
            ereignisse.veroeffentlichen(
                events.SCHNELLKNOPF,
                kind=empfaenger,
                akteur=von,
                daten=daten,
                schluessel=f"{events.SCHNELLKNOPF}:{instanz.pk}:{empfaenger.pk}",
            )
    audit.protokollieren(
        "aufgabe.schnellknopf",
        akteur=von,
        objekt=instanz,
        kind=kind,
        details={"titel": instanz.titel_snapshot, "modus": "ich_machs" if kind else "melden"},
    )
    return instanz, True


def knoepfe(benutzer=None, *, nur_kinder_knoepfe=False):
    """Aktive Schnell-Knöpfe für Kacheln, je mit ``laeuft`` (laufende Instanz oder ``None``).

    ``benutzer``: Kind -> nur Knöpfe "für alle" und für es freigegebene Aufgaben.
    ``nur_kinder_knoepfe``: Flur-Tablet (nur Knöpfe "für alle").
    """
    qs = Aufgabe.objects.filter(
        status=Status.AKTIV, wiederholungsart=wiederholung.BEI_BEDARF
    ).select_related("kategorie")
    if nur_kinder_knoepfe or getattr(benutzer, "rolle", None) == "kind":
        qs = qs.filter(schnellknopf_wer=SchnellknopfWer.ALLE)
    if getattr(benutzer, "rolle", None) == "kind":
        qs = qs.filter(Q(zugewiesen_an__isnull=True) | Q(zugewiesen_an=benutzer))
    aufgaben = list(qs.order_by("titel", "id"))
    laufende = {}
    for instanz in AufgabenInstanz.objects.filter(
        aufgabe__in=aufgaben, status__in=OFFEN_STATUS
    ).select_related("kind"):
        laufende[instanz.aufgabe_id] = instanz
    for aufgabe in aufgaben:
        aufgabe.laeuft = laufende.get(aufgabe.pk)
    return aufgaben
