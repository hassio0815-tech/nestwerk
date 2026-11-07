"""Doppel-Schutz beim Anlegen: gleicher Titel, gleiche Wiederholung, gleiche Zuweisung.

Verglichen wird mit **aktiven** Aufgaben; der Titel normalisiert (Rand-Leerzeichen, Groß-/
Kleinschreibung egal). Eltern können mit dem Häkchen "trotzdem anlegen" bestätigen."""

from django.utils.translation import gettext as _

from apps.kern.sprache import uebersetzt
from apps.konten import selectors as konten_selectors

from .models import Aufgabe, Status


def _normal(titel) -> str:
    return (titel or "").strip().casefold()


def finden(titel, wiederholungsart, zugewiesen_an, *, je_kind=False) -> Aufgabe | None:
    """Eine aktive Aufgabe, die genauso aussieht, oder ``None``.

    ``je_kind``: die neue Aufgabe entsteht für jedes aktive Kind; ein Treffer bei einem davon
    (oder bei einer Aufgabe "für alle Kinder") zählt als Doppel."""
    gesucht = _normal(titel)
    if not gesucht:
        return None
    kandidaten = Aufgabe.objects.filter(status=Status.AKTIV, wiederholungsart=wiederholungsart)
    if je_kind:
        kinder = list(konten_selectors.aktive_kinder().values_list("pk", flat=True))
        kandidaten = kandidaten.filter(zugewiesen_an__in=kinder)
    else:
        kandidaten = kandidaten.filter(zugewiesen_an=getattr(zugewiesen_an, "pk", zugewiesen_an))
    for aufgabe in kandidaten.order_by("id"):
        if _normal(aufgabe.titel) == gesucht:
            return aufgabe
    return None


def meldung(aufgabe) -> str:
    return _(
        "Die Aufgabe „%(titel)s“ gibt es schon (gleiche Wiederholung und gleiche Zuweisung). "
        "Soll sie trotzdem noch einmal angelegt werden? Dann setze unten das Häkchen."
    ) % {"titel": uebersetzt(aufgabe.titel)}
