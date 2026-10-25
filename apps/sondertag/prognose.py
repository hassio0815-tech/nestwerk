"""Prognose und Kalibrierung (AP32, ARCHITECTURE 7.9, Review P-07/P-16).

``rechnen`` ist eine reine Funktion über ``Eingabe`` (keine DB, keine Uhr): gleiche Eingabe und
gleiche Faktoren ergeben dasselbe Ergebnis. ``eingabe`` liest die Daten (spielregeln, sondertag),
``fuer_kind`` baut daraus Prognose, Abweichung vom Ziel und Empfehlung. Der Empfehlungsvorschlag
rechnet ``rechnen`` mit Kandidatenfaktoren durch (Simulation); Übernahme läuft über die
Services von spielregeln (Audit dort).

Sondertag-Termine: für jede noch offene Sondertag-Regel der früheste Zeitpunkt (Rang erreicht +
Zeitbremse für die Mods; God-Mode-Zyklen nach aktiven Wochen), dann der Reihe nach durch die
Grenzen (``grenzen.einloesbar_ab``: höchstens N je App-Jahr, Mindestabstand).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from apps.kern import einstellungen, zeit
from apps.konten import selectors as konten
from apps.spielregeln import prognose as rang_prognose
from apps.spielregeln import selectors as spielregeln

from . import events, grenzen, selectors, services
from .meilensteine_start import GODMODE_SCHLUESSEL

GRUEN, GELB, ROT = "gruen", "gelb", "rot"
KANDIDATEN = tuple(Decimal(i) / 20 for i in range(8, 41))  # 0,40 … 2,00 in 0,05er-Schritten
SCHWELLE, WOCHEN = "schwelle", "wochen"
AMPEL_TEXT = {
    GRUEN: "Ziel erreicht",
    GELB: "knapp unter dem Ziel",
    ROT: "deutlich unter dem Ziel",
}
MAX_ZYKLEN = 8


@dataclass(frozen=True)
class Schritt:
    """Noch offene Sondertag-Regel."""

    name: str
    rang_ziel: int  # Stufe, die noch fehlt (0 = Rang schon erreicht)
    mods_fehlen: int
    godmode_wochen: int | None = None  # aktive Wochen bis zum Zyklusende (nur God Mode)
    godmode_zyklus: int = 0


@dataclass(frozen=True)
class Eingabe:
    heute: date
    basis: rang_prognose.Basis
    xp: int
    aktive_wochen: int
    stufen: tuple[tuple[int, str, int, int], ...]  # offen: (stufe, name, xp_schwelle, min_wochen)
    top_stufe: int
    global_schwelle: Decimal
    global_wochen: Decimal
    schritte: tuple[Schritt, ...]
    vorhanden: tuple[date, ...]  # angenommene + bereits verdiente (Warteschlange)
    regeln: grenzen.Regeln
    mods_pro_woche: int
    zyklus_laenge: int
    ziel: int


@dataclass(frozen=True)
class Termin:
    datum: date
    frueh: date  # ohne Grenzen
    name: str

    @property
    def verschoben_tage(self) -> int:
        return max(0, (self.datum - self.frueh).days)


@dataclass(frozen=True)
class JahrZahl:
    nummer: int
    beginn: date
    ende: date  # exklusiv
    anzahl: int
    ziel: int

    @property
    def ampel(self) -> str:
        diff = self.anzahl - self.ziel
        return GRUEN if diff >= 0 else GELB if diff == -1 else ROT

    @property
    def ampel_text(self) -> str:
        return AMPEL_TEXT[self.ampel]

    @property
    def letzter_tag(self) -> date:
        return self.ende - timedelta(days=1)

    @property
    def abweichung(self) -> int:
        return self.anzahl - self.ziel


@dataclass(frozen=True)
class Ergebnis:
    ziele: list[rang_prognose.RangZiel]
    termine: list[Termin]  # voraussichtliche (noch nicht verdiente) Sondertage
    jahre: list[JahrZahl]  # laufendes und nächstes App-Jahr (inkl. angenommener/verdienter)

    @property
    def fehlbetrag(self) -> int:
        return sum(max(0, j.ziel - j.anzahl) for j in self.jahre)


def _wochen_rechnen(mods: int, pro_woche: int) -> int:
    return math.ceil(mods / max(1, pro_woche)) if mods else 0


def _app_jahre(heute: date, go_live: date) -> list[zeit.AppJahr]:
    jahr = zeit.app_jahr(heute, go_live=go_live) if heute >= go_live else None
    if jahr is None:
        jahr = zeit.app_jahr_nummer(1, go_live)
    return [jahr, zeit.app_jahr_nummer(jahr.nummer + 1, go_live)]


def rechnen(e: Eingabe, faktor_schwelle: Decimal, faktor_wochen: Decimal) -> Ergebnis:
    """Reine Prognose. ``faktor_*`` = Faktor des Kindes (wird mit dem globalen multipliziert)."""
    fs = e.global_schwelle * faktor_schwelle
    fw = e.global_wochen * faktor_wochen
    stufen = [
        rang_prognose.StufeBedarf(s, n, math.ceil(Decimal(xp) * fs), math.ceil(Decimal(w) * fw))
        for s, n, xp, w in e.stufen
    ]
    ziele = rang_prognose.rang_ziele(
        e.basis, xp=e.xp, aktive_wochen=e.aktive_wochen, stufen=stufen, stichtag=e.heute
    )
    jahre = _app_jahre(e.heute, e.regeln.go_live)
    if not e.basis.genug:
        return Ergebnis(ziele, [], _jahre_zaehlen(jahre, list(e.vorhanden), e.ziel))
    rang_datum = {z.stufe: z.datum for z in ziele}
    fruehe: list[tuple[date, str]] = []
    for s in e.schritte:
        if s.godmode_wochen is not None:
            start = rang_datum.get(e.top_stufe, e.heute)  # höchster Rang noch offen?
            if start is None:
                continue
            for i in range(MAX_ZYKLEN):
                aktiv = s.godmode_wochen + i * e.zyklus_laenge
                wochen = rang_prognose.aufrunden(max(0, aktiv), e.basis.aktivquote)
                if wochen is None:
                    break
                tag = start + timedelta(weeks=wochen)
                if tag >= jahre[-1].ende:
                    break
                fruehe.append((tag, f"{s.name} (Zyklus {s.godmode_zyklus + i})"))
            continue
        if s.rang_ziel:
            start = rang_datum.get(s.rang_ziel)
            if start is None:
                continue  # Rang nie erreichbar bei diesem Tempo
        else:
            start = e.heute
        tag = start + timedelta(weeks=_wochen_rechnen(s.mods_fehlen, e.mods_pro_woche))
        fruehe.append((tag, s.name))
    daten = list(e.vorhanden)
    termine = []
    for tag, name in sorted(fruehe):
        ab = grenzen.einloesbar_ab(max(tag, e.heute), daten, e.regeln)
        termine.append(Termin(ab, tag, name))
        daten.append(ab)
    return Ergebnis(ziele, termine, _jahre_zaehlen(jahre, daten, e.ziel))


def _jahre_zaehlen(jahre, daten, ziel) -> list[JahrZahl]:
    return [
        JahrZahl(j.nummer, j.beginn, j.ende, sum(1 for d in daten if j.enthaelt(d)), ziel)
        for j in jahre
    ]


# --- Lesen ------------------------------------------------------------------------------------


def _schritte(kind) -> tuple[list[Schritt], int]:
    """(offene Schritte, Zyklus-Länge in aktiven Wochen)."""
    laenge = max(1, int(selectors._einstellung("avatar.godmode_zyklus_aktivwochen", 26)))
    namen = selectors._rang_namen()
    ergebnis = []
    for regel in (
        spielregeln.meilenstein_regeln()
        .filter(aktiv=True, belohnungsart=events.BELOHNUNGSART)
        .order_by("reihenfolge", "id")
    ):
        if regel.schluessel == GODMODE_SCHLUESSEL or regel.wiederholbar == "bereich":
            ist = selectors._wert("godmode_aktivwochen", kind)
            if ist is None or not namen:
                continue
            erreicht = {
                f.bereich for f in spielregeln.meilensteine_erreicht(kind, regel.schluessel)
            }
            zyklus = 1
            while f"zyklus-{zyklus}" in erreicht:
                zyklus += 1
            ergebnis.append(
                Schritt(
                    regel.name,
                    0,
                    0,
                    godmode_wochen=max(0, zyklus * laenge - ist),
                    godmode_zyklus=zyklus,
                )
            )
        else:
            k = selectors._kandidat_rang(kind, regel, namen)
            if k is not None:
                ergebnis.append(Schritt(regel.name, k["rang_ziel"], k["mods_fehlen"]))
    return ergebnis, laenge


def eingabe(kind, heute: date | None = None) -> Eingabe:
    heute = heute or zeit.heute()
    w = einstellungen.werte("spielregeln.prognose_ziel_sondertage")
    f = spielregeln.rang_fortschritt(kind)
    aktuell = f.rang
    offen = tuple(
        (r.stufe, r.name, r.xp_schwelle, r.min_aktive_wochen)
        for r in spielregeln.raenge()
        if aktuell is None or r.stufe > aktuell.stufe
    )
    schritte, laenge = _schritte(kind)
    queue = [max(e.einloesbar_ab, heute) for e in selectors.warteschlange(kind, heute)]
    alle = spielregeln.raenge()
    return Eingabe(
        heute=heute,
        basis=rang_prognose.basis(kind, heute),
        xp=f.xp,
        aktive_wochen=f.aktive_wochen,
        stufen=offen,
        top_stufe=alle[-1].stufe if alle else 0,
        global_schwelle=spielregeln.globaler_faktor(),
        global_wochen=spielregeln.wochen_faktor(None),
        schritte=tuple(schritte),
        vorhanden=tuple(services.angenommene_daten(kind) + queue),
        regeln=services.regeln(),
        mods_pro_woche=max(1, int(selectors._einstellung("avatar.max_zaehlende_mods_woche", 1))),
        zyklus_laenge=laenge,
        ziel=w["spielregeln.prognose_ziel_sondertage"],
    )


# --- Auswertung für die Eltern-Seite ----------------------------------------------------------


@dataclass(frozen=True)
class Empfehlung:
    knopf: str  # SCHWELLE | WOCHEN
    faktor: Decimal
    jahre: list[JahrZahl]  # Ergebnis der Simulation

    @property
    def knopf_text(self) -> str:
        return "XP-Schwellen" if self.knopf == SCHWELLE else "Mindestwochen"

    @property
    def text(self) -> str:
        zahlen = " / ".join(str(j.anzahl) for j in self.jahre)
        return (
            f"Faktor {str(self.faktor).replace('.', ',')} auf die {self.knopf_text} "
            f"würde {zahlen} Sondertage in den beiden App-Jahren ergeben."
        )


@dataclass
class Zeile:
    kind: object
    e: Eingabe
    ergebnis: Ergebnis
    faktor_schwelle: Decimal | None  # eigener Faktor (None = keiner)
    faktor_wochen: Decimal | None
    empfehlung: Empfehlung | None = None
    texte: list[str] = field(default_factory=list)

    @property
    def basis(self):
        return self.e.basis

    @property
    def naechster_rang(self):
        return next((z for z in self.ergebnis.ziele if z.wochen is not None), None)

    @property
    def naechster_sondertag(self) -> Termin | None:
        return min(self.ergebnis.termine, key=lambda t: t.datum, default=None)

    @property
    def xp_bindet(self) -> bool:
        return rang_prognose.xp_bindet(self.ergebnis.ziele)

    @property
    def ampel(self) -> str:
        reihenfolge = (GRUEN, GELB, ROT)
        return max((j.ampel for j in self.ergebnis.jahre), key=reihenfolge.index)

    @property
    def ampel_text(self) -> str:
        return AMPEL_TEXT[self.ampel]

    @property
    def mod_faktoren(self) -> tuple[Decimal, Decimal]:
        return spielregeln.preis_faktor(self.kind), spielregeln.bauzeit_faktor(self.kind)

    @property
    def ziel_getroffen(self) -> bool:
        return self.ergebnis.fehlbetrag == 0


def empfehlen(
    e: Eingabe, eigener_schwelle: Decimal, eigener_wochen: Decimal, aktuell: Ergebnis
) -> Empfehlung | None:
    """Kandidatenfaktoren durchrechnen; kleinster Fehlbetrag, bei Gleichstand die kleinste
    Änderung gegenüber heute. ``None``, wenn kein Faktor besser ist als der jetzige Stand."""
    if not e.basis.genug or aktuell.fehlbetrag == 0:
        return None
    beste = None
    for knopf, eigener in ((SCHWELLE, eigener_schwelle), (WOCHEN, eigener_wochen)):
        for kandidat in KANDIDATEN:
            if kandidat == eigener:
                continue
            if knopf == SCHWELLE:
                erg = rechnen(e, kandidat, eigener_wochen)
            else:
                erg = rechnen(e, eigener_schwelle, kandidat)
            if erg.fehlbetrag >= aktuell.fehlbetrag:
                continue
            schluessel = (erg.fehlbetrag, abs(kandidat - eigener), knopf != WOCHEN)
            if beste is None or schluessel < beste[0]:
                beste = (schluessel, Empfehlung(knopf, kandidat, erg.jahre))
    return beste[1] if beste else None


def fuer_kind(kind, heute: date | None = None) -> Zeile:
    e = eingabe(kind, heute)
    eigener_s = spielregeln.kind_faktor(kind)
    eigener_w = spielregeln.kind_wochen_faktor(kind)
    s, w = eigener_s or Decimal("1"), eigener_w or Decimal("1")
    erg = rechnen(e, s, w)
    zeile = Zeile(kind, e, erg, eigener_s, eigener_w)
    zeile.empfehlung = empfehlen(e, s, w, erg)
    if not e.basis.genug:
        zeile.texte.append(e.basis.hinweis)
    elif erg.ziele and not zeile.xp_bindet:
        zeile.texte.append(
            "Die XP-Schwellen bremsen hier nie: nur die Mindest-Aktivwochen bestimmen das Tempo "
            "(P-07). Ein Faktor auf die XP-Schwellen ändert deshalb nichts; "
            "den Faktor auf die Mindestwochen könnt ihr stattdessen nutzen."
        )
    return zeile


def uebersicht(heute: date | None = None) -> list[Zeile]:
    return [fuer_kind(kind, heute) for kind in konten.aktive_kinder()]


def faktor_text(wert: Decimal | None) -> str:
    return "" if wert is None else f"{wert:.2f}".replace(".", ",")
