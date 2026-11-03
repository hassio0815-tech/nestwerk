"""Lesen für die KI-Anbindung (SPEC 21.6). Alles familienweit, nichts pro Kind."""

from enum import StrEnum

from .models import KiAnbieter, KiAufgabe, KiAuftrag, KiAuftragStatus, KiZuordnung


class KiStatus(StrEnum):
    AUS = "aus"  # keine Zuordnung
    NICHT_AKTIV = "nicht_aktiv"  # Anbieter zugeordnet, aber deaktiviert
    EINWILLIGUNG_FEHLT = "einwilligung_fehlt"  # Cloud ohne Einwilligung
    BEREIT = "bereit"


def anbieter_liste():
    return KiAnbieter.objects.select_related("einwilligung_von").order_by("name")


def zuordnung_fuer(aufgabe):
    """Anbieter der Aufgabe oder ``None`` (= KI aus)."""
    zeile = KiZuordnung.objects.select_related("anbieter").filter(aufgabe=aufgabe).first()
    return zeile.anbieter if zeile else None


def zuordnungen():
    """``{aufgabe: Anbieter oder None}`` für alle Aufgaben."""
    vorhanden = {z.aufgabe: z.anbieter for z in KiZuordnung.objects.select_related("anbieter")}
    return {wert: vorhanden.get(wert) for wert in KiAufgabe.values}


def status_von(anbieter):
    if anbieter is None:
        return KiStatus.AUS
    if not anbieter.aktiv:
        return KiStatus.NICHT_AKTIV
    if anbieter.ist_cloud and anbieter.einwilligung_am is None:
        return KiStatus.EINWILLIGUNG_FEHLT
    return KiStatus.BEREIT


def ki_status(aufgabe):
    return status_von(zuordnung_fuer(aufgabe))


def ki_verfuegbar(aufgabe):
    return ki_status(aufgabe) is KiStatus.BEREIT


def auftraege_offen():
    return KiAuftrag.objects.filter(
        status__in=[KiAuftragStatus.WARTEND, KiAuftragStatus.LAEUFT]
    ).count()
