"""Lesen für die Lernmappe (Material). Alles nach Kind gefiltert: Geschwister sehen nie Material
der anderen, Fremde bekommen ``None`` (die Seite antwortet mit 404)."""

from .models import Frage, Material, MaterialStatus

# Was das Kind sieht (Kindersprache, siehe Vorlagen)
KIND_PHASE = {
    MaterialStatus.WARTET_KI: "wartet",
    MaterialStatus.WARTET: "wartet",
    MaterialStatus.LIEST: "liest",
    MaterialStatus.FRAGEN: "liest",
    MaterialStatus.RUECKFRAGE: "eltern",
    MaterialStatus.WARTET_ELTERN: "eltern",
    MaterialStatus.BEREIT: "bereit",
    MaterialStatus.FEHLER: "fehler",
}


def materialien(kind):
    return Material.objects.filter(kind=kind).select_related("fach")


def material_von(kind, pk):
    """Material des Kindes oder ``None``."""
    return materialien(kind).filter(pk=pk).first()


def material(pk):
    """Für Eltern: jedes Material."""
    return Material.objects.select_related("kind", "fach").filter(pk=pk).first()


def alle_materialien():
    return Material.objects.select_related("kind", "fach")


def warten_auf_eltern():
    """Material, bei dem die Eltern etwas tun müssen (Freigabe, Fach, Fehler)."""
    return alle_materialien().filter(
        status__in=(MaterialStatus.WARTET_ELTERN, MaterialStatus.RUECKFRAGE, MaterialStatus.FEHLER)
    )


def fragen_von(material_):
    return Frage.objects.filter(material=material_).order_by("id")
