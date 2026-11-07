"""Schnell-Knöpfe: Aufgaben mit Wiederholungsart "bei Bedarf" (SPEC Schnell-Knöpfe).

Eine solche Aufgabe schläft, bis jemand ihren Knopf drückt. Drei Modi:

- "Einer für alle" (``melden``, ``kind=None``): eine ungebundene Instanz bleibt offen für alle
  Kinder; jedes erlaubte aktive Kind bekommt eine Mitteilung ("{Aufgabe}: wer macht's?").
- "Jedes Kind" (``jedes``, nur Eltern): für **jedes** erlaubte aktive Kind eine eigene Instanz,
  direkt für dieses Kind reserviert. Kinder mit laufender Instanz (oder erreichtem Limit) werden
  übersprungen (Doppel-Schutz).
- "Bestimmtes Kind" / "Ich mach's" (``ich_machs``, ``kind`` gesetzt): die Instanz wird für dieses
  Kind reserviert (wie bei einem Kind, das die Aufgabe wählt: gleiche Regeln, Frist, Limit,
  Ereignis an die Eltern). Kinder drücken so nur für sich selbst.

Was "läuft schon" heißt, hängt vom Standard-Modus des Knopfs (``Aufgabe.schnellknopf_modus``)
ab: bei "einer" blockiert jede laufende Instanz alle weiteren Drücke, bei "jedes" nur die eigene
des Kindes (oder eine ungebundene).

Race-sicher: Transaktion mit Sperre auf der Aufgabe plus Teil-Uniques "höchstens eine laufende
ungebundene Instanz je Aufgabe" und "höchstens eine laufende je Aufgabe und Kind".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.konten import selectors as konten_selectors

from . import ablauf, events, knoepfe_start, wiederholung
from .models import (
    LAUFENDE_STATUS,
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    Kategorie,
    SchnellknopfModus,
    SchnellknopfWer,
    Status,
    Vorlage,
)
from .zustand import AblaufFehler

# Läuft noch: alles bis zum Endzustand (inkl. "zum Nachbessern")
OFFEN_STATUS = (*LAUFENDE_STATUS, InstanzStatus.NACHBESSERN)

# Drück-Modi (Audit-Detail ``modus`` und Formularwerte)
MELDEN = "melden"
JEDES = "jedes"
ICH_MACHS = "ich_machs"


@dataclass
class Druck:
    """Ergebnis von ``druecken``.

    ``instanz``: die neue (bei ``jedes``: erste neue) Instanz, sonst die schon laufende bzw.
    ``None``. ``neu``: es wurde mindestens eine Instanz angelegt. ``angelegt``: alle neuen
    Instanzen. ``uebersprungen``: ``(kind, grund)`` je Kind, das bei ``jedes`` nichts bekam.
    """

    instanz: AufgabenInstanz | None
    neu: bool
    angelegt: list[AufgabenInstanz] = field(default_factory=list)
    uebersprungen: list[tuple[object, str]] = field(default_factory=list)


def laufende_instanzen(aufgabe) -> list[AufgabenInstanz]:
    """Alle laufenden Instanzen der Aufgabe, neueste zuerst."""
    return list(
        AufgabenInstanz.objects.filter(aufgabe=aufgabe, status__in=OFFEN_STATUS)
        .select_related("kind")
        .order_by("-id")
    )


def _blockiert(aufgabe, kind, laufende) -> AufgabenInstanz | None:
    """Welche laufende Instanz verhindert einen Druck für ``kind`` (``None`` = alle Kinder)?"""
    if kind is not None and aufgabe.schnellknopf_modus == SchnellknopfModus.JEDES:
        return next((i for i in laufende if i.kind_id in (None, kind.pk)), None)
    return laufende[0] if laufende else None


def laufende_instanz(aufgabe, kind=None) -> AufgabenInstanz | None:
    """Laufende Instanz, die einen Druck blockiert (mit ``kind``: für dieses Kind)."""
    return _blockiert(aufgabe, kind, laufende_instanzen(aufgabe))


def darf_druecken(aufgabe, benutzer) -> bool:
    """``benutzer=None`` = Flur-Tablet (nur Kinder-Knöpfe)."""
    if aufgabe.schnellknopf_wer == SchnellknopfWer.ELTERN:
        return getattr(benutzer, "rolle", None) == "eltern"
    return True


def erlaubte_kinder(aufgabe):
    """Aktive Kinder, die die Aufgabe machen dürfen (``zugewiesen_an`` leer = alle)."""
    kinder = konten_selectors.aktive_kinder()
    if aufgabe.zugewiesen_an_id:
        kinder = kinder.filter(pk=aufgabe.zugewiesen_an_id)
    return kinder


def _pruefen(aufgabe, von, kind, modus):
    if not aufgabe.schnellknopf or aufgabe.status != Status.AKTIV:
        raise AblaufFehler(_("Dieser Knopf ist gerade nicht aktiv."))
    if not darf_druecken(aufgabe, von):
        raise ablauf.NichtErlaubt(_("Diesen Knopf dürfen nur Eltern drücken."))
    if modus == JEDES and getattr(von, "rolle", None) != "eltern":
        raise ablauf.NichtErlaubt(_("„Jedes Kind“ dürfen nur Eltern wählen."))
    if kind is None:
        if getattr(von, "rolle", None) == "kind" and aufgabe.zugewiesen_an_id not in (
            None,
            von.pk,
        ):
            raise ablauf.NichtErlaubt(_("Diese Aufgabe ist für ein anderes Kind."))
        return
    if getattr(kind, "rolle", None) != "kind" or not kind.aktiv:
        raise ablauf.NichtErlaubt(_("Nur Kinder können Aufgaben übernehmen."))
    if getattr(von, "rolle", None) == "kind" and von.pk != kind.pk:
        raise ablauf.NichtErlaubt(_("Du kannst nur für dich selbst übernehmen."))
    if aufgabe.zugewiesen_an_id and aufgabe.zugewiesen_an_id != kind.pk:
        raise ablauf.NichtErlaubt(_("Diese Aufgabe ist für ein anderes Kind."))


def _anlegen(aufgabe, jetzt) -> AufgabenInstanz | None:
    heute = zeit.heute(jetzt)
    try:
        with transaction.atomic():
            return AufgabenInstanz.objects.create(
                aufgabe=aufgabe,
                faellig_am=heute,
                fenster_start=zeit.tag_beginn(heute),
                titel_snapshot=aufgabe.titel,
                punkte_snapshot=aufgabe.punkte,
                freigabeart_snapshot=aufgabe.freigabeart,
            )
    except IntegrityError:
        return None


def _jedes(aufgabe, von, jetzt) -> Druck:
    """Modus "Jedes Kind": je erlaubtem aktivem Kind eine Instanz anlegen und sofort binden.

    Sequenziell und je Kind in einem Savepoint: scheitert die Reservierung (Limit ...), wird die
    eben angelegte Instanz mit verworfen und das Kind übersprungen. Eine ungebundene laufende
    Instanz (Rest eines Rückgebens) gehört niemandem und blockiert das Anlegen (Teil-Unique).
    """
    laufende = laufende_instanzen(aufgabe)
    ergebnis = Druck(instanz=None, neu=False)
    for kind in erlaubte_kinder(aufgabe):
        if any(i.kind_id in (None, kind.pk) for i in laufende):
            ergebnis.uebersprungen.append((kind, _("läuft schon")))
            continue
        try:
            with transaction.atomic():
                instanz = _anlegen(aufgabe, jetzt)
                if instanz is None:  # parallel von jemand anderem angelegt
                    raise AblaufFehler(_("läuft schon"))
                instanz = ablauf.interesse_zeigen(instanz, kind, jetzt=jetzt)
        except AblaufFehler as fehler:
            ergebnis.uebersprungen.append((kind, str(fehler)))
            continue
        ergebnis.angelegt.append(instanz)
        _protokoll(instanz, von, kind, JEDES)
    ergebnis.neu = bool(ergebnis.angelegt)
    ergebnis.instanz = ergebnis.angelegt[0] if ergebnis.angelegt else None
    return ergebnis


def _protokoll(instanz, von, kind, modus):
    audit.protokollieren(
        "aufgabe.schnellknopf",
        akteur=von,
        objekt=instanz,
        kind=kind,
        details={"titel": instanz.titel_snapshot, "modus": modus},
    )


@transaction.atomic
def druecken(aufgabe, *, von=None, kind=None, modus=None, jetzt=None) -> Druck:
    """Knopf drücken. ``Druck.neu`` ist ``False``, wenn schon eine Instanz läuft.

    ``von``: der drückende Benutzer (``None`` = Flur-Tablet, dort ohne Anmeldung).
    ``modus``: ``melden`` | ``jedes`` | ``ich_machs``; ohne Angabe ``ich_machs`` mit ``kind``,
    sonst ``melden``. ``kind``: Kind für ``ich_machs`` (bei ``melden``/``jedes`` ignoriert).
    """
    jetzt = jetzt or zeit.jetzt()
    modus = modus or (ICH_MACHS if kind is not None else MELDEN)
    if modus == ICH_MACHS and kind is None:
        raise AblaufFehler(_("Bitte ein Kind wählen."))
    if modus != ICH_MACHS:
        kind = None
    aufgabe = Aufgabe.objects.select_for_update().get(pk=aufgabe.pk)
    _pruefen(aufgabe, von, kind, modus)
    if modus == JEDES:
        return _jedes(aufgabe, von, jetzt)

    vorhandene = laufende_instanz(aufgabe, kind)
    if vorhandene is not None:
        return Druck(instanz=vorhandene, neu=False)
    instanz = _anlegen(aufgabe, jetzt)
    if instanz is None:  # parallel von jemand anderem angelegt
        return Druck(instanz=laufende_instanz(aufgabe, kind), neu=False)

    if kind is not None:
        instanz = ablauf.interesse_zeigen(instanz, kind, jetzt=jetzt)
    else:
        daten = {
            "instanz_id": instanz.pk,
            "aufgabe_id": aufgabe.pk,
            "aufgabe": instanz.titel_snapshot,
            "punkte": instanz.punkte_snapshot,
        }
        for empfaenger in erlaubte_kinder(aufgabe):
            if von is not None and empfaenger.pk == von.pk:
                continue  # wer drückt, weiß es schon
            ereignisse.veroeffentlichen(
                events.SCHNELLKNOPF,
                kind=empfaenger,
                akteur=von,
                daten=daten,
                schluessel=f"{events.SCHNELLKNOPF}:{instanz.pk}:{empfaenger.pk}",
            )
    _protokoll(instanz, von, kind, modus)
    return Druck(instanz=instanz, neu=True, angelegt=[instanz])


def knoepfe(benutzer=None, *, nur_kinder_knoepfe=False):
    """Aktive Schnell-Knöpfe für Kacheln mit Laufzustand.

    Je Knopf: ``laufende`` (alle laufenden Instanzen), ``laufend_anzahl``/``kinder_anzahl``
    (wie viele der erlaubten Kinder dran sind) und ``laeuft`` (die Instanz, die weitere Drücke
    blockiert, sonst ``None``). Bei "jedes" gilt für ein Kind nur die eigene (oder ungebundene)
    Instanz; für Eltern und Tablet läuft der Knopf erst, wenn **alle** erlaubten Kinder dran
    sind.

    ``benutzer``: Kind -> nur Knöpfe "für alle" und für es freigegebene Aufgaben.
    ``nur_kinder_knoepfe``: Flur-Tablet (nur Knöpfe "für alle").
    """
    qs = Aufgabe.objects.filter(
        status=Status.AKTIV, wiederholungsart=wiederholung.BEI_BEDARF
    ).select_related("kategorie")
    ist_kind = getattr(benutzer, "rolle", None) == "kind"
    if nur_kinder_knoepfe or ist_kind:
        qs = qs.filter(schnellknopf_wer=SchnellknopfWer.ALLE)
    if ist_kind:
        qs = qs.filter(Q(zugewiesen_an__isnull=True) | Q(zugewiesen_an=benutzer))
    aufgaben = list(qs.order_by("titel", "id"))
    laufende: dict[int, list[AufgabenInstanz]] = {}
    for instanz in (
        AufgabenInstanz.objects.filter(aufgabe__in=aufgaben, status__in=OFFEN_STATUS)
        .select_related("kind")
        .order_by("-id")
    ):
        laufende.setdefault(instanz.aufgabe_id, []).append(instanz)
    kinder = list(konten_selectors.aktive_kinder())
    for aufgabe in aufgaben:
        liste = laufende.get(aufgabe.pk, [])
        aufgabe.laufende = liste
        erlaubt = [k for k in kinder if aufgabe.zugewiesen_an_id in (None, k.pk)]
        aufgabe.kinder_anzahl = len(erlaubt)
        dran = {i.kind_id for i in liste if i.kind_id}
        aufgabe.laufend_anzahl = sum(1 for k in erlaubt if k.pk in dran)
        if aufgabe.schnellknopf_modus != SchnellknopfModus.JEDES:
            aufgabe.laeuft = liste[0] if liste else None
        elif ist_kind:
            aufgabe.laeuft = _blockiert(aufgabe, benutzer, liste)
        else:
            ungebunden = next((i for i in liste if i.kind_id is None), None)
            alle_dran = bool(erlaubt) and aufgabe.laufend_anzahl == len(erlaubt)
            aufgabe.laeuft = ungebunden or (liste[0] if alle_dran else None)
    return aufgaben


# Start-Knöpfe: Titel wie die Bibliotheksvorlagen (Migration 0011)
START_KNOEPFE = knoepfe_start.START_TITEL
_MERKER = "aufgaben.schnellknoepfe_angelegt"
_MERKER_BIBLIOTHEK = "aufgaben.knoepfe_aus_bibliothek"


def schnellknoepfe_sicherstellen() -> int:
    """Legt die Start-Knöpfe und die Knöpfe aus der Bibliothek an (Anzahl neu), je **einmal**.

    Eine Aufgabe braucht einen Ersteller: der erste aktive Elternteil. Gibt es noch keinen oder
    ist der jeweilige Merker gesetzt, passiert nichts. Gibt es den Titel schon als Knopf, wird er
    übersprungen. Löschen Eltern einen Knopf später, kommt er nicht wieder (der Merker bleibt).
    """
    return _start_knoepfe_anlegen() + _knoepfe_aus_bibliothek_anlegen()


def _knoepfe_aus_bibliothek_anlegen() -> int:
    """Jede aktive Vorlage ohne gleichnamigen Knopf wird ein Knopf (Migration 0016 holt nach)."""
    with transaction.atomic():
        if einstellungen.wert(_MERKER_BIBLIOTHEK):
            return 0
        ersteller = konten_selectors.aktive_eltern().order_by("reihenfolge", "anzeigename").first()
        if ersteller is None:
            return 0

        def protokoll(aufgabe):
            audit.protokollieren(
                "aufgabe.angelegt",
                akteur=None,
                objekt=aufgabe,
                details={
                    "titel": aufgabe.titel,
                    "punkte": aufgabe.punkte,
                    "quelle": "bibliothek_umwandlung",
                },
            )

        neu = knoepfe_start.aus_bibliothek_anlegen(Aufgabe, Vorlage, ersteller, protokoll)
        knoepfe_start.modus_der_knoepfe_setzen(Aufgabe)
        einstellungen.setzen(_MERKER_BIBLIOTHEK, True, akteur=None)
    return len(neu)


def _start_knoepfe_anlegen() -> int:
    with transaction.atomic():
        if einstellungen.wert(_MERKER):
            return 0
        eltern = konten_selectors.aktive_eltern().order_by("reihenfolge", "anzeigename")
        ersteller = eltern.first()
        if ersteller is None:
            return 0
        haushalt = Kategorie.objects.filter(name="Haushalt").first()
        neu = 0
        for titel in START_KNOEPFE:
            if Aufgabe.objects.filter(titel=titel).exists():
                continue
            vorlage = Vorlage.objects.filter(titel=titel).first()
            aufgabe = Aufgabe.objects.create(
                titel=titel,
                punkte=5,
                freigabeart="eltern",
                kategorie=vorlage.kategorie if vorlage else haushalt,
                vorlage=vorlage,
                wiederholungsart=wiederholung.BEI_BEDARF,
                schnellknopf_wer=SchnellknopfWer.ALLE,
                emoji=vorlage.emoji if vorlage and vorlage.emoji else _EMOJI[titel],
                erstellt_von=ersteller,
            )
            audit.protokollieren(
                "aufgabe.angelegt",
                akteur=None,
                objekt=aufgabe,
                details={"titel": titel, "punkte": 5, "quelle": "startwerte"},
            )
            neu += 1
        einstellungen.setzen(_MERKER, True, akteur=None)
    return neu


_EMOJI = {"Restmüll": "🗑️", "Biomüll": "🍂", "Altglas": "🍾"}
