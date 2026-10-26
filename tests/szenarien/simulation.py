"""Gesamt-Simulation über Wochen/Jahre (Review AP31) mit simulierter Zeit.

Treibt alle Module über ihre Services, wie es Kinder, Eltern und Jobs tun würden:

- Kinder melden Aufgaben (Vertrauen = sofort bestätigt; Eltern-Freigabe: Sonntag gemeldet, Montag
  im Puffer oder Mittwoch nach dem Wochenabschluss bestätigt), kaufen Mods sobald möglich (nur
  Seltenheiten ab 2 bis zum eigenen Rang, God-Mode-Sets), wünschen sich Sondertage, stimmen
  sonntags ab.
- Eltern bestätigen, korrigieren, setzen Pausen (Kind/Familie), nehmen Wünsche an.
- Jobs laufen täglich (``wochen_sicherstellen``, ``familienwoche_sicherstellen``,
  ``mods_fertigstellen``, ``sondertag_sicherstellen``) – am Ende jeder Woche zweimal, um die
  Idempotenz zu prüfen.

Ergebnis: ``Protokoll`` mit Rangaufstiegen, Sondertagen (verdient/angenommen) und XP je Woche
für Invarianten und die Startwert-Kalibrierung (Entscheidung 14).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction

from apps.aufgaben import services as aufgaben
from apps.aufgaben import wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz
from apps.avatar import selectors as avatar_selectors
from apps.avatar import services as avatar
from apps.familienziel import selectors as familienziel_selectors
from apps.familienziel import services as familienziel
from apps.kern import zeit
from apps.kern.zeit import IsoWoche
from apps.punkte import selectors as punkte
from apps.sondertag import selectors as sondertag_selectors
from apps.sondertag import services as sondertag
from apps.spielregeln import services as spielregeln
from apps.spielregeln.tests.conftest import lok

WOCHENTAGE = ("mo", "di", "mi", "do", "fr", "sa", "so")


@dataclass
class Profil:
    """Fleiß eines Kindes: Punkte je Aufgabe und aktive Wochentage (0 = Montag)."""

    name: str
    punkte: int
    tage: tuple[int, ...]
    thema: str = "ritter"
    eltern_freigabe_sonntag: bool = False  # So melden, Mo bestätigen (Puffer, K1)
    pausen: tuple[tuple[int, int], ...] = ()  # (von_tag, bis_tag) relativ zu Go-live, Kind-Pause
    faul: tuple[int, ...] = ()  # Wochen-Nr. (ab 0) ohne Aufgaben und ohne Pause (Serie reißt)
    korrekturen: tuple[int, ...] = ()  # Tag-Nr.: an diesem Tag wird die letzte Aufgabe korrigiert

    @property
    def soll_woche(self) -> int:
        return self.punkte * len(self.tage)


@dataclass
class KindProtokoll:
    raenge: dict[int, int] = field(default_factory=dict)  # Stufe -> Woche (ab 1)
    sondertag_verdient: list[int] = field(default_factory=list)  # Wochen
    sondertag_angenommen: list[date] = field(default_factory=list)
    xp_woche: list[int] = field(default_factory=list)
    mods_gekauft: int = 0


@dataclass
class Protokoll:
    go_live: date
    kinder: dict = field(default_factory=dict)  # Name -> KindProtokoll
    familienziele: int = 0
    grossziele: int = 0
    helden: int = 0
    idempotenz_fehler: list = field(default_factory=list)


def _zaehlen():
    """Zeilenzahlen der Fakten-/Ergebnis-Tabellen (Idempotenz: Doppellauf ändert nichts)."""
    from django.apps import apps

    namen = [
        ("ereignisse", "Ereignis"),
        ("spielregeln", "Wochenauswertung"),
        ("spielregeln", "RangAufstieg"),
        ("spielregeln", "AbzeichenVerleihung"),
        ("spielregeln", "MeilensteinErreicht"),
        ("familienziel", "Familienwoche"),
        ("familienziel", "Grossziel"),
        ("sondertag", "SondertagAnspruch"),
        ("punkte", "Buchung"),
        ("avatar", "ModBesitz"),
        ("avatar", "ModSet"),
    ]
    stand = {m: apps.get_model(a, m).objects.count() for a, m in namen}
    w = apps.get_model("spielregeln", "Wochenauswertung")
    stand["helden"] = w.objects.filter(held_der_woche=True).count()
    stand["finalisiert"] = w.objects.filter(finalisiert_am__isnull=False).count()
    fw = apps.get_model("familienziel", "Familienwoche")
    stand["fw_status"] = sorted(fw.objects.values_list("status", flat=True))
    return stand


def jobs(jetzt=None):
    """Alle Spiel-Jobs einmal (wie die Crontab)."""
    spielregeln.wochen_sicherstellen(jetzt=jetzt)
    familienziel.sicherstellen(jetzt)
    avatar.mods_fertigstellen(jetzt)
    sondertag.nachholen()
    for kind in _kinder():
        sondertag.neu_berechnen(kind)
    sondertag.einloesbar_melden(jetzt)


def _kinder():
    from apps.konten import selectors as konten

    return list(konten.aktive_kinder())


class Simulation:
    def __init__(self, uhr, mama, kinder: dict, go_live: date):
        self.uhr = uhr
        self.mama = mama
        self.kinder = kinder  # Benutzer -> Profil
        self.go_live = go_live
        self.prot = Protokoll(go_live, {p.name: KindProtokoll() for p in kinder.values()})
        self._nr = itertools.count()
        self._aufgaben = {}
        self._offen = []  # (instanz, bestaetigen_am)
        self._letzte = {}  # kind.pk -> letzte bestätigte Instanz
        self.familien_pausen: tuple[tuple[int, int], ...] = ()
        # sparsam: nur Tage mit Aktivität, Montag und Sonntag simulieren (Mehrjahres-Lauf)
        self.sparsam = False
        for kind, profil in kinder.items():
            avatar.avatar_waehlen(kind, profil.thema, {})

    # --- Bausteine ----------------------------------------------------------------------------

    def _aufgabe(self, punkte_, freigabe):
        schluessel = (punkte_, freigabe)
        if schluessel not in self._aufgaben:
            self._aufgaben[schluessel] = Aufgabe.objects.create(
                titel=f"Aufgabe {punkte_} {freigabe}",
                punkte=punkte_,
                erstellt_von=self.mama,
                wiederholungsart=wiederholung.EINMALIG,
                freigabeart=freigabe,
            )
        return self._aufgaben[schluessel]

    def _melden(self, kind, punkte_, freigabe, jetzt):
        aufgabe = self._aufgabe(punkte_, freigabe)
        instanz = AufgabenInstanz.objects.create(
            aufgabe=aufgabe,
            titel_snapshot=aufgabe.titel,
            punkte_snapshot=aufgabe.punkte,
            freigabeart_snapshot=aufgabe.freigabeart,
        )
        aufgaben.interesse_zeigen(instanz, kind, jetzt=jetzt)
        aufgaben.erledigt_melden(instanz, kind, jetzt=jetzt)
        return instanz

    def _pausiert(self, profil, tag_nr):
        return any(a <= tag_nr <= b for a, b in (*profil.pausen, *self.familien_pausen))

    def _shop(self, kind, prot):
        """Kauft alles, was für Sondertage zählt und bezahlbar ist (günstigste zuerst)."""
        for _ in range(12):
            karten = []
            for gruppe in avatar_selectors.shop(kind):
                if gruppe.set_nummer is None and gruppe.stufe < 2:
                    continue  # Common zählt für keinen Sondertag (Zeitbremse nicht verschwenden)
                if gruppe.set_nummer is None and gruppe.stufe == 6:
                    continue  # God Mode: nur die Sets (O3)
                karten += [
                    (gruppe.set_nummer or 0, gruppe.stufe, k)
                    for k in gruppe.karten
                    if k.zustand == "kaufbar"
                ]
            if not karten:
                return
            _, _, karte = min(karten, key=lambda t: (t[0], t[1], t[2].konditionen.preis))
            avatar.mod_kaufen(kind, karte.mod)
            prot.mods_gekauft += 1

    def _sondertag(self, kind, heute):
        eintrag = sondertag_selectors.aktueller(kind, heute)
        if eintrag is None or not eintrag.einloesbar:
            return
        if not eintrag.wunsch_offen:
            sondertag.wunsch_senden(kind, eintrag.anspruch, wunsch="Ausflug", begleitung="egal")
        sondertag.annehmen(eintrag.anspruch, von=self.mama, heute=heute)

    # --- Ablauf -------------------------------------------------------------------------------

    def tag(self, tag_nr):
        heute = self.go_live + timedelta(days=tag_nr)
        wochentag = heute.weekday()
        woche_nr = tag_nr // 7
        if self.sparsam and wochentag not in {
            0,
            6,
            *(t for p in self.kinder.values() for t in p.tage),
        }:
            return
        self.uhr.stellen(lok(heute.year, heute.month, heute.day, 0, 30))
        jobs()
        if wochentag == 0:
            self._familienpause_setzen(tag_nr)

        # Kinder: Aufgaben
        jetzt = self.uhr.stellen(lok(heute.year, heute.month, heute.day, 17))
        for kind, profil in self.kinder.items():
            if woche_nr in profil.faul or self._pausiert(profil, tag_nr):
                continue
            if wochentag not in profil.tage:
                continue
            if profil.eltern_freigabe_sonntag and wochentag == 6:
                instanz = self._melden(kind, profil.punkte, "eltern", jetzt)
                # Mo im Puffer bestätigen, jede 10. Woche erst Mittwoch (Woche abgeschlossen)
                versatz = 3 if woche_nr % 10 == 9 else 1
                self._offen.append((instanz, heute + timedelta(days=versatz)))
            else:
                instanz = self._melden(kind, profil.punkte, "vertrauen", jetzt)
                self._letzte[kind.pk] = instanz

        # Eltern: Bestätigen, Korrigieren
        jetzt = self.uhr.stellen(lok(heute.year, heute.month, heute.day, 18))
        faellig = [(i, t) for i, t in self._offen if t <= heute]
        self._offen = [(i, t) for i, t in self._offen if t > heute]
        for instanz, _ in faellig:
            aufgaben.bestaetigen(instanz, von=self.mama, jetzt=jetzt)
            self._letzte[instanz.kind_id] = instanz
        for kind, profil in self.kinder.items():
            if tag_nr in profil.korrekturen and kind.pk in self._letzte:
                aufgaben.korrigieren(
                    self._letzte.pop(kind.pk), von=self.mama, begruendung="doch nicht", jetzt=jetzt
                )

        # Kinder: Shop, Sondertag, Abstimmung (Sonntag)
        self.uhr.stellen(lok(heute.year, heute.month, heute.day, 19))
        for kind, profil in self.kinder.items():
            prot = self.prot.kinder[profil.name]
            with transaction.atomic():
                self._shop(kind, prot)
            self._sondertag(kind, heute)
            if wochentag == 6:
                abstimmung = familienziel_selectors.abstimmung_offen()
                if abstimmung and abstimmung.optionen:
                    familienziel.stimme_abgeben(kind, abstimmung.optionen[0].pk)

        if wochentag == 6:
            self._wochenende(woche_nr, heute)

    def _familienpause_setzen(self, tag_nr):
        for von, bis in self.familien_pausen:
            if von == tag_nr:
                spielregeln.pause_setzen(
                    None,
                    von=self.mama,
                    ab=self.go_live + timedelta(days=von),
                    bis=self.go_live + timedelta(days=bis),
                )
        for kind, profil in self.kinder.items():
            for von, bis in profil.pausen:
                if von == tag_nr:
                    spielregeln.pause_setzen(
                        kind,
                        von=self.mama,
                        ab=self.go_live + timedelta(days=von),
                        bis=self.go_live + timedelta(days=bis),
                    )

    def _wochenende(self, woche_nr, sonntag):
        """Sonntag 23:00: Protokoll; Montag 00:30 + Dienstag 01:00 Jobs doppelt (Idempotenz)."""
        dienstag = sonntag + timedelta(days=2)
        self.uhr.stellen(lok(dienstag.year, dienstag.month, dienstag.day, 1))
        jobs()
        vorher = _zaehlen()
        jobs()
        nachher = _zaehlen()
        if vorher != nachher:
            self.prot.idempotenz_fehler.append((str(IsoWoche.von(sonntag)), vorher, nachher))

    def laufen(self, wochen):
        for tag_nr in range(wochen * 7):
            self.tag(tag_nr)
        self._abschluss(wochen)
        return self.prot

    def _abschluss(self, wochen):
        from apps.familienziel.models import Familienwoche, Grossziel
        from apps.sondertag.models import SondertagAnspruch
        from apps.spielregeln.models import RangAufstieg, Wochenauswertung

        for kind, profil in self.kinder.items():
            prot = self.prot.kinder[profil.name]
            for w in range(wochen):  # XP je Woche nach Bezugsdatum (inkl. Bestätigung im Puffer)
                woche = IsoWoche.von(self.go_live + timedelta(days=7 * w))
                prot.xp_woche.append(punkte.xp_zeitraum(woche.montag, woche.sonntag, kind=kind))
            for fakt in RangAufstieg.objects.filter(kind=kind).select_related("rang"):
                tage = (zeit.heute(fakt.erreicht_am) - self.go_live).days
                prot.raenge[fakt.rang.stufe] = tage // 7 + 1
            for a in SondertagAnspruch.objects.filter(kind=kind).order_by("verdient_am"):
                prot.sondertag_verdient.append(
                    (zeit.heute(a.verdient_am) - self.go_live).days // 7 + 1
                )
                if a.annahme_datum:
                    prot.sondertag_angenommen.append(a.annahme_datum)
        self.prot.familienziele = Familienwoche.objects.filter(status="erreicht").count()
        self.prot.grossziele = Grossziel.objects.count()
        self.prot.helden = Wochenauswertung.objects.filter(held_der_woche=True).count()
