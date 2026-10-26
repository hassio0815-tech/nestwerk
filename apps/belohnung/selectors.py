"""Lesende Schnittstelle von belohnung."""

from datetime import date

from django.db.models import Sum

from apps.kern import einstellungen, zeit
from apps.punkte import selectors as punkte

from .models import Belohnung, Einloeseantrag, Status, TaschengeldLimit

LIMIT_SCHLUESSEL = "belohnung.taschengeld_limit_cent"


def offene_reservierung(kind):
    """Reservierter Punktestand des Kindes: Summe seiner offenen Anträge (punkte-Registry)."""
    return (
        Einloeseantrag.objects.filter(kind=kind, status=Status.OFFEN).aggregate(
            s=Sum("preis_snapshot")
        )["s"]
        or 0
    )


def katalog(*, nur_aktive=True):
    qs = Belohnung.objects.select_related("kategorie")
    return qs.filter(aktiv=True) if nur_aktive else qs


def antraege_des_kindes(kind):
    return Einloeseantrag.objects.filter(kind=kind).select_related("belohnung")


def offene_antraege():
    return Einloeseantrag.objects.filter(status=Status.OFFEN).select_related("kind", "belohnung")


def standard_limit_cent():
    return einstellungen.wert(LIMIT_SCHLUESSEL)


def limit_cent(kind):
    """Monatslimit des Kindes in Cent (eigenes Limit, sonst Standard-Einstellung)."""
    eigenes = TaschengeldLimit.objects.filter(kind=kind).first()
    return eigenes.monatslimit_cent if eigenes else standard_limit_cent()


def monat_intervall(tag=None):
    """[Beginn, Ende) des Kalendermonats von ``tag`` (Standard heute) als UTC-Zeitpunkte."""
    tag = tag or zeit.heute()
    erster = tag.replace(day=1)
    naechster = date(erster.year + (erster.month == 12), erster.month % 12 + 1, 1)
    return zeit.tag_beginn(erster), zeit.tag_beginn(naechster)


def taschengeld_belegt_cent(kind, tag=None):
    """Im Kalendermonat bestätigt (Entscheidungsdatum) plus alle offenen Taschengeld-Anträge."""
    von, bis = monat_intervall(tag)
    alle = Einloeseantrag.objects.filter(kind=kind, geldwert_cent_snapshot__isnull=False)
    bestaetigt = alle.filter(
        status=Status.BESTAETIGT, entschieden_am__gte=von, entschieden_am__lt=bis
    )
    offen = alle.filter(status=Status.OFFEN)
    return _summe(bestaetigt) + _summe(offen)


def _summe(qs):
    return qs.aggregate(s=Sum("geldwert_cent_snapshot"))["s"] or 0


def taschengeld_frei_cent(kind, tag=None):
    return max(0, limit_cent(kind) - taschengeld_belegt_cent(kind, tag))


def verfuegbar(kind):
    return punkte.verfuegbar(kind)
