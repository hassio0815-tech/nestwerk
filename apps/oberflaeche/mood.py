"""Mood-Vorschläge mit Benachrichtigung: verbindet ``konten.services`` (Vorschläge,
Entscheidung) mit den Ereignissen (Eltern bei neuem Vorschlag, Kind bei Entscheidung)."""

from django.db import transaction

from apps.ereignisse import services as ereignisse
from apps.konten import services as konten

from . import events


def vorschlagen(kind, text):
    with transaction.atomic():
        vorschlag = konten.mood_vorschlagen(kind, text)
        ereignisse.veroeffentlichen(
            events.MOOD_VORGESCHLAGEN,
            kind=kind,
            akteur=kind,
            daten={"vorschlag": vorschlag.text, "vorschlag_id": vorschlag.pk},
            schluessel=f"{events.MOOD_VORGESCHLAGEN}:{vorschlag.pk}",
        )
    return vorschlag


def entscheiden(vorschlag, zulassen, *, von):
    typ = events.MOOD_ZUGELASSEN if zulassen else events.MOOD_ABGELEHNT
    with transaction.atomic():
        vorschlag = konten.mood_vorschlag_entscheiden(vorschlag, zulassen, von=von)
        ereignisse.veroeffentlichen(
            typ,
            kind=vorschlag.kind,
            akteur=von,
            daten={"vorschlag": vorschlag.text, "vorschlag_id": vorschlag.pk},
            schluessel=f"{typ}:{vorschlag.pk}",
        )
    return vorschlag
