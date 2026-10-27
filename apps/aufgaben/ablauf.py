"""Kinderablauf (AP12): Interesse, Konflikt, Zuteilung, Meldung, Bestätigung, Sonderpunkte,
Korrektur. Öffentlich über ``aufgaben.services``.

Regeln:

- Jeder Statuswechsel über ``zustand.uebergang`` (zentrale Tabelle, bedingtes Update).
- Jede Funktion ist eine Transaktion (SQLite ``BEGIN IMMEDIATE``): parallele Klicks laufen
  nacheinander, der zweite scheitert am bedingten Update (``UngueltigerUebergang``).
- Punkte genau einmal: Idempotenz-Schlüssel je Instanz (``aufgabe:<id>:basis``,
  ``aufgabe:<id>:serienbonus`` (AP21, über Hook), ``aufgabe:<id>:sonderpunkte``); Korrektur =
  Gegenbuchung aller drei (K2).
- K1: Bezugsdatum der Buchungen und der Aktivität = Meldedatum (``gemeldet_am``, lokal).
- K10: Limit pro Zeitraum je Kind und Aufgabe, geprüft beim Interesse.
- K11: Bei Konflikt läuft keine Frist; sie startet mit der Zuteilung durch die Eltern.
- Nachweis-Inhalte (Texte, AP13: Fotos) werden beim Abschluss gelöscht, nie ins Audit/Ereignis.

Erweiterungspunkte (Hooks, laufen in der Transaktion des Vorgangs):

- ``erledigung_hook_registrieren(f)``: ``f(erledigung: Erledigung)`` nach jeder Bestätigung
  (auch Vertrauen). Phase 2: Aktivität erfassen, AP21: Serienbonus buchen.
- ``storno_hook_registrieren(f)``: ``f(instanz, kind, von)`` nach einer Korrektur.
- ``nachweis_speicher_registrieren(f)``: ``f(meldung, fotos, neu=bool)`` beim Melden/Antworten
  (AP13); ``neu`` = Meldung entsteht gerade (Reste gleicher ID entfernen).
- ``nachweis_loescher_registrieren(f)``: ``f(meldung)`` beim Abschluss einer Meldung (AP13).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte
from apps.spielregeln import selectors as spielregeln

from . import events, schluessel
from .instanzen import reservierung_frist
from .models import (
    INTERESSE_LAUFEND,
    MELDUNG_LAUFEND,
    AufgabenInstanz,
    Freigabeart,
    InstanzStatus,
    Interesse,
    InteresseStatus,
    Meldung,
    MeldungStatus,
    Status,
)
from .zustand import AblaufFehler, UngueltigerUebergang, uebergang

S = InstanzStatus
I = InteresseStatus  # noqa: E741

MELDUNG_TEXT_MAX = 1000
RUECKFRAGE_MAX = 300
BEGRUENDUNG_MAX = 200
QUELLE = "aufgaben"


class LimitErreicht(AblaufFehler):
    """K10: Limit pro Zeitraum für dieses Kind und diese Aufgabe erreicht."""


class NichtErlaubt(AblaufFehler):
    """Die Person darf diese Aktion an dieser Instanz nicht ausführen."""


# --- Hooks ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Erledigung:
    """Fakt "Aufgabe erledigt und bestätigt" (Phase 2: Aktivität, AP21: Serienbonus)."""

    instanz: AufgabenInstanz
    kind: object
    bezugsdatum: date  # K1: Meldedatum (lokal)
    gemeldet_am: datetime
    bestaetigt_am: datetime
    punkte: int
    buchung: object  # punkte.Buchung (Basis)
    von: object | None  # Elternteil; bei Vertrauen das Kind
    vertrauen: bool


_erledigung_hooks: list[Callable] = []
_storno_hooks: list[Callable] = []
_nachweis_speicher: list[Callable] = []
_nachweis_loescher: list[Callable] = []


def _registrieren(liste, funktion):
    if funktion not in liste:
        liste.append(funktion)
    return funktion


def erledigung_hook_registrieren(funktion):
    return _registrieren(_erledigung_hooks, funktion)


def storno_hook_registrieren(funktion):
    return _registrieren(_storno_hooks, funktion)


def nachweis_speicher_registrieren(funktion):
    return _registrieren(_nachweis_speicher, funktion)


def nachweis_loescher_registrieren(funktion):
    return _registrieren(_nachweis_loescher, funktion)


# --- Hilfen -----------------------------------------------------------------------------------


def _laden(instanz) -> AufgabenInstanz:
    """Frischer Stand innerhalb der Transaktion (Schreibsperre ist ab BEGIN gehalten)."""
    return AufgabenInstanz.objects.select_related("aufgabe", "kind").get(pk=instanz.pk)


def _daten(instanz, **extra) -> dict:
    return {
        "instanz_id": instanz.pk,
        "aufgabe_id": instanz.aufgabe_id,
        "aufgabe": instanz.titel_snapshot,
        "punkte": instanz.punkte_snapshot,
        **extra,
    }


def _protokoll(aktion, instanz, *, akteur, kind=None, **details):
    audit.protokollieren(
        aktion,
        akteur=akteur,
        objekt=instanz,
        kind=kind if kind is not None else instanz.kind,
        details={"titel": instanz.titel_snapshot, **details},
    )


def _text(wert, grenze, name=None) -> str:
    name = name or _("Text")
    wert = (wert or "").strip()
    if len(wert) > grenze:
        raise AblaufFehler(
            _("%(name)s ist zu lang (höchstens %(grenze)s Zeichen).")
            % {"name": name, "grenze": grenze}
        )
    return wert


def _ist_kind(kind):
    if getattr(kind, "rolle", None) != "kind":
        raise NichtErlaubt(_("Nur Kinder können Aufgaben übernehmen."))


def _ist_eltern(von):
    if getattr(von, "rolle", None) != "eltern":
        raise NichtErlaubt(_("Nur Eltern können das entscheiden."))


def _sichtbar_fuer(instanz, kind, jetzt) -> None:
    aufgabe = instanz.aufgabe
    if aufgabe.status != Status.AKTIV:
        raise AblaufFehler(_("Diese Aufgabe ist gerade pausiert oder beendet."))
    if aufgabe.zugewiesen_an_id and aufgabe.zugewiesen_an_id != kind.pk:
        raise NichtErlaubt(_("Diese Aufgabe ist für ein anderes Kind."))
    if instanz.fenster_ende is not None and instanz.fenster_ende <= jetzt:
        raise AblaufFehler(_("Die Zeit für diese Aufgabe ist vorbei."))


def _interessen(instanz, *status):
    return Interesse.objects.filter(instanz=instanz, status__in=status or INTERESSE_LAUFEND)


def _interesse_setzen(qs, status, *, von=None, jetzt):
    return qs.update(status=status, entschieden_von=von, geaendert_am=jetzt)


def _offene_meldung(instanz) -> Meldung:
    meldung = Meldung.objects.filter(instanz=instanz, status__in=MELDUNG_LAUFEND).first()
    if meldung is None:  # pragma: no cover - Konsistenz: gemeldet ohne Meldung
        raise UngueltigerUebergang(_("Zu dieser Aufgabe gibt es keine offene Meldung."))
    return meldung


# --- Limit pro Zeitraum (K10) -----------------------------------------------------------------


def zeitraum(art: str, jetzt: datetime, tz=None) -> tuple[datetime, datetime]:
    """Laufender Zeitraum (``tag``/``woche``/``monat``) als halboffenes UTC-Intervall."""
    tz = tz or zeit.zeitzone()
    heute = zeit.heute(jetzt, tz)
    if art == "tag":
        return zeit.tag_intervall(heute, tz)
    if art == "woche":
        return zeit.IsoWoche.von(heute).intervall(tz)
    if art == "monat":
        erster = heute.replace(day=1)
        naechster = (erster + timedelta(days=32)).replace(day=1)
        return zeit.tag_beginn(erster, tz), zeit.tag_beginn(naechster, tz)
    raise ValueError(f"Unbekannter Zeitraum '{art}'")


def limit_stand(aufgabe, kind, *, jetzt=None) -> tuple[int, int] | None:
    """(genutzt, erlaubt) im laufenden Zeitraum oder ``None`` ohne Limit.

    Genutzt = laufende Übernahmen dieses Kindes (Interesse aktiv/zugeteilt, Instanz noch nicht
    abgeschlossen) + bestätigte Instanzen mit Meldedatum (K1) im Zeitraum. Abgelehnte,
    stornierte, abgelaufene und zurückgegebene zählen nicht (keine Strafe).
    """
    if not aufgabe.limit_anzahl or not aufgabe.limit_zeitraum:
        return None
    jetzt = jetzt or zeit.jetzt()
    beginn, ende = zeitraum(aufgabe.limit_zeitraum, jetzt)
    laufend = Interesse.objects.filter(
        kind=kind,
        status__in=INTERESSE_LAUFEND,
        instanz__aufgabe=aufgabe,
        instanz__status__in=(S.RESERVIERT, S.KONFLIKT, S.GEMELDET, S.RUECKFRAGE),
    ).count()
    erledigt = AufgabenInstanz.objects.filter(
        aufgabe=aufgabe,
        kind=kind,
        status=S.BESTAETIGT,
        gemeldet_am__gte=beginn,
        gemeldet_am__lt=ende,
    ).count()
    return laufend + erledigt, aufgabe.limit_anzahl


_ZEITRAUM_TEXT = {
    "tag": gettext_lazy("pro Tag"),
    "woche": gettext_lazy("pro Woche"),
    "monat": gettext_lazy("pro Monat"),
}


def _limit_pruefen(aufgabe, kind, jetzt):
    stand = limit_stand(aufgabe, kind, jetzt=jetzt)
    if stand is not None and stand[0] >= stand[1]:
        raise LimitErreicht(
            _("„%(titel)s“ geht höchstens %(n)s× %(zeitraum)s. Such dir eine andere Aufgabe aus!")
            % {
                "titel": aufgabe.titel,
                "n": stand[1],
                "zeitraum": _ZEITRAUM_TEXT[aufgabe.limit_zeitraum],
            }
        )


# --- Kind: Interesse, Rückgabe ----------------------------------------------------------------


@transaction.atomic
def interesse_zeigen(instanz, kind, *, jetzt=None) -> AufgabenInstanz:
    """Kind wählt eine Aufgabe.

    - ``offen`` -> ``reserviert`` (Frist ab jetzt, E22).
    - ``reserviert`` (anderes Kind) -> ``konflikt``, wenn ``aufgaben.mitbewerben_erlaubt``:
      Frist stoppt, die Eltern teilen zu (K11).
    - ``konflikt`` -> bleibt, weiteres Interesse.
    """
    jetzt = jetzt or zeit.jetzt()
    _ist_kind(kind)
    instanz = _laden(instanz)
    _sichtbar_fuer(instanz, kind, jetzt)
    if _interessen(instanz).filter(kind=kind).exists():
        raise AblaufFehler(_("Du hast diese Aufgabe schon gewählt."))
    _limit_pruefen(instanz.aufgabe, kind, jetzt)

    if instanz.status == S.OFFEN:
        uebergang(
            instanz,
            S.RESERVIERT,
            kind=kind,
            reserviert_bis=reservierung_frist(instanz, jetzt),
            erinnert_am=None,
        )
        Interesse.objects.create(
            instanz=instanz, kind=kind, status=I.ZUGETEILT, erstellt_am=jetzt, geaendert_am=jetzt
        )
        ereignisse.veroeffentlichen(
            events.INTERESSE,
            kind=kind,
            akteur=kind,
            daten=_daten(instanz, reserviert_bis=instanz.reserviert_bis.isoformat()),
        )
        _protokoll("aufgabe.interesse", instanz, akteur=kind, ergebnis="reserviert")
        return instanz

    if instanz.status in (S.RESERVIERT, S.KONFLIKT) and einstellungen.wert(
        "aufgaben.mitbewerben_erlaubt"
    ):
        if instanz.status == S.RESERVIERT:
            uebergang(
                instanz,
                S.KONFLIKT,
                bedingung={"kind": instanz.kind},
                kind=None,
                reserviert_bis=None,
                erinnert_am=None,
            )
            _interesse_setzen(_interessen(instanz, I.ZUGETEILT), I.AKTIV, jetzt=jetzt)
        Interesse.objects.create(
            instanz=instanz, kind=kind, status=I.AKTIV, erstellt_am=jetzt, geaendert_am=jetzt
        )
        namen = [i.kind.anzeigename for i in _interessen(instanz, I.AKTIV).select_related("kind")]
        ereignisse.veroeffentlichen(
            events.KONFLIKT,
            kind=kind,
            akteur=kind,
            daten=_daten(instanz, kinder=", ".join(namen)),
        )
        _protokoll("aufgabe.interesse", instanz, akteur=kind, kind=kind, ergebnis="konflikt")
        return instanz

    raise UngueltigerUebergang(_("Diese Aufgabe ist nicht mehr frei."))


@transaction.atomic
def zurueckgeben(instanz, kind, *, jetzt=None) -> AufgabenInstanz:
    """Kind gibt eine reservierte Aufgabe zurück (-> ``offen``) bzw. zieht im Konflikt sein
    Interesse zurück (bleibt nur ein Kind übrig, ist sie für dieses reserviert, Frist ab jetzt).
    """
    jetzt = jetzt or zeit.jetzt()
    _ist_kind(kind)
    instanz = _laden(instanz)
    eigenes = _interessen(instanz).filter(kind=kind)
    if not eigenes.exists():
        raise NichtErlaubt(_("Diese Aufgabe hast du nicht gewählt."))

    if instanz.status == S.RESERVIERT:
        uebergang(
            instanz,
            S.OFFEN,
            bedingung={"kind": kind},
            kind=None,
            reserviert_bis=None,
            erinnert_am=None,
        )
        _interesse_setzen(eigenes, I.ZURUECKGEZOGEN, jetzt=jetzt)
        ereignisse.veroeffentlichen(
            events.ZURUECKGEGEBEN, kind=kind, akteur=kind, daten=_daten(instanz)
        )
        _protokoll("aufgabe.zurueckgegeben", instanz, akteur=kind, kind=kind)
        return instanz

    if instanz.status == S.KONFLIKT:
        _interesse_setzen(eigenes, I.ZURUECKGEZOGEN, jetzt=jetzt)
        _protokoll("aufgabe.zurueckgegeben", instanz, akteur=kind, kind=kind)
        uebrig = list(_interessen(instanz, I.AKTIV).select_related("kind"))
        if len(uebrig) == 1:
            _reservieren_nach_konflikt(instanz, uebrig[0], von=None, jetzt=jetzt)
        return instanz

    raise UngueltigerUebergang(_("Diese Aufgabe kannst du nicht mehr zurückgeben."))


def _reservieren_nach_konflikt(instanz, interesse, *, von, jetzt):
    """Konflikt -> reserviert für ``interesse.kind``; K11: Frist startet jetzt."""
    gewinner = interesse.kind
    uebergang(
        instanz,
        S.RESERVIERT,
        kind=gewinner,
        reserviert_bis=reservierung_frist(instanz, jetzt),
        erinnert_am=None,
    )
    _interesse_setzen(Interesse.objects.filter(pk=interesse.pk), I.ZUGETEILT, von=von, jetzt=jetzt)
    verlierer = list(_interessen(instanz, I.AKTIV).select_related("kind"))
    _interesse_setzen(_interessen(instanz, I.AKTIV), I.VERDRAENGT, von=von, jetzt=jetzt)
    daten = _daten(instanz, reserviert_bis=instanz.reserviert_bis.isoformat())
    ereignisse.veroeffentlichen(events.ZUGETEILT, kind=gewinner, akteur=von, daten=daten)
    for i in verlierer:
        ereignisse.veroeffentlichen(events.VERGEBEN, kind=i.kind, akteur=von, daten=_daten(instanz))
    return instanz


def interesse_abgelaufen(instanz, kind) -> None:
    """Hook für ``reservierungen_pruefen``: Interesse des Inhabers -> ``abgelaufen``."""
    _interesse_setzen(
        _interessen(instanz, I.ZUGETEILT).filter(kind=kind), I.ABGELAUFEN, jetzt=zeit.jetzt()
    )


# --- Eltern: Zuteilen, Lösen ------------------------------------------------------------------


@transaction.atomic
def zuteilen(instanz, kind, *, von, jetzt=None) -> AufgabenInstanz:
    """Konflikt: Eltern teilen einem der Interessenten zu (die anderen: "vergeben")."""
    jetzt = jetzt or zeit.jetzt()
    _ist_eltern(von)
    instanz = _laden(instanz)
    if instanz.status != S.KONFLIKT:
        raise UngueltigerUebergang(_("Hier gibt es nichts mehr zuzuteilen."))
    interesse = _interessen(instanz, I.AKTIV).filter(kind=kind).select_related("kind").first()
    if interesse is None:
        raise AblaufFehler(_("Dieses Kind hat die Aufgabe nicht gewählt."))
    _reservieren_nach_konflikt(instanz, interesse, von=von, jetzt=jetzt)
    _protokoll("aufgabe.zugeteilt", instanz, akteur=von, kind=kind)
    return instanz


@transaction.atomic
def reservierung_loesen(instanz, *, von, jetzt=None) -> AufgabenInstanz:
    """Eltern lösen eine Reservierung oder einen Konflikt: die Aufgabe ist wieder frei."""
    jetzt = jetzt or zeit.jetzt()
    _ist_eltern(von)
    instanz = _laden(instanz)
    if instanz.status not in (S.RESERVIERT, S.KONFLIKT):
        raise UngueltigerUebergang(_("Diese Aufgabe ist nicht (mehr) reserviert."))
    betroffene = [i.kind for i in _interessen(instanz).select_related("kind")]
    uebergang(instanz, S.OFFEN, kind=None, reserviert_bis=None, erinnert_am=None)
    _interesse_setzen(_interessen(instanz), I.VERDRAENGT, von=von, jetzt=jetzt)
    for kind in betroffene:
        ereignisse.veroeffentlichen(events.GELOEST, kind=kind, akteur=von, daten=_daten(instanz))
    _protokoll(
        "aufgabe.reservierung_geloest",
        instanz,
        akteur=von,
        kind=betroffene[0] if len(betroffene) == 1 else None,
        kinder=[str(k.pk) for k in betroffene],
    )
    return instanz


# --- Kind: Melden, Antworten ------------------------------------------------------------------


def _nachweise_speichern(meldung, fotos, *, neu=False):
    """Fotos speichern. ``neu`` (Meldung entsteht gerade): Speicher entfernen zuerst Reste einer
    zurückgerollten Meldung mit derselben ID (Review AP19, B-04), auch ganz ohne Fotos.

    Aufrufer rufen das als **letzten** Schritt ihrer Transaktion auf: Was danach scheitern
    könnte (Ereignis, Audit), läuft vorher; Dateien entstehen erst, wenn sonst alles steht.
    """
    if not fotos and not neu:
        return
    if fotos and not _nachweis_speicher:
        raise AblaufFehler(_("Fotos können noch nicht hochgeladen werden."))
    for speicher in _nachweis_speicher:
        speicher(meldung, fotos, neu=neu)


@transaction.atomic
def erledigt_melden(instanz, kind, *, text="", fotos: Sequence = (), jetzt=None):
    """Kind meldet "erledigt".

    - Vertrauen: sofort ``bestaetigt``, Punkte gebucht (Eltern können korrigieren, K2). Ein
      Text wird nicht gespeichert (es gibt niemanden, der ihn bestätigt).
    - Eltern bestätigen / Nachweis: ``gemeldet``; Nachweis verlangt Text oder Foto (AP13).
    """
    jetzt = jetzt or zeit.jetzt()
    _ist_kind(kind)
    text = _text(text, MELDUNG_TEXT_MAX)
    instanz = _laden(instanz)
    if instanz.status not in (S.RESERVIERT, S.NACHBESSERN):
        raise UngueltigerUebergang(_("Diese Aufgabe ist nicht (mehr) für dich reserviert."))
    if (
        instanz.status == S.NACHBESSERN
        and instanz.nachbessern_bis
        and instanz.nachbessern_bis <= jetzt
    ):
        raise UngueltigerUebergang(_("Die Frist zum Nachbessern ist vorbei."))
    if instanz.kind_id != kind.pk:
        raise NichtErlaubt(_("Diese Aufgabe ist für ein anderes Kind reserviert."))
    gemeldet_am = instanz.gemeldet_am or jetzt

    nachbessern = instanz.status == S.NACHBESSERN  # einmal Bestätigung, auch bei Vertrauen
    if instanz.freigabeart_snapshot == Freigabeart.VERTRAUEN and not nachbessern:
        uebergang(
            instanz,
            S.BESTAETIGT,
            bedingung={"kind": kind},
            gemeldet_am=gemeldet_am,
            bestaetigt_am=jetzt,
            bestaetigt_von=None,
            abgeschlossen_am=jetzt,
            reserviert_bis=None,
        )
        meldung = Meldung.objects.create(
            instanz=instanz,
            kind=kind,
            gemeldet_am=jetzt,
            status=MeldungStatus.BESTAETIGT,
            entschieden_am=jetzt,
        )
        buchung = _basis_buchen(instanz, von=kind)
        ereignisse.veroeffentlichen(events.VERTRAUEN, kind=kind, akteur=kind, daten=_daten(instanz))
        _erledigt(instanz, buchung, von=kind, vertrauen=True)
        _protokoll("aufgabe.vertrauen", instanz, akteur=kind, punkte=instanz.punkte_snapshot)
        _nachweise_speichern(meldung, (), neu=True)  # Fotos bei Vertrauen nie speichern
        return instanz

    if instanz.freigabeart_snapshot == Freigabeart.NACHWEIS and not (text or fotos):
        raise AblaufFehler(_("Schreib kurz, was du gemacht hast, oder füge ein Foto hinzu."))
    uebergang(
        instanz,
        S.GEMELDET,
        bedingung={"kind": kind},
        gemeldet_am=gemeldet_am,
        reserviert_bis=None,
        nachbessern_bis=None,
    )
    meldung = Meldung.objects.create(
        instanz=instanz, kind=kind, gemeldet_am=jetzt, text=text, status=MeldungStatus.OFFEN
    )
    ereignisse.veroeffentlichen(
        events.GEMELDET,
        kind=kind,
        akteur=kind,
        daten=_daten(instanz, mit_text=bool(text), fotos=len(fotos)),
    )
    _protokoll("aufgabe.gemeldet", instanz, akteur=kind, mit_text=bool(text), fotos=len(fotos))
    _nachweise_speichern(meldung, fotos, neu=True)
    return instanz


@transaction.atomic
def rueckfrage_beantworten(instanz, kind, *, text="", fotos: Sequence = (), jetzt=None):
    """Kind antwortet auf eine Rückfrage: ``rueckfrage`` -> ``gemeldet``."""
    jetzt = jetzt or zeit.jetzt()
    _ist_kind(kind)
    text = _text(text, MELDUNG_TEXT_MAX, "Antwort")
    instanz = _laden(instanz)
    if instanz.kind_id != kind.pk:
        raise NichtErlaubt(_("Das ist nicht deine Aufgabe."))
    uebergang(instanz, S.GEMELDET, von=S.RUECKFRAGE, bedingung={"kind": kind})
    meldung = _offene_meldung(instanz)
    meldung.status = MeldungStatus.OFFEN
    meldung.antwort_text = text
    meldung.save(update_fields=["status", "antwort_text"])
    ereignisse.veroeffentlichen(
        events.ANTWORT,
        kind=kind,
        akteur=kind,
        daten=_daten(instanz, mit_text=bool(text), fotos=len(fotos)),
    )
    _protokoll("aufgabe.antwort", instanz, akteur=kind, mit_text=bool(text), fotos=len(fotos))
    _nachweise_speichern(meldung, fotos)
    return instanz


# --- Eltern: Bestätigen, Ablehnen, Rückfrage --------------------------------------------------


def _xp_bezugsdatum(instanz) -> date:
    """Bezugsdatum der Punkte (K1, ARCHITECTURE 7.2): Meldedatum; wird erst nach dem
    Wochenabschluss (Puffer) bestätigt, der Tag der Bestätigung – wie die Aktivität. So landen
    XP (Familienziel, Held der Woche, Wochen-XP) und Aktivität in derselben Woche (Review AP31)."""
    return spielregeln.wirksames_datum(
        zeit.heute(instanz.gemeldet_am), instanz.bestaetigt_am or zeit.jetzt()
    )


def _basis_buchen(instanz, *, von):
    """Basis-Punkte, genau einmal je Instanz; Bezugsdatum siehe ``_xp_bezugsdatum``."""
    return punkte.buchen(
        instanz.kind,
        punkte.Art.AUFGABE,
        instanz.punkte_snapshot,
        schluessel=schluessel.buchung(instanz.pk, "basis", instanz.nachbessern_anzahl),
        quelle_modul=QUELLE,
        bezugsdatum=_xp_bezugsdatum(instanz),
        referenz=instanz,
        von=von,
    )


def _erledigt(instanz, buchung, *, von, vertrauen):
    erledigung = Erledigung(
        instanz=instanz,
        kind=instanz.kind,
        bezugsdatum=zeit.heute(instanz.gemeldet_am),
        gemeldet_am=instanz.gemeldet_am,
        bestaetigt_am=instanz.bestaetigt_am,
        punkte=instanz.punkte_snapshot,
        buchung=buchung,
        von=von,
        vertrauen=vertrauen,
    )
    ereignisse.veroeffentlichen(
        events.ERLEDIGT,
        kind=instanz.kind,
        akteur=von,
        daten=_daten(
            instanz,
            bezugsdatum=erledigung.bezugsdatum.isoformat(),
            gemeldet_am=instanz.gemeldet_am.isoformat(),
            bestaetigt_am=instanz.bestaetigt_am.isoformat(),
            vertrauen=vertrauen,
        ),
        schluessel=f"{events.ERLEDIGT}:{instanz.pk}",
    )
    for hook in _erledigung_hooks:
        hook(erledigung)
    return erledigung


def _meldung_abschliessen(instanz, status, *, von, jetzt):
    """Meldung entscheiden und Nachweis-Inhalte löschen (SPEC 5.4, ARCHITECTURE 9)."""
    meldung = _offene_meldung(instanz)
    meldung.status = status
    meldung.entschieden_von = von
    meldung.entschieden_am = jetzt
    hatte_inhalt = bool(meldung.text or meldung.antwort_text or meldung.rueckfrage_text)
    meldung.text = meldung.antwort_text = meldung.rueckfrage_text = ""
    meldung.nachweis_geloescht_am = jetzt
    meldung.save(
        update_fields=[
            "status",
            "entschieden_von",
            "entschieden_am",
            "text",
            "antwort_text",
            "rueckfrage_text",
            "nachweis_geloescht_am",
        ]
    )
    for loescher in _nachweis_loescher:
        loescher(meldung)
    audit.protokollieren(
        "aufgabe.nachweis_geloescht",
        akteur=von,
        objekt=meldung,
        kind=meldung.kind,
        details={"titel": instanz.titel_snapshot, "hatte_text": hatte_inhalt},
    )
    return meldung


@transaction.atomic
def bestaetigen(instanz, *, von, sonderpunkte=0, begruendung="", jetzt=None):
    """Eltern bestätigen (``gemeldet``/``rueckfrage`` -> ``bestaetigt``): Punkte genau einmal,
    optional Sonderpunkte (mit Begründung, Deckel), Nachweis gelöscht."""
    jetzt = jetzt or zeit.jetzt()
    _ist_eltern(von)
    instanz = _laden(instanz)
    if instanz.status not in (S.GEMELDET, S.RUECKFRAGE):
        raise UngueltigerUebergang(_("Diese Meldung ist schon entschieden."))
    if sonderpunkte:
        _sonderpunkte_pruefen(instanz, sonderpunkte, begruendung)
    uebergang(
        instanz,
        S.BESTAETIGT,
        von=(S.GEMELDET, S.RUECKFRAGE),
        bestaetigt_am=jetzt,
        bestaetigt_von=von,
        abgeschlossen_am=jetzt,
    )
    _meldung_abschliessen(instanz, MeldungStatus.BESTAETIGT, von=von, jetzt=jetzt)
    buchung = _basis_buchen(instanz, von=von)
    ereignisse.veroeffentlichen(
        events.BESTAETIGT, kind=instanz.kind, akteur=von, daten=_daten(instanz)
    )
    _erledigt(instanz, buchung, von=von, vertrauen=False)
    _protokoll("aufgabe.bestaetigt", instanz, akteur=von, punkte=instanz.punkte_snapshot)
    if sonderpunkte:
        _sonderpunkte_buchen(instanz, sonderpunkte, begruendung, von=von)
    return instanz


@transaction.atomic
def ablehnen(instanz, *, von, begruendung="", jetzt=None):
    """Eltern lehnen ab (Endzustand, keine Punkte, keine Strafe); Nachweis gelöscht."""
    jetzt = jetzt or zeit.jetzt()
    _ist_eltern(von)
    begruendung = _text(begruendung, BEGRUENDUNG_MAX, _("Begründung"))
    instanz = _laden(instanz)
    uebergang(instanz, S.ABGELEHNT, von=(S.GEMELDET, S.RUECKFRAGE), abgeschlossen_am=jetzt)
    _meldung_abschliessen(instanz, MeldungStatus.ABGELEHNT, von=von, jetzt=jetzt)
    ereignisse.veroeffentlichen(
        events.ABGELEHNT,
        kind=instanz.kind,
        akteur=von,
        daten=_daten(instanz, begruendung=begruendung),
    )
    _protokoll("aufgabe.abgelehnt", instanz, akteur=von, begruendung=begruendung)
    return instanz


@transaction.atomic
def rueckfrage_stellen(instanz, *, von, text, jetzt=None):
    """Eltern fragen nach (``gemeldet`` -> ``rueckfrage``). Der Text ist Teil der Meldung und
    wird beim Abschluss gelöscht (nicht im Ereignis/Audit)."""
    _ist_eltern(von)
    text = _text(text, RUECKFRAGE_MAX, _("Rückfrage"))
    if not text:
        raise AblaufFehler(_("Bitte die Rückfrage eingeben."))
    instanz = _laden(instanz)
    uebergang(instanz, S.RUECKFRAGE, von=S.GEMELDET)
    meldung = _offene_meldung(instanz)
    meldung.status = MeldungStatus.RUECKFRAGE
    meldung.rueckfrage_text = text
    meldung.entschieden_von = von
    meldung.save(update_fields=["status", "rueckfrage_text", "entschieden_von"])
    ereignisse.veroeffentlichen(
        events.RUECKFRAGE, kind=instanz.kind, akteur=von, daten=_daten(instanz)
    )
    _protokoll("aufgabe.rueckfrage", instanz, akteur=von)
    return instanz


# --- Sonderpunkte -----------------------------------------------------------------------------


def sonderpunkte_deckel(instanz) -> int | None:
    """Höchste Sonderpunkte je Instanz oder ``None`` (kein Deckel).

    Eigener Wert der Aufgabe (``sonderpunkte_deckel_prozent``) gilt immer; sonst der globale
    Wert, wenn ``aufgaben.sonderpunkte_deckel_aktiv``. Aufgerundet (zugunsten des Kindes).
    """
    prozent = instanz.aufgabe.sonderpunkte_deckel_prozent
    if prozent is None:
        werte = einstellungen.werte(
            "aufgaben.sonderpunkte_deckel_aktiv", "aufgaben.sonderpunkte_deckel_prozent"
        )
        if not werte["aufgaben.sonderpunkte_deckel_aktiv"]:
            return None
        prozent = werte["aufgaben.sonderpunkte_deckel_prozent"]
    return math.ceil(instanz.punkte_snapshot * prozent / 100)


def _sonderpunkte_pruefen(instanz, punktzahl, begruendung):
    if isinstance(punktzahl, bool) or not isinstance(punktzahl, int) or punktzahl <= 0:
        raise AblaufFehler(_("Sonderpunkte: bitte eine ganze Zahl größer 0."))
    if not _text(begruendung, BEGRUENDUNG_MAX, _("Begründung")):
        raise AblaufFehler(_("Sonderpunkte brauchen eine kurze Begründung."))
    if instanz.sonderpunkte:
        raise AblaufFehler(_("Für diese Aufgabe gab es schon Sonderpunkte."))
    deckel = sonderpunkte_deckel(instanz)
    if deckel is not None and punktzahl > deckel:
        raise AblaufFehler(
            _("Höchstens %(deckel)s Sonderpunkte für diese Aufgabe.") % {"deckel": deckel}
        )


def _sonderpunkte_buchen(instanz, punktzahl, begruendung, *, von):
    begruendung = _text(begruendung, BEGRUENDUNG_MAX, _("Begründung"))
    if not AufgabenInstanz.objects.filter(
        pk=instanz.pk, status=S.BESTAETIGT, sonderpunkte=0
    ).update(sonderpunkte=punktzahl, sonderpunkte_begruendung=begruendung):
        raise UngueltigerUebergang(_("Für diese Aufgabe gab es schon Sonderpunkte."))
    instanz.sonderpunkte, instanz.sonderpunkte_begruendung = punktzahl, begruendung
    punkte.buchen(
        instanz.kind,
        punkte.Art.SONDERPUNKTE,
        punktzahl,
        schluessel=schluessel.buchung(instanz.pk, "sonderpunkte", instanz.nachbessern_anzahl),
        quelle_modul=QUELLE,
        bezugsdatum=_xp_bezugsdatum(instanz),
        referenz=instanz,
        begruendung=begruendung,
        von=von,
    )
    ereignisse.veroeffentlichen(
        events.SONDERPUNKTE,
        kind=instanz.kind,
        akteur=von,
        daten=_daten(instanz, punkte=punktzahl, begruendung=begruendung),
    )
    _protokoll(
        "aufgabe.sonderpunkte", instanz, akteur=von, punkte=punktzahl, begruendung=begruendung
    )


@transaction.atomic
def sonderpunkte_vergeben(instanz, punktzahl, begruendung, *, von):
    """Sonderpunkte nach der Bestätigung (einmal je Instanz, Deckel, Begründung Pflicht)."""
    _ist_eltern(von)
    instanz = _laden(instanz)
    if instanz.status != S.BESTAETIGT:
        raise UngueltigerUebergang(_("Sonderpunkte gibt es nur für bestätigte Aufgaben."))
    _sonderpunkte_pruefen(instanz, punktzahl, begruendung)
    _sonderpunkte_buchen(instanz, punktzahl, begruendung, von=von)
    return instanz


# --- Korrektur (K2) ---------------------------------------------------------------------------


@transaction.atomic
def korrigieren(instanz, *, von, begruendung, jetzt=None, nachbessern=False):
    """Nachträgliche Korrektur (v. a. Vertrauen): alle Punkte der Instanz (Basis + Serienbonus +
    Sonderpunkte) per Gegenbuchung zurück; mindert Guthaben und XP (K2).

    - Standard: ``bestaetigt`` -> ``storniert`` (endgültig).
    - ``nachbessern``: dieselbe Instanz geht als ``nachbessern`` zurück an das Kind (Frist
      ``nachbessern_bis``, Einstellung ``aufgaben.nachbessern_stunden``). Die nächste Meldung
      braucht Bestätigung; die Punkte werden mit neuen Schlüsseln (Runde +1) erneut gebucht."""
    jetzt = jetzt or zeit.jetzt()
    _ist_eltern(von)
    begruendung = _text(begruendung, BEGRUENDUNG_MAX, _("Begründung"))
    if not begruendung:
        raise AblaufFehler(_("Bitte kurz begründen, warum korrigiert wird."))
    instanz = _laden(instanz)
    runde = instanz.nachbessern_anzahl
    if nachbessern:
        uebergang(
            instanz,
            S.NACHBESSERN,
            von=S.BESTAETIGT,
            nachbessern_anzahl=runde + 1,
            nachbessern_grund=begruendung,
            nachbessern_bis=jetzt
            + timedelta(hours=einstellungen.wert("aufgaben.nachbessern_stunden")),
            gemeldet_am=None,
            bestaetigt_am=None,
            bestaetigt_von=None,
            abgeschlossen_am=None,
            geprueft_am=None,
            geprueft_von=None,
            reserviert_bis=None,
        )
    else:
        uebergang(instanz, S.STORNIERT, von=S.BESTAETIGT)
    abgezogen = 0
    for art in ("basis", "serienbonus", "sonderpunkte"):
        buchung = punkte_selectors.buchung_zu_schluessel(schluessel.buchung(instanz.pk, art, runde))
        if buchung is not None:
            storno = punkte.gegenbuchen(buchung, begruendung=begruendung, von=von)
            abgezogen -= storno.guthaben_delta
    ereignisse.veroeffentlichen(
        events.NACHBESSERN if nachbessern else events.KORRIGIERT,
        kind=instanz.kind,
        akteur=von,
        daten=_daten(instanz, punkte=abgezogen, begruendung=begruendung),
        **({"schluessel": f"{events.NACHBESSERN}:{instanz.pk}:{runde + 1}"} if nachbessern else {}),
    )
    instanz.nachbessern_anzahl = runde  # Hooks stornieren die Aktivität der alten Runde
    for hook in _storno_hooks:
        hook(instanz, instanz.kind, von)
    instanz.nachbessern_anzahl = runde + 1 if nachbessern else runde
    _protokoll(
        "aufgabe.nachbessern" if nachbessern else "aufgabe.korrigiert",
        instanz,
        akteur=von,
        punkte=abgezogen,
        begruendung=begruendung,
    )
    return instanz


@transaction.atomic
def nachbessern_pruefen(*, jetzt=None) -> dict:
    """Frist abgelaufen: ``nachbessern`` -> ``storniert`` (keine Punkte), Eltern werden informiert.
    Läuft im Job ``verfall_pruefen``."""
    jetzt = jetzt or zeit.jetzt()
    zaehler = {"nachbessern_abgelaufen": 0}
    faellige = AufgabenInstanz.objects.filter(status=S.NACHBESSERN, nachbessern_bis__lte=jetzt)
    for pk in list(faellige.values_list("pk", flat=True)):
        instanz = AufgabenInstanz.objects.select_related("aufgabe", "kind").get(pk=pk)
        try:
            uebergang(
                instanz,
                S.STORNIERT,
                von=S.NACHBESSERN,
                abgeschlossen_am=jetzt,
                nachbessern_bis=None,
            )
        except UngueltigerUebergang:
            continue
        ereignisse.veroeffentlichen(
            events.NACHBESSERN_ABGELAUFEN,
            kind=instanz.kind,
            daten=_daten(instanz),
            schluessel=f"{events.NACHBESSERN_ABGELAUFEN}:{instanz.pk}:{instanz.nachbessern_anzahl}",
        )
        _protokoll("aufgabe.nachbessern_abgelaufen", instanz, akteur=None)
        zaehler["nachbessern_abgelaufen"] += 1
    return zaehler


# --- Vertrauen prüfen (Eltern-Dashboard "Erledigt – kurz prüfen") ------------------------------


def zu_pruefen():
    """Vertrauens-Erledigungen, die noch niemand durchgesehen hat (neueste zuletzt)."""
    return (
        AufgabenInstanz.objects.filter(
            status=S.BESTAETIGT,
            freigabeart_snapshot=Freigabeart.VERTRAUEN,
            bestaetigt_von__isnull=True,
            geprueft_am__isnull=True,
        )
        .select_related("kind", "aufgabe")
        .order_by("bestaetigt_am", "pk")
    )


@transaction.atomic
def passt(instanz, *, von, jetzt=None):
    """ "Passt": als geprüft markieren, Punkte bleiben."""
    jetzt = jetzt or zeit.jetzt()
    _ist_eltern(von)
    instanz = _laden(instanz)
    treffer = AufgabenInstanz.objects.filter(
        pk=instanz.pk,
        status=S.BESTAETIGT,
        freigabeart_snapshot=Freigabeart.VERTRAUEN,
        geprueft_am__isnull=True,
    ).update(geprueft_am=jetzt, geprueft_von=von)
    if not treffer:
        raise UngueltigerUebergang(_("Diese Aufgabe ist schon geprüft oder wurde geändert."))
    _protokoll("aufgabe.geprueft", instanz, akteur=von)
    return instanz


@transaction.atomic
def alle_passen(*, von, jetzt=None):
    """ "Alle passen": jede offene Vertrauens-Erledigung als geprüft markieren. Gibt die Anzahl."""
    anzahl = 0
    for instanz in list(zu_pruefen()):
        try:
            passt(instanz, von=von, jetzt=jetzt)
            anzahl += 1
        except UngueltigerUebergang:
            continue
    return anzahl


# --- Lesen für Oberflächen (eigene Daten) -----------------------------------------------------


def kind_darf_sehen(instanz, kind) -> bool:
    """Kind sieht freie Instanzen (für alle oder ihm zugewiesen) und eigene."""
    if instanz.kind_id == kind.pk or _interessen(instanz).filter(kind=kind).exists():
        return True
    zugewiesen = instanz.aufgabe.zugewiesen_an_id
    return instanz.status in (S.OFFEN, S.RESERVIERT, S.KONFLIKT) and zugewiesen in (None, kind.pk)


def offene_interessen_q(kind) -> Q:
    return Q(interessen__kind=kind, interessen__status__in=INTERESSE_LAUFEND)
