"""Lesende Abfragen von aufgaben (öffentliche Schnittstelle für Dashboards, AP12/AP14/AP17)."""

from datetime import date

from .models import LAUFENDE_STATUS, AufgabenInstanz, InstanzStatus, Status


def laufende_instanzen():
    """Nicht abgeschlossene Instanzen aktiver Aufgaben (offen bis Rückfrage)."""
    return AufgabenInstanz.objects.filter(
        status__in=LAUFENDE_STATUS, aufgabe__status=Status.AKTIV
    ).select_related("aufgabe")


def instanzen_im_zeitraum(von: date, bis: date):
    """Instanzen mit wirksamem Datum in ``[von, bis]`` (Wochenplan, AP14)."""
    return AufgabenInstanz.objects.filter(faellig_am__range=(von, bis)).select_related("aufgabe")


def nicht_uebernommene(seit=None):
    """Verfallene Instanzen für die Eltern-Ansicht ("nicht übernommen")."""
    qs = AufgabenInstanz.objects.filter(status=InstanzStatus.NICHT_UEBERNOMMEN)
    if seit is not None:
        qs = qs.filter(abgeschlossen_am__gte=seit)
    return qs.order_by("-abgeschlossen_am")
