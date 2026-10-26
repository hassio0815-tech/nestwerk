"""Lesende Abfragen von konten (für Anmeldeseiten und andere Apps)."""

from apps.kern import zeit

from . import sperre
from .models import Benutzer, ElternProfil, ElternZugang, Geraet, KindProfil, Rolle


def aktive_kinder():
    return Benutzer.objects.filter(rolle=Rolle.KIND, aktiv=True).select_related("kindprofil")


def aktive_eltern():
    return Benutzer.objects.filter(rolle=Rolle.ELTERN, aktiv=True)


def kind_gesperrt_bis(kind):
    """Sperrende der PIN-Eingabe oder ``None`` (z. B. für Eltern-Dashboard und Kachel)."""
    # frisch aus der DB, nicht über ein evtl. veraltetes ``kind.kindprofil``
    profil = KindProfil.objects.get(benutzer=kind)
    return sperre.kind_gesperrt_bis(profil, zeit.jetzt())


def gesperrte_kinder():
    jetzt = zeit.jetzt()
    return [k for k in aktive_kinder() if sperre.kind_gesperrt_bis(k.kindprofil, jetzt)]


def geraete(nur_aktive=True):
    qs = Geraet.objects.select_related("registriert_von")
    return qs.filter(aktiv=True) if nur_aktive else qs


def eltern_email(benutzer):
    """E-Mail-Adresse eines Elternteils oder ``""``."""
    return ElternProfil.objects.filter(pk=benutzer.pk).values_list("email", flat=True).first() or ""


def eltern_passwort_gesetzt():
    """Gibt es ein Eltern-Passwort? (Der Hash selbst verlässt konten nie.)"""
    return ElternZugang.objects.filter(pk=1).exists()
