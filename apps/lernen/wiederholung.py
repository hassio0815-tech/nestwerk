"""Abstandswiederholung in Boxen und Auswahl der nächsten Frage (SPEC 21.2, Lernen lernen).

- Jede Box hat einen Abstand in Tagen (Einstellung ``lernen.box_abstaende_tage``, z. B. 1, 3, 7,
  14). Richtig: eine Box weiter. Noch nicht richtig: zurück in die erste Box.
- Ein Eintrag ist ein Paar aus Frage und Richtung. Vokabeln gibt es in beide Richtungen, Fragen
  nur vorwärts.
- Gemischte Themen: Die Auswahl vermeidet dasselbe Thema direkt hintereinander.
"""

import re
from dataclasses import dataclass
from datetime import timedelta

from apps.kern.einstellungen import wert

from .mathe.hilfe import aufgabe_aus_frage
from .models import Frage, FrageTyp, Intensitaet, Lernstand, Richtung, Vorhaben
from .pruefung import alternativen, anzeige_antwort, pruefen, pruefen_mathe
from .selectors import nutzbare_fragen


@dataclass(frozen=True)
class Aufgabe:
    """Eine gestellte Frage: Text, erwartete Antwort(en) und Richtung."""

    frage: Frage
    richtung: str
    text: str  # was das Kind sieht
    erwartet: str  # alle akzeptierten Antworten, wie gespeichert

    @property
    def generiert(self):
        return self.frage.generiert

    @property
    def loesung(self):
        """Die Lösung als Anzeige (erste Schreibweise ohne Klammern; bei erzeugten
        Mathe-Aufgaben die berechnete Lösung, ``3/4`` bleibt ein Bruch)."""
        if self.generiert:
            return self.frage.antwort
        return anzeige_antwort(self.erwartet)

    @property
    def eingabemodus(self):
        """Tastatur auf dem Handy: reine, nicht negative Zahl als Ziffernblock, sonst Text
        (Brüche, Minus, Gleichungen, Einheiten und Rest brauchen Buchstaben und Zeichen)."""
        if self.generiert and re.fullmatch(r"\d+([.,]\d+)?", self.frage.antwort.strip()):
            return "decimal"
        return "text"

    @property
    def mehrere(self):
        return not self.generiert and len(alternativen(self.erwartet)) > 1

    def pruefen(self, eingabe):
        """Prüft die Eingabe: Vokabel und Frage wie bisher, Mathe gegen die berechnete Lösung."""
        if self.generiert:
            return pruefen_mathe(
                eingabe, self.frage.gen_daten["loesung"], aufgabe_aus_frage(self.frage)
            )
        return pruefen(eingabe, self.erwartet)


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


# Ab dieser Hilfestufe rückt eine richtige Antwort die Karte nicht vor (W-1): Wer das Gerüst
# oder die Lösung gebraucht hat, kann es noch nicht. Gilt nur für neue Antworten.
HILFE_OHNE_FORTSCHRITT_AB = 3


def stand_buchen(kind, frage, richtung, richtig, heute, jetzt, *, hilfestufe=0, karte=None):
    """Schreibt das Ergebnis einer Antwort in den Lernstand (legt ihn bei Bedarf an).
    Richtig mit viel Hilfe bleibt in der Box und kommt nach deren Abstand wieder."""
    stand, _neu = Lernstand.objects.get_or_create(
        kind=kind, frage=frage, richtung=richtung, defaults={"faellig_am": heute}
    )
    mit_hilfe = richtig and hilfestufe >= HILFE_OHNE_FORTSCHRITT_AB
    if not mit_hilfe:
        stand.box = naechste_box(stand.box, richtig)
    stand.faellig_am = faellig_nach(stand.box, heute)
    stand.versuche += 1
    stand.richtige += 1 if richtig and not mit_hilfe else 0
    stand.zuletzt = jetzt
    if karte is not None:
        stand.karte = karte
    stand.save()
    return stand


def _kandidaten(kind, fach, themen, thema, heute, nur_fragen=None):
    """Alle Paare (Frage, Richtung) der Auswahl mit ihrem Stand, getrennt in neu und fällig.
    Neue Paare kommen nur aus dem gewählten Thema (oder aus dem ganzen Fach), fällige Wiederholungen
    aus dem ganzen Fach, damit die Themen gemischt werden. Mit ``nur_fragen`` (Prüfungsportion)
    zählen nur diese Fragen, gleich aus welchem Fach."""
    fragen = {}
    for t in themen:
        if thema is not None and t.pk != thema.pk:
            continue
        for f in nutzbare_fragen(t, kind, mit_generierten=nur_fragen is not None):
            if nur_fragen is None or f.pk in nur_fragen:
                fragen[f.pk] = f
    staende_qs = Lernstand.objects.filter(kind=kind)
    if nur_fragen is None:
        # erzeugte Mathe-Aufgaben wiederholt mathe_aufgaben als gleichartige neue Aufgabe
        staende_qs = staende_qs.filter(frage__thema__fach=fach, frage__generiert=False)
    else:
        staende_qs = staende_qs.filter(frage_id__in=nur_fragen)
    staende = {(s.frage_id, s.richtung): s for s in staende_qs.select_related("frage__thema")}
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
    nur_fragen=None,
):
    """Wählt das nächste Paar (Frage, Richtung) oder ``None``, wenn nichts mehr dran ist.

    ``themen``: alle Themen in Reichweite des Kindes, ``thema``: das gewählte (``None`` = gemischt).
    ``ausgeschlossen``: Paare, die in dieser Sitzung schon dran waren. Die Reihenfolge der Pools
    folgt dem Vorhaben; innerhalb eines Pools bevorzugt die Intensität eine Richtung
    (Aufwärmen: Fremdsprache zu Deutsch, Herausforderung: Deutsch zu Fremdsprache).

    ``nur_fragen`` (Menge von Frage-IDs, Prüfungsportion): nur diese Fragen; ist nichts neu oder
    fällig, kommen sie trotzdem dran (die Portion soll sich üben lassen).
    """
    neu, faellig, stolper = _kandidaten(kind, fach, themen, thema, heute, nur_fragen)
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
    if nur_fragen is not None:
        return _beliebige(kind, themen, nur_fragen, ausgeschlossen, letztes_thema, zufall)
    return None


def _beliebige(kind, themen, nur_fragen, ausgeschlossen, letztes_thema, zufall):
    """Prüfungsportion ohne Neues oder Fälliges: irgendeine noch nicht gestellte Frage daraus."""
    paare = [
        (f, r)
        for t in themen
        for f in nutzbare_fragen(t, kind, mit_generierten=True)
        if f.pk in nur_fragen
        for r in richtungen(f)
        if (f.pk, r) not in ausgeschlossen
    ]
    if not paare:
        return None
    zufall.shuffle(paare)
    return next((p for p in paare if p[0].thema_id != letztes_thema), paare[0])
