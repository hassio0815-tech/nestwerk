"""Wochenplan (AP14): Daten für die Wochenansicht und Verschieben mit Reihenfolge."""

from datetime import date

from django.db import transaction
from django.utils.translation import gettext as _

from apps.kern import audit, zeit

from . import instanzen, wiederholung
from .models import AufgabenInstanz, InstanzStatus, Status

MAX_REIHENFOLGE = 100


def woche_aus_datum(text) -> zeit.IsoWoche:
    """ISO-Woche zum Datum ``JJJJ-MM-TT``; ungültig/leer = aktuelle Woche."""
    try:
        return zeit.IsoWoche.von(date.fromisoformat(text))
    except (TypeError, ValueError):
        return zeit.aktuelle_woche()


def verschiebbar(instanz) -> bool:
    return instanz.status in instanzen.VERSCHIEBBAR


# Löschen im Wochenplan: nur Karten ohne gebuchte oder offene Punkte. Gemeldet, bestätigt,
# abgelehnt, storniert und "zum Nachbessern" tragen Entscheidungen/Buchungen und bleiben.
LOESCHBAR = (
    InstanzStatus.OFFEN,
    InstanzStatus.KONFLIKT,
    InstanzStatus.RESERVIERT,
    InstanzStatus.NICHT_UEBERNOMMEN,
)
MODI_LOESCHEN = ("tag", "serie")


def loeschbar(instanz) -> bool:
    return instanz.status in LOESCHBAR and instanz.ausgelassen_am is None


def ist_serie(aufgabe) -> bool:
    """Wiederkehrend (wöchentlich/Intervall); einmalige und Schnell-Knöpfe sind keine Serie."""
    return aufgabe.wiederholungsart not in (wiederholung.EINMALIG, wiederholung.BEI_BEDARF)


def woche_daten(woche: zeit.IsoWoche, *, heute=None) -> dict:
    """Tage Mo-So mit ihren Instanzen sowie Instanzen ohne Termin (nur Info)."""
    from . import selectors

    heute = heute or zeit.heute()
    nach_tag = {tag: [] for tag in woche.tage()}
    for inst in (
        selectors.instanzen_im_zeitraum(woche.montag, woche.sonntag)
        .filter(ausgelassen_am__isnull=True)
        .select_related("kind", "aufgabe__kategorie")
    ):
        inst.beweglich = verschiebbar(inst)
        inst.loeschbar = loeschbar(inst)
        inst.serie = ist_serie(inst.aufgabe)
        nach_tag[inst.faellig_am].append(inst)
    ohne_termin = AufgabenInstanz.objects.filter(
        faellig_am__isnull=True, status__in=instanzen.VERSCHIEBBAR, ausgelassen_am__isnull=True
    ).select_related("kind", "aufgabe__kategorie")
    ohne_termin = list(ohne_termin)
    for inst in ohne_termin:
        inst.beweglich = True
        inst.loeschbar = loeschbar(inst)
        inst.serie = ist_serie(inst.aufgabe)
    tage = [{"datum": t, "heute": t == heute, "instanzen": nach_tag[t]} for t in woche.tage()]
    return {
        "woche": woche,
        "tage": tage,
        "ohne_termin": list(ohne_termin),
        "vorherige": woche.vorherige().montag,
        "naechste": woche.naechste().montag,
        "heute_datum": heute,
    }


def reihenfolge_lesen(text) -> list[int]:
    """Kommagetrennte Instanz-IDs; ungültige Eingaben -> ValueError."""
    if not text:
        return []
    try:
        ids = [int(x) for x in str(text).split(",") if x.strip()]
    except ValueError as exc:
        raise ValueError(_("Ungültige Reihenfolge")) from exc
    if len(ids) > MAX_REIHENFOLGE or len(set(ids)) != len(ids):
        raise ValueError(_("Ungültige Reihenfolge"))
    return ids


@transaction.atomic
def verschieben(instanz_pk, datum: date, *, von, reihenfolge=()):
    """Verschiebt eine Instanz auf ``datum`` und ordnet den Tag nach ``reihenfolge`` (IDs).

    Das Verschieben selbst (Zustandsprüfung, Fenster, Audit) macht
    ``instanzen.instanz_verschieben``. Löst ``ValueError`` aus, wenn nicht erlaubt.
    """
    try:
        inst = AufgabenInstanz.objects.get(pk=instanz_pk)
    except AufgabenInstanz.DoesNotExist as exc:
        raise ValueError(_("Aufgabe nicht gefunden")) from exc
    reihenfolge = list(reihenfolge)
    position = reihenfolge.index(inst.pk) if inst.pk in reihenfolge else None
    inst = instanzen.instanz_verschieben(inst, datum, von=von, sortierung=position)
    for index, pk in enumerate(reihenfolge):
        if pk == inst.pk:
            continue
        AufgabenInstanz.objects.filter(pk=pk, faellig_am=datum).exclude(
            status__in=(InstanzStatus.STORNIERT,)
        ).update(sortierung=index)
    return inst


@transaction.atomic
def auslassen(instanz_pk, *, von, jetzt=None) -> AufgabenInstanz:
    """Nimmt genau diese Karte aus dem Wochenplan ("Nur diesen Tag").

    Die Zeile wird nicht gelöscht, sondern auf ``storniert`` mit ``ausgelassen_am`` gesetzt:
    ``unique(aufgabe, plan_datum)`` und ``abgeschlossen_am`` (ungebunden: nächster Termin erst
    danach) verhindern, dass der Generator die Instanz neu erzeugt. Reservierte/Konflikt-Karten
    werden zuerst gelöst (Kinder bekommen die übliche Nachricht). Punkte bleiben unberührt.
    """
    from . import ablauf

    jetzt = jetzt or zeit.jetzt()
    try:
        inst = AufgabenInstanz.objects.select_related("aufgabe").get(pk=instanz_pk)
    except AufgabenInstanz.DoesNotExist as exc:
        raise ValueError(_("Aufgabe nicht gefunden")) from exc
    if not loeschbar(inst):
        raise ValueError(_("Diese Aufgabe kann nicht mehr gelöscht werden."))
    if inst.status in (InstanzStatus.RESERVIERT, InstanzStatus.KONFLIKT):
        try:
            ablauf.reservierung_loesen(inst, von=von)
        except ablauf.AblaufFehler as exc:
            raise ValueError(str(exc)) from exc
        inst.refresh_from_db()
    felder = {"status": InstanzStatus.STORNIERT, "ausgelassen_am": jetzt}
    if inst.abgeschlossen_am is None:
        felder["abgeschlossen_am"] = jetzt
    treffer = AufgabenInstanz.objects.filter(
        pk=inst.pk,
        status__in=(InstanzStatus.OFFEN, InstanzStatus.NICHT_UEBERNOMMEN),
        ausgelassen_am__isnull=True,
    ).update(**felder)
    if not treffer:
        raise ValueError(_("Instanz wurde zwischenzeitlich geändert"))
    inst.refresh_from_db()
    audit.protokollieren(
        "aufgabe.instanz_ausgelassen",
        akteur=von,
        objekt=inst,
        details={"titel": inst.titel_snapshot, "faellig_am": str(inst.faellig_am)},
    )
    return inst


@transaction.atomic
def loeschen(instanz_pk, modus, *, von, jetzt=None) -> AufgabenInstanz:
    """Löschen aus dem Wochenplan. ``tag``: nur diese Karte. ``serie``: Aufgabe beenden (endgültig,
    Punkte bleiben), freie Instanzen entfallen. Einmalige Aufgaben enden mit ihrer einzigen Karte;
    Schnell-Knöpfe bleiben (nur die Karte geht)."""
    from . import services

    if modus not in MODI_LOESCHEN:
        raise ValueError(_("Unbekannte Auswahl."))
    inst = auslassen(instanz_pk, von=von, jetzt=jetzt)
    aufgabe = inst.aufgabe
    einmalig = aufgabe.wiederholungsart == wiederholung.EINMALIG
    if (modus == "serie" and ist_serie(aufgabe)) or einmalig:
        if aufgabe.status != Status.BEENDET:
            services.aufgabe_status_setzen(aufgabe, Status.BEENDET, von=von)
    return inst
