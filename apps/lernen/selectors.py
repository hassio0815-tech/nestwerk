"""Lesen für lernen (Etappe 1). Geschwister sehen die Fragen und die Mappe nie."""

from django.db.models import Q

from .models import Fach, Frage, Freigabe, Leistungsstufe, Thema


def faecher(nur_aktive=True):
    return Fach.objects.filter(aktiv=True) if nur_aktive else Fach.objects.all()


def themen(fach, klassenstufe=None):
    """Themen eines Fachs; mit ``klassenstufe`` auch die stufenlosen."""
    qs = Thema.objects.filter(fach=fach)
    if klassenstufe is not None:
        qs = qs.filter(Q(klassenstufe=klassenstufe) | Q(klassenstufe__isnull=True))
    return qs


def nutzbare_fragen(thema, kind):
    """Freigegebene Fragen: Startdaten und die eigenen des Kindes (nie die eines Geschwisters)."""
    return Frage.objects.filter(thema=thema, freigabe=Freigabe.FREIGEGEBEN).filter(
        Q(kind__isnull=True) | Q(kind=kind)
    )


def offene_fragen(kind=None):
    """Fragen, die auf die Freigabe durch die Eltern warten."""
    qs = Frage.objects.filter(freigabe=Freigabe.OFFEN)
    return qs.filter(kind=kind) if kind is not None else qs


def leistungsstufe(kind, fach):
    return Leistungsstufe.objects.filter(kind=kind, fach=fach).first()
