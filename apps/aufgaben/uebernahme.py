"""Aufgabe aus der Wochenvorschau übernehmen (Anmeldeseite -> Anmeldung -> Wahl).

Keine eigenen Regeln: gesucht wird die **bestehende** Instanz zu ``(Aufgabe, Plan-Tag)``; gewählt
wird über ``ablauf.interesse_zeigen`` (Limits, Reservierung, Mitbewerben, Zuweisung, Fenster).
Außerhalb des Instanz-Horizonts gibt es keine Instanz und es entsteht auch keine.
"""

from dataclasses import dataclass
from datetime import date

from django.utils.translation import gettext as _

from . import ablauf
from .models import AufgabenInstanz, InstanzStatus
from .zustand import AblaufFehler


@dataclass(frozen=True)
class Ergebnis:
    """``art``: ``erfolg`` | ``info`` | ``fehler`` (wie die Toast-Arten der Oberfläche)."""

    art: str
    text: str


def uebernehmen(kind, aufgabe_id: int, datum: date, *, jetzt=None) -> Ergebnis:
    instanz = (
        AufgabenInstanz.objects.filter(aufgabe_id=aufgabe_id, plan_datum=datum)
        .select_related("aufgabe")
        .first()
    )
    if instanz is None:
        return Ergebnis(
            "fehler",
            _("Diese Aufgabe kann noch nicht übernommen werden. Schau später noch einmal vorbei!"),
        )
    titel = instanz.titel_snapshot or instanz.aufgabe.titel
    try:
        instanz = ablauf.interesse_zeigen(instanz, kind, jetzt=jetzt)
    except AblaufFehler as fehler:
        if instanz.kind_id == getattr(kind, "pk", None) and instanz.status != InstanzStatus.OFFEN:
            return Ergebnis("info", _("„%(titel)s“ hast du schon!") % {"titel": titel})
        return Ergebnis("fehler", str(fehler))
    if instanz.status == InstanzStatus.KONFLIKT:
        return Ergebnis(
            "info",
            _("„%(titel)s“ wollen mehrere Kinder. Mama oder Papa entscheiden.") % {"titel": titel},
        )
    return Ergebnis("erfolg", _("„%(titel)s“ gehört jetzt dir!") % {"titel": titel})
