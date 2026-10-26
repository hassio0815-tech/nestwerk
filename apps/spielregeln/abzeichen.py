"""Abzeichen- und Meilenstein-Engine (AP23, ARCHITECTURE 7.5/7.6, Entscheidung 1/12, K12).

Öffentlich über ``selectors`` (lesen) und ``services`` (schreiben).

- **Regeln sind Daten:** ``AbzeichenDefinition`` (eine Bedingung: Metrik, Vergleich, Schwelle) und
  ``MeilensteinRegel`` (UND über mehrere Bedingungen). Metriken kommen aus ``kern.registry``
  (``spielregeln.registry.metrik_wert``); neue Metriken späterer Module wirken ohne Änderung hier.
- **Verleihung/Erreichen ist ein Fakt:** ``unique(kind, regel, bereich)``; einmal verliehen bleibt
  verliehen (auch bei höherer Schwelle oder deaktivierter Regel). Parallel-sicher über die
  Eindeutigkeit (``get_or_create`` im Savepoint), nur der Anleger meldet.
- **Bereiche:** ``wiederholbar = bereich`` verleiht je Bereich der Metrik (``metrik.<x>.bereiche``),
  z. B. je Quartal (``2027-Q1``) oder je Rang (``rang-3``).
- **Auslöser:** Ende jeder Auswertung eines Kindes (``kind_auswerten``: Aktivität, Pause, Storno,
  Wochenabschluss, Job ``wochen_sicherstellen`` = Catch-up), Ereignis ``rang.aufgestiegen``
  (XP-Pfad), Regeländerung durch Eltern. Module mit eigenen Metriken rufen nach einer Änderung
  ``services.abzeichen_pruefen(kind)``; spätestens der stündliche Job holt alles nach.
- **Ereignisse:** ``abzeichen.verliehen`` (Kind: Pop-up, Eltern: Benachrichtigung) einmal je
  Prüfung mit allen neuen Abzeichen (keine Pop-up-Flut beim Catch-up); ``meilenstein.erreicht``
  (intern, z. B. ``sondertag`` AP27) je Fakt, immer – auch bei ``melden=False``, weil Folgemodule
  darauf ihre Ansprüche gründen.
"""

from __future__ import annotations

import logging
import operator
from dataclasses import dataclass
from functools import lru_cache

from django.contrib.staticfiles import finders
from django.db import transaction
from django.templatetags.static import static
from django.utils.text import slugify

from apps.ereignisse import services as ereignisse
from apps.kern import audit, zeit
from apps.kern import registry as kern_registry
from apps.kern import svg as kern_svg
from apps.konten import selectors as konten

from . import events
from .models import (
    AbzeichenDefinition,
    AbzeichenVerleihung,
    MeilensteinErreicht,
    MeilensteinRegel,
    Vergleich,
    Wiederholbar,
)
from .registry import hat_bereiche, metrik_bereiche, metrik_wert

logger = logging.getLogger("nestwerk.spielregeln")

VERGLEICHE = {">=": operator.ge, ">": operator.gt, "==": operator.eq}
NAME_MAX = 60
BESCHREIBUNG_MAX = 200
SCHWELLE_MAX = 1_000_000
NAECHSTE_MAX = 3

# Platzhalter-Icons aus dem Sprite je Gruppe, bis AP28 eigene Grafiken liefert
GRUPPEN_ICON = {
    "tagesserie": "funke",
    "wochenserie": "kalender",
    "quartal": "stern",
    "rang": "pokal",
}
STANDARD_ICON = "stern"
_METRIK_GRUPPE = {
    "tagesserie": "tagesserie",
    "rekord_tagesserie": "tagesserie",
    "wochenserie": "wochenserie",
    "rekord_wochenserie": "wochenserie",
    "aktive_wochen": "wochenserie",
    "quartal_voll_aktiv": "quartal",
    "rang": "rang",
}


class AbzeichenFehler(ValueError):
    """Fachlicher Fehler (Meldung ist für Eltern lesbar)."""


@dataclass(frozen=True)
class Bedingung:
    metrik: str
    vergleich: str
    wert: int

    def erfuellt(self, ist: int) -> bool:
        return VERGLEICHE[self.vergleich](ist, self.wert)


def bedingung_lesen(roh) -> Bedingung:
    """``{"metrik": "rang", "vergleich": ">=", "wert": 2}`` prüfen (Metrik registriert)."""
    if not isinstance(roh, dict):
        raise AbzeichenFehler("Bedingung: Objekt mit metrik, vergleich, wert erwartet.")
    metrik = roh.get("metrik")
    vergleich = roh.get("vergleich", Vergleich.MIN)
    wert = roh.get("wert")
    if not isinstance(metrik, str) or metrik not in kern_registry.metrik_verzeichnis:
        raise AbzeichenFehler(f"Unbekannte Metrik: {metrik!r}.")
    if vergleich not in VERGLEICHE:
        raise AbzeichenFehler(f"Unbekannter Vergleich: {vergleich!r}.")
    if isinstance(wert, bool) or not isinstance(wert, int) or not 0 <= wert <= SCHWELLE_MAX:
        raise AbzeichenFehler("Wert: ganze Zahl ab 0 erwartet.")
    return Bedingung(metrik, vergleich, wert)


def _bedingungen(regel) -> list[Bedingung]:
    if isinstance(regel, AbzeichenDefinition):
        return [Bedingung(regel.metrik, regel.vergleich, regel.schwelle)]
    return [
        Bedingung(b["metrik"], b.get("vergleich", Vergleich.MIN), b["wert"])
        for b in regel.bedingungen
    ]


class _Werte:
    """Metrik-Werte eines Kindes, je Prüfung einmal berechnet."""

    def __init__(self, kind):
        self.kind = kind
        self._wert = {}
        self._bereiche = {}

    def wert(self, metrik) -> int:
        if metrik not in self._wert:
            self._wert[metrik] = int(metrik_wert(metrik, self.kind) or 0)
        return self._wert[metrik]

    def bereiche(self, metrik):
        if metrik not in self._bereiche:
            self._bereiche[metrik] = metrik_bereiche(metrik, self.kind)
        return self._bereiche[metrik]


@dataclass(frozen=True)
class Treffer:
    bereich: str
    bezeichnung: str
    werte: dict


def auswerten(bedingungen: list[Bedingung], wiederholbar: str, werte: _Werte) -> list[Treffer]:
    """Erfüllte Bereiche einer Regel (UND über alle Bedingungen).

    ``einmalig``: ein Treffer mit Bereich ``""``. ``bereich``: je Bereich der Metriken mit
    Bereichen; Bedingungen auf Metriken ohne Bereiche gelten mit ihrem Gesamtwert."""
    if not bedingungen:
        return []
    if wiederholbar == Wiederholbar.EINMALIG:
        stand = {}
        for b in bedingungen:
            stand[b.metrik] = werte.wert(b.metrik)
            if not b.erfuellt(stand[b.metrik]):
                return []
        return [Treffer("", "", stand)]
    je = {b.metrik: werte.bereiche(b.metrik) for b in bedingungen}
    je = {m: v for m, v in je.items() if v is not None}
    if not je:
        return []
    treffer = []
    for bereich in sorted(set().union(*je.values())):
        stand, bezeichnung = {}, ""
        for b in bedingungen:
            if b.metrik in je:
                eintrag = je[b.metrik].get(bereich)
                if eintrag is None:
                    break
                stand[b.metrik], name = eintrag
                bezeichnung = bezeichnung or name
            else:
                stand[b.metrik] = werte.wert(b.metrik)
            if not b.erfuellt(stand[b.metrik]):
                break
        else:
            treffer.append(Treffer(bereich, bezeichnung, stand))
    return treffer


# --- Prüfen (schreibt Fakten) -----------------------------------------------------------------


@dataclass
class Pruefung:
    verliehen: list
    erreicht: list


def _titel(verleihung) -> str:
    name = verleihung.abzeichen.name
    return f"{name} · {verleihung.bereich_bezeichnung}" if verleihung.bereich else name


@transaction.atomic
def pruefen(kind, *, jetzt=None, melden=True) -> Pruefung:
    """Wertet alle aktiven Abzeichen- und Meilenstein-Regeln für ``kind`` aus und legt fehlende
    Fakten an. Idempotent (Catch-up beliebig oft). ``melden=False``: ohne Abzeichen-Pop-up
    (Reparatur); ``meilenstein.erreicht`` entsteht trotzdem."""
    ergebnis = Pruefung([], [])
    if getattr(kind, "rolle", None) != "kind" or not getattr(kind, "pk", None):
        return ergebnis
    jetzt = jetzt or zeit.jetzt()
    werte = _Werte(kind)

    vorhanden = set(
        AbzeichenVerleihung.objects.filter(kind=kind).values_list("abzeichen_id", "bereich")
    )
    for definition in AbzeichenDefinition.objects.filter(aktiv=True):
        for t in _treffer(definition, werte):
            if (definition.pk, t.bereich) in vorhanden:
                continue
            fakt, neu = AbzeichenVerleihung.objects.get_or_create(
                kind=kind,
                abzeichen=definition,
                bereich=t.bereich,
                defaults={
                    "bereich_bezeichnung": t.bezeichnung,
                    "wert": t.werte.get(definition.metrik, 0),
                    "schwelle": definition.schwelle,
                    "verliehen_am": jetzt,
                },
            )
            if neu:
                ergebnis.verliehen.append(fakt)

    erreicht = set(MeilensteinErreicht.objects.filter(kind=kind).values_list("regel_id", "bereich"))
    for regel in MeilensteinRegel.objects.filter(aktiv=True):
        for t in _treffer(regel, werte):
            if (regel.pk, t.bereich) in erreicht:
                continue
            fakt, neu = MeilensteinErreicht.objects.get_or_create(
                kind=kind,
                regel=regel,
                bereich=t.bereich,
                defaults={"werte": t.werte, "erreicht_am": jetzt},
            )
            if neu:
                _meilenstein_melden(kind, fakt)
                ergebnis.erreicht.append(fakt)

    if ergebnis.verliehen:
        _abzeichen_melden(kind, ergebnis.verliehen, melden)
    return ergebnis


def _treffer(regel, werte) -> list[Treffer]:
    try:
        return auswerten(_bedingungen(regel), regel.wiederholbar, werte)
    except (kern_registry.UnbekannterEintrag, KeyError, TypeError) as fehler:
        # Metrik eines entfernten/fehlenden Moduls oder kaputte Bedingung: Regel überspringen
        logger.warning("Regel %s übersprungen: %s", regel.schluessel, fehler)
        return []


def _abzeichen_melden(kind, neu, melden):
    titel = [_titel(v) for v in neu]
    audit.protokollieren(
        "abzeichen.verliehen",
        akteur=None,
        objekt=neu[-1],
        kind=kind,
        details={"abzeichen": [f"{v.abzeichen.schluessel}:{v.bereich}" for v in neu]},
    )
    if not melden:
        return
    erstes = neu[0]
    if len(neu) == 1:
        anzeige, beschreibung = titel[0], erstes.abzeichen.beschreibung or "Neu in der Vitrine."
    else:
        anzeige = f"{titel[0]} (+{len(neu) - 1} weitere)"
        beschreibung = f"{len(neu)} neue Abzeichen: " + ", ".join(titel)
    ereignisse.veroeffentlichen(
        events.ABZEICHEN_VERLIEHEN,
        kind=kind,
        daten={
            "abzeichen": anzeige,
            "beschreibung": beschreibung,
            "anzahl": len(neu),
            "symbol": erstes.abzeichen.symbol,
            "verleihungen": [v.pk for v in neu],
            "schluessel": [v.abzeichen.schluessel for v in neu],
        },
        schluessel=f"{events.ABZEICHEN_VERLIEHEN}:{kind.pk}:{erstes.pk}",
    )


def _meilenstein_melden(kind, fakt):
    regel = fakt.regel
    ereignis = ereignisse.veroeffentlichen(
        events.MEILENSTEIN_ERREICHT,
        kind=kind,
        daten={
            "meilenstein": regel.name,
            "regel": regel.schluessel,
            "regel_id": regel.pk,
            "bereich": fakt.bereich,
            "belohnungsart": regel.belohnungsart,
            "modul": regel.modul,
            "erreicht": fakt.pk,
            "werte": fakt.werte,
        },
        schluessel=f"{events.MEILENSTEIN_ERREICHT}:{fakt.pk}",
    )
    MeilensteinErreicht.objects.filter(pk=fakt.pk).update(ereignis=ereignis)
    fakt.ereignis = ereignis
    audit.protokollieren(
        "meilenstein.erreicht",
        akteur=None,
        objekt=fakt,
        kind=kind,
        details={"regel": regel.schluessel, "bereich": fakt.bereich, "werte": fakt.werte},
    )


def pruefen_sicher(kind, **kwargs) -> Pruefung:
    """Savepoint: ein Fehler hier darf die auslösende Änderung nicht kippen; der Job holt es
    nach."""
    try:
        with transaction.atomic():
            return pruefen(kind, **kwargs)
    except Exception:
        logger.exception("Abzeichen von %s nicht geprüft", getattr(kind, "pk", None))
        return Pruefung([], [])


def alle_pruefen(jetzt=None, melden=True) -> dict:
    """Job/Catch-up: alle aktiven Kinder, je Kind eigene Transaktion."""
    verliehen = erreicht = 0
    for kind in konten.aktive_kinder():
        with transaction.atomic():
            p = pruefen_sicher(kind, jetzt=jetzt, melden=melden)
        verliehen += len(p.verliehen)
        erreicht += len(p.erreicht)
    return {"abzeichen_verliehen": verliehen, "meilensteine_erreicht": erreicht}


def nach_ereignis(ereignis):
    """Synchroner Handler (z. B. ``rang.aufgestiegen``): Regeln des Kindes prüfen."""
    if ereignis.kind_id is not None:
        pruefen_sicher(ereignis.kind)


# --- Lesen ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """``bild``: URL der Abzeichen-Grafik (AP28, ``static/abzeichen/<schluessel>.svg``) oder
    ``""``; ``icon``: Platzhalter aus dem Sprite."""

    schluessel: str
    bild: str
    icon: str


# Abzeichen-Grafiken (AP28): eigene Fläche 64 x 64, Verläufe erlaubt; geprüft mit dem gemeinsamen
# SVG-Sanitizer aus kern (Review AP31; vorher mit viewBox-Trick gegen die Avatar-Whitelist).
GRAFIK_VIEWBOX = (0, 0, 64, 64)


def grafik_pruefen(text: str) -> str | None:
    """``None``, wenn eine Abzeichen-Grafik die Whitelist besteht, sonst die Fehlermeldung."""
    return kern_svg.svg_pruefen(text, viewbox=GRAFIK_VIEWBOX, verlaeufe=True)


@lru_cache(maxsize=512)
def _bild(name: str) -> str:
    pfad = f"abzeichen/{name}.svg"
    return static(pfad) if finders.find(pfad) else ""


def symbol(definition, bereich: str = "") -> Symbol:
    """Grafik je Bereich (``<symbol>-<bereich>.svg``, z. B. ``rangaufstieg-rang-3.svg``), sonst
    je Abzeichen (``<symbol>.svg``), sonst Platzhalter-Icon der Gruppe."""
    bild = (_bild(f"{definition.symbol}-{bereich}") if bereich else "") or _bild(definition.symbol)
    return Symbol(definition.symbol, bild, GRUPPEN_ICON.get(definition.gruppe, STANDARD_ICON))


def definitionen(nur_aktive=False):
    qs = AbzeichenDefinition.objects.all()
    return qs.filter(aktiv=True) if nur_aktive else qs


def verleihungen(kind):
    return AbzeichenVerleihung.objects.filter(kind=kind).select_related("abzeichen")


@dataclass(frozen=True)
class Verdient:
    verleihung: AbzeichenVerleihung
    titel: str
    symbol: Symbol


@dataclass(frozen=True)
class Naechstes:
    abzeichen: AbzeichenDefinition
    wert: int
    ziel: int
    fehlt: int
    prozent: int
    symbol: Symbol


@dataclass(frozen=True)
class Vitrine:
    verdient: list
    naechste: list
    rekord_wochenserie: int
    rekord_tagesserie: int


def naechste(kind, *, verdient_ids=None, limit=NAECHSTE_MAX) -> list[Naechstes]:
    """Nächste erreichbare einmalige Abzeichen (je Metrik die kleinste offene Schwelle),
    sortiert nach Fortschritt."""
    if verdient_ids is None:
        verdient_ids = set(
            AbzeichenVerleihung.objects.filter(kind=kind).values_list("abzeichen_id", flat=True)
        )
    werte = _Werte(kind)
    je_metrik = {}
    offen = definitionen(nur_aktive=True).filter(
        wiederholbar=Wiederholbar.EINMALIG, vergleich__in=[Vergleich.MIN, Vergleich.MEHR]
    )
    for d in offen.exclude(pk__in=verdient_ids).order_by("schwelle", "reihenfolge"):
        if d.metrik in je_metrik:
            continue
        try:
            wert = werte.wert(d.metrik)
        except kern_registry.UnbekannterEintrag:
            continue
        ziel = d.schwelle + (1 if d.vergleich == Vergleich.MEHR else 0)
        prozent = 100 if ziel <= 0 else min(99, max(0, wert) * 100 // ziel)
        je_metrik[d.metrik] = Naechstes(d, wert, ziel, max(0, ziel - wert), prozent, symbol(d))
    auswahl = sorted(je_metrik.values(), key=lambda n: (-n.prozent, n.abzeichen.reihenfolge))
    return auswahl[:limit]


def vitrine(kind) -> Vitrine:
    from . import selectors

    liste = list(verleihungen(kind))
    verdient = [Verdient(v, _titel(v), symbol(v.abzeichen, v.bereich)) for v in liste]
    stand = selectors.stand(kind)
    return Vitrine(
        verdient=verdient,
        naechste=naechste(kind, verdient_ids={v.abzeichen_id for v in liste}),
        rekord_wochenserie=stand.rekord_wochenserie,
        rekord_tagesserie=stand.rekord_tagesserie,
    )


def meilenstein_regeln(modul=None):
    qs = MeilensteinRegel.objects.all()
    return qs.filter(modul=modul) if modul else qs


def meilensteine_erreicht(kind, regel=None):
    """Fakten eines Kindes (optional nur einer Regel, Schlüssel oder Objekt)."""
    qs = MeilensteinErreicht.objects.filter(kind=kind).select_related("regel")
    if isinstance(regel, str):
        return qs.filter(regel__schluessel=regel)
    return qs.filter(regel=regel) if regel is not None else qs


def meilenstein_erreicht(kind, schluessel, bereich="") -> MeilensteinErreicht | None:
    return meilensteine_erreicht(kind, schluessel).filter(bereich=bereich).first()


@dataclass(frozen=True)
class BedingungsStand:
    metrik: str
    vergleich: str
    ziel: int
    wert: int | None  # None = Metrik nicht registriert
    erfuellt: bool


def meilenstein_stand(kind, schluessel) -> list[BedingungsStand]:
    """Je Bedingung Ziel, aktueller Gesamtwert und ob erfüllt (für Fortschrittsanzeigen)."""
    regel = MeilensteinRegel.objects.get(schluessel=schluessel)
    werte = _Werte(kind)
    ergebnis = []
    for b in _bedingungen(regel):
        try:
            wert = werte.wert(b.metrik)
        except kern_registry.UnbekannterEintrag:
            wert = None
        ergebnis.append(
            BedingungsStand(
                b.metrik, b.vergleich, b.wert, wert, wert is not None and b.erfuellt(wert)
            )
        )
    return ergebnis


def eltern_uebersicht() -> list[dict]:
    """Je aktivem Kind: verdiente Abzeichen und nächste (Eltern-Seite/Kachel)."""
    zeilen = []
    for kind in konten.aktive_kinder():
        liste = list(verleihungen(kind))
        zeilen.append(
            {
                "kind": kind,
                "verdient": [Verdient(v, _titel(v), symbol(v.abzeichen, v.bereich)) for v in liste],
                "naechste": naechste(kind, verdient_ids={v.abzeichen_id for v in liste}),
            }
        )
    return zeilen


# --- Regeln pflegen (Eltern, Module) ----------------------------------------------------------


def _eltern_pruefen(von):
    if getattr(von, "rolle", None) != "eltern":
        raise AbzeichenFehler("Abzeichen ändern nur Eltern.")


def _ganzzahl(wert, feld, maximum=SCHWELLE_MAX):
    if isinstance(wert, str) and wert.strip().isdigit():
        wert = int(wert.strip())
    if isinstance(wert, bool) or not isinstance(wert, int) or not 0 <= wert <= maximum:
        raise AbzeichenFehler(f"{feld}: bitte eine ganze Zahl von 0 bis {maximum}.")
    return wert


_UMLAUTE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def _neuer_schluessel(name) -> str:
    basis = (slugify(name.translate(_UMLAUTE)) or "abzeichen")[:50]
    schluessel, n = basis, 2
    while AbzeichenDefinition.objects.filter(schluessel=schluessel).exists():
        schluessel, n = f"{basis}-{n}", n + 1
    return schluessel


@transaction.atomic
def abzeichen_speichern(
    definition,
    *,
    von,
    name,
    metrik,
    schwelle,
    beschreibung="",
    vergleich=Vergleich.MIN,
    wiederholbar=Wiederholbar.EINMALIG,
    reihenfolge=None,
    aktiv=True,
):
    """Eltern legen ein Abzeichen an (``definition=None``) oder ändern es (Audit). Bestehende
    Verleihungen bleiben; eine niedrigere Schwelle kann sofort verleihen."""
    _eltern_pruefen(von)
    name = (name or "").strip()
    beschreibung = (beschreibung or "").strip()
    if not name or len(name) > NAME_MAX:
        raise AbzeichenFehler(f"Name: 1 bis {NAME_MAX} Zeichen.")
    if len(beschreibung) > BESCHREIBUNG_MAX:
        raise AbzeichenFehler(f"Beschreibung: höchstens {BESCHREIBUNG_MAX} Zeichen.")
    bedingung_lesen(
        {"metrik": metrik, "vergleich": vergleich, "wert": _ganzzahl(schwelle, "Schwelle")}
    )
    if wiederholbar not in Wiederholbar.values:
        raise AbzeichenFehler("Wiederholung: einmalig oder je Bereich.")
    if wiederholbar == Wiederholbar.BEREICH and not hat_bereiche(metrik):
        raise AbzeichenFehler("Diese Metrik hat keine Bereiche – bitte „einmalig“ wählen.")
    neu = {
        "name": name,
        "beschreibung": beschreibung,
        "metrik": metrik,
        "vergleich": vergleich,
        "schwelle": _ganzzahl(schwelle, "Schwelle"),
        "wiederholbar": wiederholbar,
        "aktiv": bool(aktiv),
    }
    if reihenfolge not in (None, ""):
        neu["reihenfolge"] = _ganzzahl(reihenfolge, "Reihenfolge", 32767)
    if definition is None:
        schluessel = _neuer_schluessel(name)
        definition = AbzeichenDefinition.objects.create(
            schluessel=schluessel,
            symbol=schluessel,
            gruppe=_METRIK_GRUPPE.get(metrik, kern_registry.metrik(metrik).modul)[:30],
            modul="spielregeln",
            **neu,
        )
        audit.protokollieren("abzeichen.angelegt", akteur=von, objekt=definition, details=neu)
    else:
        definition = AbzeichenDefinition.objects.select_for_update().get(pk=definition.pk)
        alt = {f: getattr(definition, f) for f in neu}
        geaendert = {f: v for f, v in neu.items() if alt[f] != v}
        if not geaendert:
            return definition
        AbzeichenDefinition.objects.filter(pk=definition.pk).update(**geaendert)
        definition.refresh_from_db()
        audit.protokollieren(
            "abzeichen.geaendert",
            akteur=von,
            objekt=definition,
            details={"alt": {f: alt[f] for f in geaendert}, "neu": geaendert},
        )
    if definition.aktiv:
        for kind in konten.aktive_kinder():
            pruefen_sicher(kind)
    return definition


@transaction.atomic
def abzeichen_aktiv_setzen(definition, aktiv: bool, *, von):
    """Deaktivieren/aktivieren (keine Löschung: Verleihungen bleiben sichtbar)."""
    _eltern_pruefen(von)
    if (
        AbzeichenDefinition.objects.filter(pk=definition.pk)
        .exclude(aktiv=aktiv)
        .update(aktiv=aktiv)
    ):
        definition.refresh_from_db()
        audit.protokollieren(
            "abzeichen.geaendert",
            akteur=von,
            objekt=definition,
            details={"alt": {"aktiv": not aktiv}, "neu": {"aktiv": aktiv}},
        )
        if aktiv:
            for kind in konten.aktive_kinder():
                pruefen_sicher(kind)
    return definition


def meilenstein_uebersicht() -> list[dict]:
    """Eltern-Verwaltung (AP27): je Regel Bedingungen mit Metrik-Namen und Anzahl Fakten."""
    zeilen = []
    for regel in MeilensteinRegel.objects.order_by("reihenfolge", "id"):
        bedingungen = []
        for b in regel.bedingungen or []:
            metrik = b.get("metrik", "")
            try:
                bezeichnung = kern_registry.metrik(metrik).bezeichnung
            except kern_registry.UnbekannterEintrag:
                bezeichnung = f"{metrik} (Modul fehlt)"
            bedingungen.append({**b, "bezeichnung": bezeichnung})
        zeilen.append(
            {"regel": regel, "bedingungen": bedingungen, "anzahl": regel.erreicht.count()}
        )
    return zeilen


@transaction.atomic
def meilenstein_speichern(regel, *, von, name, bedingungen, beschreibung=""):
    """Eltern passen Name, Beschreibung und Bedingungen an (Audit). Erreichte Meilensteine bleiben
    (Fakten); gelockerte Bedingungen können sofort neue Fakten auslösen."""
    _eltern_pruefen(von)
    name = (name or "").strip()
    beschreibung = (beschreibung or "").strip()
    if not name or len(name) > 80:
        raise AbzeichenFehler("Name: 1 bis 80 Zeichen.")
    if len(beschreibung) > BESCHREIBUNG_MAX:
        raise AbzeichenFehler(f"Beschreibung: höchstens {BESCHREIBUNG_MAX} Zeichen.")
    if not isinstance(bedingungen, list | tuple) or not bedingungen:
        raise AbzeichenFehler("Mindestens eine Bedingung.")
    gelesen = [
        bedingung_lesen({**b, "wert": _ganzzahl(b.get("wert"), "Wert")}) for b in bedingungen
    ]
    if regel.wiederholbar == Wiederholbar.BEREICH and not any(
        hat_bereiche(b.metrik) for b in gelesen
    ):
        raise AbzeichenFehler("„Je Bereich“ braucht mindestens eine Metrik mit Bereichen.")
    regel = MeilensteinRegel.objects.select_for_update().get(pk=regel.pk)
    neu = {
        "name": name,
        "beschreibung": beschreibung,
        "bedingungen": [
            {"metrik": b.metrik, "vergleich": b.vergleich, "wert": b.wert} for b in gelesen
        ],
    }
    alt = {f: getattr(regel, f) for f in neu}
    geaendert = {f: v for f, v in neu.items() if alt[f] != v}
    if not geaendert:
        return regel
    MeilensteinRegel.objects.filter(pk=regel.pk).update(**geaendert)
    regel.refresh_from_db()
    audit.protokollieren(
        "meilenstein.geaendert",
        akteur=von,
        objekt=regel,
        details={"alt": {f: alt[f] for f in geaendert}, "neu": geaendert},
    )
    if regel.aktiv:
        for kind in konten.aktive_kinder():
            pruefen_sicher(kind)
    return regel


@transaction.atomic
def meilenstein_aktiv_setzen(regel, aktiv: bool, *, von):
    """Meilenstein ein-/ausschalten (keine Löschung: erreichte Fakten und Ansprüche bleiben)."""
    _eltern_pruefen(von)
    if MeilensteinRegel.objects.filter(pk=regel.pk).exclude(aktiv=aktiv).update(aktiv=aktiv):
        regel.refresh_from_db()
        audit.protokollieren(
            "meilenstein.geaendert",
            akteur=von,
            objekt=regel,
            details={"alt": {"aktiv": not aktiv}, "neu": {"aktiv": aktiv}},
        )
        if aktiv:
            for kind in konten.aktive_kinder():
                pruefen_sicher(kind)
    return regel


@transaction.atomic
def meilenstein_anlegen(
    schluessel,
    name,
    bedingungen,
    *,
    modul,
    beschreibung="",
    belohnungsart="",
    wiederholbar=Wiederholbar.EINMALIG,
    reihenfolge=100,
    aktiv=True,
):
    """Meilenstein-Regel anlegen (Module, z. B. AP27; idempotent: besteht der Schlüssel, bleibt
    die Zeile unverändert). ``bedingungen``: Liste von ``{"metrik", "vergleich", "wert"}``, alle
    müssen gelten (UND)."""
    if not isinstance(bedingungen, list | tuple) or not bedingungen:
        raise AbzeichenFehler("Mindestens eine Bedingung.")
    gelesen = [bedingung_lesen(b) for b in bedingungen]
    if wiederholbar not in Wiederholbar.values:
        raise AbzeichenFehler("Wiederholung: einmalig oder je Bereich.")
    if wiederholbar == Wiederholbar.BEREICH and not any(hat_bereiche(b.metrik) for b in gelesen):
        raise AbzeichenFehler("„Je Bereich“ braucht mindestens eine Metrik mit Bereichen.")
    if slugify(schluessel) != schluessel or not 0 < len(schluessel) <= 60:
        raise AbzeichenFehler("Schlüssel: Kleinbuchstaben, Ziffern, Bindestrich (max. 60).")
    regel, _ = MeilensteinRegel.objects.get_or_create(
        schluessel=schluessel,
        defaults={
            "name": name[:80],
            "beschreibung": beschreibung[:200],
            "bedingungen": [
                {"metrik": b.metrik, "vergleich": b.vergleich, "wert": b.wert} for b in gelesen
            ],
            "belohnungsart": belohnungsart[:40],
            "wiederholbar": wiederholbar,
            "modul": modul[:40],
            "reihenfolge": reihenfolge,
            "aktiv": aktiv,
        },
    )
    return regel
