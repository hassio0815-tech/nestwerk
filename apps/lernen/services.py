"""Schreiben für lernen (Etappe 1: Fundament). Punkte und Aktivität folgen mit den Sitzungen."""

from apps.kern.einstellungen import wert

from .models import Frage, Freigabe, Leistungsstufe, Lernmappe, Quelle
from .speicher import Speicher


def lernmappe_sicherstellen(kind, speicher=None):
    """Legt die Lernmappe (1:1 je Kind) und ihre Ordner an. Idempotent."""
    mappe, _neu = Lernmappe.objects.get_or_create(kind=kind)
    (speicher or Speicher()).ordner_anlegen(kind.pk)
    return mappe


def speicher_limit_bytes():
    return wert("lernen.speicher_limit_mb") * 1024 * 1024


def frage_anlegen(thema, typ, frage, antwort, *, quelle, kind=None):
    """Neue Frage von Eltern oder KI. Der Status folgt der Einstellung
    ``lernen.freigabe_durch_eltern``; Eltern-Fragen sind sofort freigegeben."""
    if quelle == Quelle.SYSTEM:
        raise ValueError("Startdaten entstehen nur per Datenmigration.")
    offen = quelle == Quelle.KI and wert("lernen.freigabe_durch_eltern")
    return Frage.objects.create(
        thema=thema,
        typ=typ,
        frage=frage,
        antwort=antwort,
        quelle=quelle,
        kind=kind,
        freigabe=Freigabe.OFFEN if offen else Freigabe.FREIGEGEBEN,
    )


def leistungsstufe_setzen(kind, fach, stufe="", klassenstufe=None):
    obj, _neu = Leistungsstufe.objects.update_or_create(
        kind=kind, fach=fach, defaults={"stufe": stufe, "klassenstufe": klassenstufe}
    )
    return obj
