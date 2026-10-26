"""Wochenplan (AP14): Daten für die Wochenansicht und Verschieben mit Reihenfolge."""

from datetime import date

from django.db import transaction

from apps.kern import zeit

from . import instanzen
from .models import AufgabenInstanz, InstanzStatus

MAX_REIHENFOLGE = 100


def woche_aus_datum(text) -> zeit.IsoWoche:
    """ISO-Woche zum Datum ``JJJJ-MM-TT``; ungültig/leer = aktuelle Woche."""
    try:
        return zeit.IsoWoche.von(date.fromisoformat(text))
    except (TypeError, ValueError):
        return zeit.aktuelle_woche()


def verschiebbar(instanz) -> bool:
    return instanz.status in instanzen.VERSCHIEBBAR


def woche_daten(woche: zeit.IsoWoche, *, heute=None) -> dict:
    """Tage Mo-So mit ihren Instanzen sowie Instanzen ohne Termin (nur Info)."""
    from . import selectors

    heute = heute or zeit.heute()
    nach_tag = {tag: [] for tag in woche.tage()}
    for inst in selectors.instanzen_im_zeitraum(woche.montag, woche.sonntag).select_related(
        "kind", "aufgabe__kategorie"
    ):
        inst.beweglich = verschiebbar(inst)
        nach_tag[inst.faellig_am].append(inst)
    ohne_termin = AufgabenInstanz.objects.filter(
        faellig_am__isnull=True, status__in=instanzen.VERSCHIEBBAR
    ).select_related("kind", "aufgabe__kategorie")
    ohne_termin = list(ohne_termin)
    for inst in ohne_termin:
        inst.beweglich = True
    tage = [{"datum": t, "heute": t == heute, "instanzen": nach_tag[t]} for t in woche.tage()]
    return {
        "woche": woche,
        "tage": tage,
        "ohne_termin": list(ohne_termin),
        "vorherige": woche.vorherige().montag,
        "naechste": woche.naechste().montag,
        "heute_datum": heute,
    }


def reihenfolge_lesen(text) -> list[int]:
    """Kommagetrennte Instanz-IDs; ungültige Eingaben -> ValueError."""
    if not text:
        return []
    try:
        ids = [int(x) for x in str(text).split(",") if x.strip()]
    except ValueError as exc:
        raise ValueError("Ungültige Reihenfolge") from exc
    if len(ids) > MAX_REIHENFOLGE or len(set(ids)) != len(ids):
        raise ValueError("Ungültige Reihenfolge")
    return ids


@transaction.atomic
def verschieben(instanz_pk, datum: date, *, von, reihenfolge=()):
    """Verschiebt eine Instanz auf ``datum`` und ordnet den Tag nach ``reihenfolge`` (IDs).

    Das Verschieben selbst (Zustandsprüfung, Fenster, Audit) macht
    ``instanzen.instanz_verschieben``. Löst ``ValueError`` aus, wenn nicht erlaubt.
    """
    try:
        inst = AufgabenInstanz.objects.get(pk=instanz_pk)
    except AufgabenInstanz.DoesNotExist as exc:
        raise ValueError("Aufgabe nicht gefunden") from exc
    reihenfolge = list(reihenfolge)
    position = reihenfolge.index(inst.pk) if inst.pk in reihenfolge else None
    inst = instanzen.instanz_verschieben(inst, datum, von=von, sortierung=position)
    for index, pk in enumerate(reihenfolge):
        if pk == inst.pk:
            continue
        AufgabenInstanz.objects.filter(pk=pk, faellig_am=datum).exclude(
            status__in=(InstanzStatus.STORNIERT,)
        ).update(sortierung=index)
    return inst
