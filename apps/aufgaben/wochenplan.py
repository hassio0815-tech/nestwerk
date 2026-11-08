"""Wochenplan (AP14): Daten für die Wochenansicht und Verschieben mit Reihenfolge."""

from datetime import date

from django.db import transaction
from django.utils.translation import gettext as _

from apps.kern import audit, zeit

from . import instanzen, wiederholung, zustand
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


# Löschen im Wochenplan, zwei Wege (ⓧ an jeder Karte):
# - ``LOESCHBAR`` (offen, Konflikt, reserviert, nicht übernommen): Karte auslassen, es gibt keine
#   Punkte ("Nur diesen Tag" / "Ganze Serie").
# - alle anderen Karten (gemeldet, Rückfrage, bestätigt, nachzubessern, abgelehnt, storniert):
#   ganzer Vorgang (``ablauf.vorgang_loeschen``: Punkte per Gegenbuchung auf netto 0, überall weg).
LOESCHBAR = (
    InstanzStatus.OFFEN,
    InstanzStatus.KONFLIKT,
    InstanzStatus.RESERVIERT,
    InstanzStatus.NICHT_UEBERNOMMEN,
)
MODI_LOESCHEN = ("tag", "serie")


def loeschbar(instanz) -> bool:
    return instanz.status in LOESCHBAR and instanz.ausgelassen_am is None


def vorgang_loeschbar(instanz) -> bool:
    """ⓧ löscht den ganzen Vorgang (Punkte weg, verschwindet überall): jede sichtbare Karte, die
    nicht über ``loeschbar`` nur ausgelassen wird."""
    return instanz.status not in LOESCHBAR and instanz.ausgelassen_am is None


def loeschen_moeglich(instanz) -> bool:
    return loeschbar(instanz) or vorgang_loeschbar(instanz)


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
        inst.vorgang = vorgang_loeschbar(inst)
        inst.serie = ist_serie(inst.aufgabe)
        nach_tag[inst.faellig_am].append(inst)
    ohne_termin = AufgabenInstanz.objects.filter(
        faellig_am__isnull=True, status__in=instanzen.VERSCHIEBBAR, ausgelassen_am__isnull=True
    ).select_related("kind", "aufgabe__kategorie")
    ohne_termin = list(ohne_termin)
    for inst in ohne_termin:
        inst.beweglich = True
        inst.loeschbar = loeschbar(inst)
        inst.vorgang = vorgang_loeschbar(inst)
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

    Die Zeile wird nicht gelöscht, sondern über den Zustandsautomaten auf ``storniert`` mit
    ``ausgelassen_am`` gesetzt (Kind-Ansichten zeigen sie nicht als „Punkte korrigiert“):
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
            ablauf.reservierung_loesen(inst, von=von, entfaellt=True)
        except ablauf.AblaufFehler as exc:
            raise ValueError(str(exc)) from exc
        inst.refresh_from_db()
    felder = {"ausgelassen_am": jetzt}
    if inst.abgeschlossen_am is None:
        felder["abgeschlossen_am"] = jetzt
    try:
        zustand.uebergang(
            inst,
            InstanzStatus.STORNIERT,
            von=(InstanzStatus.OFFEN, InstanzStatus.NICHT_UEBERNOMMEN),
            bedingung={"ausgelassen_am__isnull": True},
            **felder,
        )
    except zustand.UngueltigerUebergang as exc:
        raise ValueError(_("Instanz wurde zwischenzeitlich geändert")) from exc
    inst.refresh_from_db()
    audit.protokollieren(
        "aufgabe.instanz_ausgelassen",
        akteur=von,
        objekt=inst,
        details={"titel": inst.titel_snapshot, "faellig_am": str(inst.faellig_am)},
    )
    return inst


def _vorgang_loeschen(inst, modus, *, von, jetzt=None) -> AufgabenInstanz:
    """Karte mit Vorgang (bestätigt, gemeldet ...): alles löschen. Einmalige Aufgaben beendet
    ``ablauf.vorgang_loeschen`` selbst; ``serie`` beendet zusätzlich eine Serie."""
    from . import ablauf, services

    try:
        ablauf.vorgang_loeschen(inst, von=von, jetzt=jetzt)
    except ablauf.AblaufFehler as exc:
        raise ValueError(str(exc)) from exc
    aufgabe = AufgabenInstanz.alle.select_related("aufgabe").get(pk=inst.pk).aufgabe
    if modus == "serie" and ist_serie(aufgabe) and aufgabe.status != Status.BEENDET:
        services.aufgabe_status_setzen(aufgabe, Status.BEENDET, von=von)
    return AufgabenInstanz.alle.select_related("aufgabe").get(pk=inst.pk)


def loeschart(instanz) -> str:
    """Welcher Löschweg gilt für die Karte gerade (Dialog-Variante): ``einzeln`` | ``serie``
    (Karte auslassen) | ``vorgang`` | ``vorgang-serie`` (ganzer Vorgang)."""
    vorgang = vorgang_loeschbar(instanz)
    serie = ist_serie(instanz.aufgabe)
    return (
        ("vorgang" if vorgang else "")
        + ("-" if vorgang and serie else "")
        + ("serie" if serie else "")
    ) or "einzeln"


@transaction.atomic
def loeschen(instanz_pk, modus, *, von, jetzt=None, art=None) -> AufgabenInstanz:
    """Löschen aus dem Wochenplan. ``tag``: nur diese Karte. ``serie``: Aufgabe beenden (endgültig,
    Punkte bleiben), freie Instanzen entfallen. Einmalige Aufgaben enden mit ihrer einzigen Karte;
    Schnell-Knöpfe bleiben (nur die Karte geht). Karten mit Vorgang (``vorgang_loeschbar``)
    löschen den ganzen Vorgang samt Punkten (``ablauf.vorgang_loeschen``). ``art``: der Weg, den der
    Dialog angezeigt hat (``loeschart``); passt er nicht mehr zur Karte, ``ValueError``."""
    from . import services

    if modus not in MODI_LOESCHEN:
        raise ValueError(_("Unbekannte Auswahl."))
    try:
        vorhanden = AufgabenInstanz.objects.select_related("aufgabe").get(pk=instanz_pk)
    except AufgabenInstanz.DoesNotExist as exc:
        raise ValueError(_("Aufgabe nicht gefunden")) from exc
    if art is not None and art != loeschart(vorhanden):
        raise ValueError(_("Die Karte hat sich geändert, bitte neu laden."))
    if vorgang_loeschbar(vorhanden):
        return _vorgang_loeschen(vorhanden, modus, von=von, jetzt=jetzt)
    inst = auslassen(instanz_pk, von=von, jetzt=jetzt)
    aufgabe = inst.aufgabe
    einmalig = aufgabe.wiederholungsart == wiederholung.EINMALIG
    if (modus == "serie" and ist_serie(aufgabe)) or einmalig:
        if aufgabe.status != Status.BEENDET:
            services.aufgabe_status_setzen(aufgabe, Status.BEENDET, von=von)
    return inst
