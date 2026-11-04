"""Lesen für den Tutor (SPEC 21.3, 21.4). Gespräche gehören genau einem Kind: ``gespraech`` und
``gespraeche`` filtern immer nach dem Kind (Geschwister sehen nie fremde Gespräche). Nur die
Eltern-Funktionen (``fuer_eltern``) lesen über Kinder hinweg."""

from collections import Counter
from enum import StrEnum

from django.db.models import Q

from apps.kern import zeit
from apps.kern.einstellungen import wert

from . import ki_selectors
from .models import (
    Frage,
    GespraechStatus,
    KiAufgabe,
    NachrichtRolle,
    TutorGespraech,
    TutorNachricht,
)
from .pruefung import normalisieren

STUFEN = (1, 2, 3, 4, 5)


class TutorStatus(StrEnum):
    AUS = "aus"  # Einstellung ``lernen.tutor_aktiv`` ist aus
    KEINE_KI = "keine_ki"  # Aufgabe ``tutor`` hat keinen aktiven Anbieter
    BEREIT = "bereit"


def status():
    if not wert("lernen.tutor_aktiv"):
        return TutorStatus.AUS
    if not ki_selectors.ki_verfuegbar(KiAufgabe.TUTOR):
        return TutorStatus.KEINE_KI
    return TutorStatus.BEREIT


def bereit():
    return status() is TutorStatus.BEREIT


def bewerten_bereit():
    return ki_selectors.ki_verfuegbar(KiAufgabe.BEWERTEN)


# --- Kind ---------------------------------------------------------------------------------------


def gespraeche(kind):
    return TutorGespraech.objects.filter(kind=kind).select_related("material", "thema__fach")


def offene_gespraeche(kind):
    return gespraeche(kind).filter(status=GespraechStatus.OFFEN)


def gespraech(kind, pk):
    """Gespräch des Kindes oder ``None`` (fremde Gespräche gibt es hier nicht)."""
    return gespraeche(kind).filter(pk=pk).first()


def nachrichten(gespraech_):
    return TutorNachricht.objects.filter(gespraech=gespraech_).order_by("id")


def letzte_nachrichten(gespraech_, anzahl):
    """Die letzten ``anzahl`` Nachrichten, ältestes zuerst."""
    neu = list(TutorNachricht.objects.filter(gespraech=gespraech_).order_by("-id")[:anzahl])
    return list(reversed(neu))


def kind_nachrichten_heute(kind, *, jetzt=None):
    """Wie viele Nachrichten hat das Kind heute (lokaler Tag) an den Tutor geschickt?"""
    anfang, ende = zeit.tag_intervall(zeit.heute(jetzt))
    return TutorNachricht.objects.filter(
        gespraech__kind=kind, rolle=NachrichtRolle.KIND, zeit__gte=anfang, zeit__lt=ende
    ).count()


def letzte_aufgabe(gespraech_):
    """Letzte Frage oder letzter Versuch des Kindes (Text) oder ``None``."""
    zeile = (
        TutorNachricht.objects.filter(gespraech=gespraech_, rolle=NachrichtRolle.KIND)
        .exclude(art="mehr_hilfe")
        .order_by("-id")
        .first()
    )
    return zeile.text if zeile else None


def letzte_frage(gespraech_):
    """Letzte freie Frage des Kindes (kein Versuch, keine Bitte um Hilfe) oder ``None``."""
    zeile = (
        TutorNachricht.objects.filter(gespraech=gespraech_, rolle=NachrichtRolle.KIND, art="frage")
        .order_by("-id")
        .first()
    )
    return zeile.text if zeile else None


def kind_texte(gespraech_):
    """Alle Texte, die das Kind in diesem Gespräch geschrieben hat."""
    return list(
        TutorNachricht.objects.filter(gespraech=gespraech_, rolle=NachrichtRolle.KIND)
        .exclude(art="mehr_hilfe")
        .order_by("id")
        .values_list("text", flat=True)
    )


def bekannte_antworten(gespraech_, texte=()):
    """Antworten, die der Tutor nicht verraten darf: Fragen des Materials oder Themas des Gesprächs
    sowie Fragen, deren Fragetext in ``texte`` (Nachrichten des Kindes) vorkommt. Nur für die
    Leak-Prüfung, nie im Kontext der KI."""
    kind = gespraech_.kind
    antworten = []
    if gespraech_.material_id:
        antworten += list(
            Frage.objects.filter(material=gespraech_.material, kind=kind).values_list(
                "antwort", flat=True
            )
        )
    if gespraech_.thema_id:
        antworten += list(
            # erzeugte Mathe-Aufgaben nicht: ihre kurzen Zahlen-Antworten wären Fehlalarme
            Frage.objects.filter(thema=gespraech_.thema, freigabe="freigegeben", generiert=False)
            .filter(Q(kind__isnull=True) | Q(kind=kind))
            .values_list("antwort", flat=True)
        )
    text_n = " " + normalisieren(" ".join(texte)) + " "
    if text_n.strip():
        sichtbar = Frage.objects.filter(freigabe="freigegeben").filter(
            Q(kind__isnull=True) | Q(kind=kind)
        )
        for frage, antwort in sichtbar.values_list("frage", "antwort"):
            form = normalisieren(frage)
            if len(form) >= 3 and f" {form} " in text_n:
                antworten.append(antwort)
    return list(dict.fromkeys(a for a in antworten if a))


# --- Eltern -------------------------------------------------------------------------------------


def fuer_eltern(pk):
    """Ein Gespräch beliebiger Kinder (nur lesen, Eltern)."""
    return (
        TutorGespraech.objects.select_related("kind", "material", "thema__fach")
        .filter(pk=pk)
        .first()
    )


def protokoll(kind):
    """Gespräche eines Kindes für die Eltern, neueste zuerst."""
    return gespraeche(kind)


def hilfestufen_zaehler(kind):
    """``{stufe: Anzahl}`` der Antworten des Tutors je Hilfestufe (1 bis 5) für ein Kind."""
    zeilen = TutorNachricht.objects.filter(
        gespraech__kind=kind, rolle=NachrichtRolle.TUTOR, art="antwort"
    ).values_list("hilfestufe", flat=True)
    zaehler = Counter(zeilen)
    return {stufe: zaehler.get(stufe, 0) for stufe in STUFEN}
