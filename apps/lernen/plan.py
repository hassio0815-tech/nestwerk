"""Planer der Prüfungsvorbereitung (SPEC 21.7). Reine Funktionen, keine Datenbank.

Grundsätze (SPEC 21.2 "Schaffbare Ziele"):

- Der Plan geht rückwärts vom Termin aus und hat kleine Portionen. Pro Tag steht höchstens das
  persönliche Tagesziel des Kindes darin, nie mehr.
- Puffertage (Standard: ein Puffertag je fünf Lerntage) bleiben frei. Der letzte Lerntag vor der
  Prüfung bringt nur leichte Wiederholung.
- Wiederholung im Abstand der Boxen (Etappe 2). Je Portion gibt es eine Pflicht-Wiederholung,
  weitere nur, wenn Platz ist.
- **Realitätscheck:** Passt der Stoff nicht in die verfügbare Zeit, entsteht *kein* Plan.
  Stattdessen gibt es Vorschläge (früher anfangen, Stoff verkleinern, Ziel etwas erhöhen). Das
  System entscheidet das nie selbst.
"""

import math
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

ART_NEU = "neu"
ART_WDH = "wiederholung"
ART_LEICHT = "leicht"
ART_PUFFER = "puffer"

GRUND_OK = ""
GRUND_KEIN_STOFF = "kein_stoff"
GRUND_VORBEI = "termin_vorbei"
GRUND_ZU_VIEL = "zu_viel"

VORSCHLAG_FRUEHER = "frueher"
VORSCHLAG_KLEINER = "kleiner"
VORSCHLAG_ZIEL = "ziel"

FRUEHER_MAX_TAGE = 60  # so weit sucht der Vorschlag "früher anfangen"
LEICHT_FRAGEN_MAX = 40


@dataclass(frozen=True)
class Parameter:
    """Alle Stellschrauben des Planers (kommen aus den Einstellungen in der Datenbank)."""

    tagesziel: int  # Minuten pro Tag, die das Kind sich vorgenommen hat: nie mehr planen
    portion_minuten: int = 10
    sekunden_pro_frage: int = 45
    wdh_prozent: int = 40
    leicht_minuten: int = 10
    puffer_rhythmus: int = 5  # ein Puffertag je so vielen Lerntagen, 0 = keiner
    abstaende: tuple = (1, 3, 7, 14)
    wochentage: frozenset = frozenset(range(7))  # 0 = Montag
    max_laenge: int = 42  # so viele Tage vor dem Termin beginnt der Plan frühestens
    vorlauf: int = 14  # kürzer als das ist "knapp" (nur ein freundlicher Hinweis)
    ziel_zuschlag_max: int = 15  # so weit darf der Vorschlag das Tagesziel erhöhen


@dataclass(frozen=True)
class Teil:
    """Ein Stoffteil: eine Portion, die neu gelernt wird."""

    schluessel: str
    stoff: str
    fragen: tuple


@dataclass(frozen=True)
class WdhOffen:
    """Eine noch ausstehende Wiederholung aus einem früheren Plan (beim Neuplanen)."""

    stoff: str
    fragen: tuple
    minuten: int
    frueh_ab: date
    pflicht: bool = True


@dataclass(frozen=True)
class Eintrag:
    datum: date
    art: str
    stoff: str = ""
    fragen: tuple = ()
    minuten: int = 0
    pflicht: bool = False
    schluessel: str = ""

    @property
    def puffer(self):
        return self.art == ART_PUFFER


@dataclass(frozen=True)
class Vorschlag:
    """Was das Kind oder die Eltern ändern könnten. ``wert``: Tage, Fragen oder Minuten."""

    art: str
    wert: int


@dataclass(frozen=True)
class Plan:
    ok: bool
    grund: str = GRUND_OK
    eintraege: tuple = ()
    benoetigt: int = 0  # Minuten, die der Stoff braucht (neu + Pflicht-Wiederholung)
    verfuegbar: int = 0  # Minuten, die bis zum Termin zur Verfügung stehen
    lerntage: int = 0
    puffertage: int = 0
    puffer_genutzt: bool = False
    knapp: bool = False
    vorschlaege: tuple = field(default_factory=tuple)

    @property
    def fehlt(self):
        return max(0, self.benoetigt - self.verfuegbar)


# --- Bausteine ---------------------------------------------------------------------------------


def minuten_neu(anzahl_fragen, p):
    """Minuten für eine Portion mit ``anzahl_fragen`` Fragen (mindestens 1, höchstens ein Tag)."""
    return min(p.tagesziel, max(1, math.ceil(anzahl_fragen * p.sekunden_pro_frage / 60)))


def minuten_wdh(minuten, p):
    return max(1, math.ceil(minuten * p.wdh_prozent / 100))


def fragen_je_portion(p):
    """So viele Fragen passen in eine Portion (mindestens eine)."""
    grenze = min(p.portion_minuten, p.tagesziel)
    return max(1, int(grenze * 60 // max(1, p.sekunden_pro_frage)))


def teilen(stoffe, p):
    """Schneidet ``{stoff: (frage_id, ...)}`` in Portionen. Gibt eine Liste von ``Teil`` zurück."""
    je = fragen_je_portion(p)
    teile = []
    for stoff, fragen in stoffe.items():
        fragen = tuple(fragen)
        for nr, von in enumerate(range(0, len(fragen), je)):
            teile.append(Teil(f"{stoff}:{nr}", stoff, fragen[von : von + je]))
    return teile


def _tage(start, termin, blockiert, p, extra=0):
    """Mögliche Lerntage: ab ``start`` (höchstens ``max_laenge`` vor dem Termin) bis zum Tag vor
    dem Termin, ohne Pausentage und ohne ausgeschlossene Wochentage."""
    erster = max(start - timedelta(days=extra), termin - timedelta(days=p.max_laenge + extra))
    tage = []
    tag = erster
    while tag < termin:
        if tag not in blockiert and tag.weekday() in p.wochentage:
            tage.append(tag)
        tag += timedelta(days=1)
    return tage


def _puffer(lern, p, fest):
    if fest is not None:
        return frozenset(d for d in lern if d in fest)
    r = p.puffer_rhythmus
    if r <= 0:
        return frozenset()
    return frozenset(d for i, d in enumerate(lern) if (i + 1) % (r + 1) == 0)


def _pflicht_index(p):
    return min(1, len(p.abstaende) - 1)


def _belegen(tage, teile, wdh_offen, p, cap_neu):
    """Verteilt Portionen auf die Tage. Gibt die Einträge zurück oder ``None``, wenn etwas übrig
    bleibt (eine Portion oder eine Pflicht-Wiederholung)."""
    ziel = p.tagesziel
    eintraege = []
    # ausstehende Wiederholungen: (fällig, Eintrag; das Datum setzt erst ``platzieren``)
    ausstehend = [
        (w.frueh_ab, Eintrag(w.frueh_ab, ART_WDH, w.stoff, w.fragen, w.minuten, w.pflicht))
        for w in wdh_offen
    ]
    warteschlange = list(teile)
    letzter = tage[-1] if tage else None
    pf = _pflicht_index(p)
    for tag in tage:
        frei = ziel

        def platzieren(eintrag, tag=tag):
            eintraege.append(
                Eintrag(
                    tag,
                    eintrag.art,
                    eintrag.stoff,
                    eintrag.fragen,
                    eintrag.minuten,
                    eintrag.pflicht,
                    eintrag.schluessel,
                )
            )

        for faellig, e in sorted(
            (x for x in ausstehend if x[0] <= tag and x[1].pflicht), key=lambda x: x[0]
        ):
            if e.minuten <= frei:
                platzieren(e)
                frei -= e.minuten
                ausstehend.remove((faellig, e))
        neu_heute = 0
        while warteschlange:
            teil = warteschlange[0]
            m = minuten_neu(len(teil.fragen), p)
            if m > frei or (neu_heute and neu_heute + m > cap_neu):
                break
            warteschlange.pop(0)
            eintraege.append(
                Eintrag(tag, ART_NEU, teil.stoff, teil.fragen, m, True, teil.schluessel)
            )
            frei -= m
            neu_heute += m
            wdh_m = minuten_wdh(m, p)
            for k, abstand in enumerate(p.abstaende):
                faellig = tag + timedelta(days=abstand)
                if k == pf:
                    faellig = min(faellig, letzter)
                elif faellig > letzter:
                    continue
                ausstehend.append(
                    (
                        faellig,
                        Eintrag(
                            faellig,
                            ART_WDH,
                            teil.stoff,
                            teil.fragen,
                            wdh_m,
                            k == pf,
                            f"{teil.schluessel}:w{k}",
                        ),
                    )
                )
        for faellig, e in sorted(
            (x for x in ausstehend if x[0] <= tag and not x[1].pflicht), key=lambda x: x[0]
        ):
            if e.minuten <= frei:
                platzieren(e)
                frei -= e.minuten
                ausstehend.remove((faellig, e))
    if warteschlange or any(e.pflicht for _f, e in ausstehend):
        return None
    return eintraege


def _leicht(tag, stoffe, p):
    """Der letzte Lerntag: von jedem Stoff ein kleines Stück zum Auffrischen, zusammen höchstens
    ``leicht_minuten`` (und nie über dem Tagesziel)."""
    if tag is None or not stoffe:
        return []
    budget = min(p.tagesziel, p.leicht_minuten)
    je = max(1, budget // len(stoffe))
    eintraege = []
    benutzt = 0
    for stoff, fragen in stoffe.items():
        if not fragen or benutzt + je > budget:
            continue
        auswahl = tuple(fragen[:LEICHT_FRAGEN_MAX])
        eintraege.append(Eintrag(tag, ART_LEICHT, stoff, auswahl, je, False, f"{stoff}:leicht"))
        benutzt += je
    return eintraege


def _cap_start(teile, tage, p):
    gesamt = sum(minuten_neu(len(t.fragen), p) for t in teile)
    neu_tage = max(1, len(tage) - max(1, round(len(tage) / 3)))
    return max(1, math.ceil(gesamt / neu_tage))


def _verteilen(tage, teile, wdh_offen, p):
    """Sucht die gleichmäßigste Verteilung: erst mit dem größten Tagespensum prüfen, ob es überhaupt
    geht, dann von klein nach groß das kleinste Pensum, das reicht."""
    if not teile and not any(w.pflicht for w in wdh_offen):
        return _belegen(tage, [], wdh_offen, p, p.tagesziel) if tage else []
    if not tage:
        return None
    if _belegen(tage, teile, wdh_offen, p, p.tagesziel) is None:
        return None
    for cap in range(min(_cap_start(teile, tage, p), p.tagesziel), p.tagesziel + 1):
        ergebnis = _belegen(tage, teile, wdh_offen, p, cap)
        if ergebnis is not None:
            return ergebnis
    return None  # pragma: no cover  (cap == tagesziel ging oben schon)


def _benoetigt(teile, wdh_offen, p):
    gesamt = 0
    for t in teile:
        m = minuten_neu(len(t.fragen), p)
        gesamt += m + minuten_wdh(m, p)
    return gesamt + sum(w.minuten for w in wdh_offen if w.pflicht)


def _versuch(p, start, termin, blockiert, teile, stoffe, wdh_offen, fest, nutzen, extra=0):
    """Ein Planversuch. Gibt ``(eintraege oder None, lerntage, puffertage, verfuegbar)`` zurück."""
    tage = _tage(start, termin, blockiert, p, extra)
    if not tage:
        return None, 0, 0, 0
    lern, leicht_tag = tage[:-1], tage[-1]
    puffer = _puffer(lern, p, fest)
    normal = [d for d in lern if nutzen or d not in puffer]
    eintraege = _verteilen(normal, teile, wdh_offen, p)
    verfuegbar = len(normal) * p.tagesziel
    if eintraege is None:
        return None, len(normal), len(puffer), verfuegbar
    genutzt = {e.datum for e in eintraege}
    eintraege = list(eintraege) + _leicht(leicht_tag, stoffe, p)
    eintraege += [Eintrag(d, ART_PUFFER) for d in sorted(puffer) if d not in genutzt]
    eintraege.sort(key=lambda e: (e.datum, e.art == ART_PUFFER, e.art != ART_WDH))
    return tuple(eintraege), len(normal), len(puffer), verfuegbar


def _gekuerzt(teile, entfernen):
    """Nimmt ``entfernen`` Fragen vom Ende weg (leere Portionen entfallen)."""
    ergebnis = list(teile)
    while entfernen > 0 and ergebnis:
        letzter = ergebnis[-1]
        if len(letzter.fragen) <= entfernen:
            entfernen -= len(letzter.fragen)
            ergebnis.pop()
        else:
            ergebnis[-1] = Teil(
                letzter.schluessel, letzter.stoff, letzter.fragen[: len(letzter.fragen) - entfernen]
            )
            entfernen = 0
    return ergebnis


def _neu_geteilt(teile, p):
    """Dieselben Fragen in derselben Reihenfolge, nach Stoff zusammengefasst und neu geschnitten."""
    je_stoff = {}
    for t in teile:
        je_stoff.setdefault(t.stoff, []).extend(t.fragen)
    return teilen(je_stoff, p)


def _vorschlaege(p, start, termin, blockiert, teile, stoffe, wdh_offen, fest):
    """Rechnet die drei Auswege durch. Jeder steht nur drin, wenn er den Plan wirklich schafft."""
    ergebnis = []

    def geht(parameter=p, teile_=teile, extra=0):
        return (
            _versuch(
                parameter, start, termin, blockiert, teile_, stoffe, wdh_offen, fest, False, extra
            )[0]
            is not None
        )

    for extra in range(1, FRUEHER_MAX_TAGE + 1):
        if geht(extra=extra):
            ergebnis.append(Vorschlag(VORSCHLAG_FRUEHER, extra))
            break
    gesamt = sum(len(t.fragen) for t in teile)
    if gesamt > 1 and geht(teile_=_gekuerzt(teile, gesamt - 1)):
        niedrig, hoch = 1, gesamt - 1  # kleinste Kürzung, die reicht (hoch geht sicher)
        while niedrig < hoch:
            mitte = (niedrig + hoch) // 2
            if geht(teile_=_gekuerzt(teile, mitte)):
                hoch = mitte
            else:
                niedrig = mitte + 1
        ergebnis.append(Vorschlag(VORSCHLAG_KLEINER, hoch))
    for ziel in range(p.tagesziel + 1, p.tagesziel + p.ziel_zuschlag_max + 1):
        neu_p = replace(p, tagesziel=ziel)  # größeres Ziel, also auch größere Portionen
        if geht(parameter=neu_p, teile_=_neu_geteilt(teile, neu_p)):
            ergebnis.append(Vorschlag(VORSCHLAG_ZIEL, ziel))
            break
    return tuple(ergebnis)


# --- Hauptfunktion -----------------------------------------------------------------------------


def plane(
    p,
    *,
    start,
    termin,
    blockiert=frozenset(),
    teile=(),
    stoffe=None,
    wdh_offen=(),
    puffer_fest=None,
    puffer_nutzen=False,
):
    """Baut den Plan oder zeigt ehrlich, dass er nicht schaffbar ist.

    ``start``: frühester Tag (heute). ``termin``: Tag der Prüfung (bis zum Vortag wird geplant).
    ``blockiert``: Pausentage. ``teile``: neue Portionen (``teilen``). ``stoffe``: alle Fragen je
    Stoff für die leichte Wiederholung am Ende. ``wdh_offen``/``puffer_fest``: Stand beim
    Neuplanen. ``puffer_nutzen``: Puffertage dürfen Lerntage werden (nur beim Aufholen).
    """
    teile = list(teile)
    stoffe = {k: tuple(v) for k, v in (stoffe or {}).items() if v}
    if termin <= start:
        return Plan(False, GRUND_VORBEI)
    if not teile and not wdh_offen and not stoffe:
        return Plan(False, GRUND_KEIN_STOFF)
    knapp = (termin - start).days < p.vorlauf
    eintraege, lerntage, puffertage, verfuegbar = _versuch(
        p, start, termin, blockiert, teile, stoffe, wdh_offen, puffer_fest, puffer_nutzen
    )
    benoetigt = _benoetigt(teile, wdh_offen, p)
    if eintraege is None:
        return Plan(
            False,
            GRUND_ZU_VIEL,
            benoetigt=benoetigt,
            verfuegbar=verfuegbar,
            lerntage=lerntage,
            puffertage=puffertage,
            knapp=knapp,
            vorschlaege=_vorschlaege(
                p, start, termin, blockiert, teile, stoffe, wdh_offen, puffer_fest
            ),
        )
    lern_daten = {e.datum for e in eintraege if e.art in (ART_NEU, ART_WDH)}
    sollte_puffer = _puffer(
        _tage(start, termin, blockiert, p)[:-1],
        p,
        puffer_fest,
    )
    return Plan(
        True,
        GRUND_OK,
        eintraege,
        benoetigt,
        verfuegbar,
        lerntage,
        puffertage,
        bool(puffer_nutzen and sollte_puffer & lern_daten),
        knapp,
    )
