"""Abstandswiederholung in Boxen und Auswahl der nächsten Frage (SPEC 21.2, Lernen lernen).

- Jede Box hat einen Abstand in Tagen (Einstellung ``lernen.box_abstaende_tage``, z. B. 1, 3, 7,
  14). Richtig: eine Box weiter. Noch nicht richtig: zurück in die erste Box.
- Ein Eintrag ist ein Paar aus Frage und Richtung. Vokabeln gibt es in beide Richtungen, Fragen
  nur vorwärts.
- Gemischte Themen: Die Auswahl vermeidet dasselbe Thema direkt hintereinander.
"""

from dataclasses import dataclass
from datetime import timedelta

from apps.kern.einstellungen import wert

from .models import Frage, FrageTyp, Intensitaet, Lernstand, Richtung, Vorhaben
from .pruefung import alternativen, anzeige_antwort
from .selectors import nutzbare_fragen


@dataclass(frozen=True)
class Aufgabe:
    """Eine gestellte Frage: Text, erwartete Antwort(en) und Richtung."""

    frage: Frage
    richtung: str
    text: str  # was das Kind sieht
    erwartet: str  # alle akzeptierten Antworten, wie gespeichert

    @property
    def loesung(self):
        """Die Lösung als Anzeige (erste Schreibweise ohne Klammern)."""
        return anzeige_antwort(self.erwartet)

    @property
    def mehrere(self):
        return len(alternativen(self.erwartet)) > 1


def aufgabe_fuer(frage, richtung):
    """Frage und erwartete Antwort in der gewünschten Richtung."""
    if richtung == Richtung.EN_DE and frage.typ == FrageTyp.VOKABEL:
        return Aufgabe(frage, richtung, anzeige_antwort(frage.antwort), frage.frage)
    return Aufgabe(frage, Richtung.DE_EN, frage.frage, frage.antwort)


def richtungen(frage):
    return (Richtung.DE_EN, Richtung.EN_DE) if frage.typ == FrageTyp.VOKABEL else (Richtung.DE_EN,)


def abstaende():
    return list(wert("lernen.box_abstaende_tage"))


def naechste_box(box, richtig):
    """Richtig: eine Box weiter (höchstens die letzte). Sonst zurück in die erste."""
    return min(box + 1, len(abstaende()) - 1) if richtig else 0


def faellig_nach(box, heute):
    return heute + timedelta(days=abstaende()[min(box, len(abstaende()) - 1)])


def stand_buchen(kind, frage, richtung, richtig, heute, jetzt):
    """Schreibt das Ergebnis einer Antwort in den Lernstand (legt ihn bei Bedarf an)."""
    stand, _neu = Lernstand.objects.get_or_create(
        kind=kind, frage=frage, richtung=richtung, defaults={"faellig_am": heute}
    )
    stand.box = naechste_box(stand.box, richtig)
    stand.faellig_am = faellig_nach(stand.box, heute)
    stand.versuche += 1
    stand.richtige += 1 if richtig else 0
    stand.zuletzt = jetzt
    stand.save()
    return stand


def _kandidaten(kind, fach, themen, thema, heute):
    """Alle Paare (Frage, Richtung) der Auswahl mit ihrem Stand, getrennt in neu und fällig.
    Neue Paare kommen nur aus dem gewählten Thema (oder aus dem ganzen Fach), fällige Wiederholungen
    aus dem ganzen Fach, damit die Themen gemischt werden."""
    fragen = {}
    for t in themen:
        if thema is not None and t.pk != thema.pk:
            continue
        for f in nutzbare_fragen(t, kind):
            fragen[f.pk] = f
    staende = {
        (s.frage_id, s.richtung): s
        for s in Lernstand.objects.filter(kind=kind, frage__thema__fach=fach).select_related(
            "frage__thema"
        )
    }
    neu, faellig, stolper = [], [], []
    for f in fragen.values():
        for richtung in richtungen(f):
            if (f.pk, richtung) not in staende:
                neu.append((f, richtung))
    for (frage_id, richtung), s in staende.items():
        if s.faellig_am > heute:
            continue
        frage = fragen.get(frage_id) or s.frage
        if frage.kind_id not in (None, kind.pk) or frage.freigabe != "freigegeben":
            continue
        faellig.append((frage, richtung))
        if s.box == 0 and s.versuche > s.richtige:
            stolper.append((frage, richtung))
    return neu, faellig, stolper


def naechste(
    kind,
    fach,
    themen,
    *,
    thema,
    vorhaben,
    intensitaet,
    heute,
    ausgeschlossen,
    letztes_thema,
    zufall,
):
    """Wählt das nächste Paar (Frage, Richtung) oder ``None``, wenn nichts mehr dran ist.

    ``themen``: alle Themen in Reichweite des Kindes, ``thema``: das gewählte (``None`` = gemischt).
    ``ausgeschlossen``: Paare, die in dieser Sitzung schon dran waren. Die Reihenfolge der Pools
    folgt dem Vorhaben; innerhalb eines Pools bevorzugt die Intensität eine Richtung
    (Aufwärmen: Fremdsprache zu Deutsch, Herausforderung: Deutsch zu Fremdsprache).
    """
    neu, faellig, stolper = _kandidaten(kind, fach, themen, thema, heute)
    pools = {
        Vorhaben.NEU: (neu, faellig),
        Vorhaben.WIEDERHOLEN: (faellig, neu),
        Vorhaben.STOLPERSTELLEN: (stolper, faellig, neu),
    }.get(vorhaben, (faellig, neu))
    bevorzugt = {
        Intensitaet.AUFWAERMEN: Richtung.EN_DE,
        Intensitaet.HERAUSFORDERUNG: Richtung.DE_EN,
    }.get(intensitaet)
    for pool in pools:
        frei = [(f, r) for f, r in pool if (f.pk, r) not in ausgeschlossen]
        if not frei:
            continue
        # Vokabeln ohne Richtungswunsch zufällig, mit Wunsch zuerst die bevorzugte Richtung
        frei.sort(key=lambda p: (0 if p[1] == bevorzugt else 1, zufall.random()))
        for f, r in frei:
            if f.thema_id != letztes_thema:
                return f, r
        return frei[0]
    return None
