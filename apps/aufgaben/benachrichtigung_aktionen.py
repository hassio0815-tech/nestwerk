"""Aktionen in der Benachrichtigungs-Karte der Eltern (Anbieter für ``benachrichtigung.aktionen``).

- "hat eine Aufgabe gemeldet" / "hat geantwortet": Bestätigen, Ablehnen (wie auf der
  Meldungen-Seite, ohne Bonus und ohne Begründung).
- "möchte eine Aufgabe machen" (Kind wählt): Erlauben (die Reservierung bleibt), Ablehnen
  (Reservierung lösen, die Aufgabe ist wieder frei).
- "Mehrere Kinder wollen dieselbe Aufgabe": Erlauben teilt dem Kind der Karte zu.

Offen bleibt eine Karte, solange die Instanz im passenden Zustand ist; danach ist sie erledigt.
"""

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from apps.benachrichtigung import aktionen
from apps.benachrichtigung.aktionen import Aktion, AktionFehler, Zustand
from apps.punkte import selectors as punkte_selectors

from . import events, services
from .models import AufgabenInstanz, InstanzStatus, Interesse, InteresseStatus

# Texte stehen als Msgid in den .po-Dateien (Aktion.text wird erst in der Vorlage übersetzt)
BESTAETIGEN = Aktion("bestaetigen", gettext_noop("Bestätigen"), "primaer", "check")
ABLEHNEN = Aktion("ablehnen", gettext_noop("Ablehnen"), "sanft", "x")
ERLAUBEN = Aktion("erlauben", gettext_noop("Erlauben"), "primaer", "check")

KEINE = Zustand(offen=False)


def _instanzen(eintraege) -> dict:
    ids = {e.ereignis.daten.get("instanz_id") for e in eintraege}
    ids.discard(None)
    return {i.pk: i for i in AufgabenInstanz.objects.filter(pk__in=ids)}


def _melden_zustaende(eintraege) -> dict:
    instanzen = _instanzen(eintraege)
    ergebnis = {}
    for e in eintraege:
        instanz = instanzen.get(e.ereignis.daten.get("instanz_id"))
        if instanz is not None and instanz.status == InstanzStatus.GEMELDET:
            ergebnis[e.pk] = Zustand(offen=True, aktionen=(BESTAETIGEN, ABLEHNEN))
        else:
            ergebnis[e.pk] = KEINE
    return ergebnis


def _interesse_zustaende(eintraege) -> dict:
    instanzen = _instanzen(eintraege)
    ergebnis = {}
    for e in eintraege:
        instanz = instanzen.get(e.ereignis.daten.get("instanz_id"))
        offen = (
            instanz is not None
            and instanz.status == InstanzStatus.RESERVIERT
            and instanz.kind_id == e.ereignis.kind_id
            and e.gelesen_am is None
        )
        ergebnis[e.pk] = Zustand(offen=True, aktionen=(ERLAUBEN, ABLEHNEN)) if offen else KEINE
    return ergebnis


def _konflikt_zustaende(eintraege) -> dict:
    instanzen = _instanzen(eintraege)
    aktiv = set(
        Interesse.objects.filter(
            instanz__in=list(instanzen), status=InteresseStatus.AKTIV
        ).values_list("instanz_id", "kind_id")
    )
    ergebnis = {}
    for e in eintraege:
        instanz = instanzen.get(e.ereignis.daten.get("instanz_id"))
        offen = (
            instanz is not None
            and instanz.status == InstanzStatus.KONFLIKT
            and (instanz.pk, e.ereignis.kind_id) in aktiv
        )
        ergebnis[e.pk] = Zustand(offen=True, aktionen=(ERLAUBEN,)) if offen else KEINE
    return ergebnis


def _ausfuehren(eintrag, aktion, benutzer) -> str:
    typ = eintrag.ereignis.typ_id
    instanz = AufgabenInstanz.objects.filter(pk=eintrag.ereignis.daten.get("instanz_id")).first()
    if instanz is None:
        raise AktionFehler(_("Diese Aufgabe gibt es nicht mehr."))
    try:
        if typ in (events.GEMELDET, events.ANTWORT):
            if aktion == "bestaetigen":
                services.bestaetigen(instanz, von=benutzer)
                return _("Bestätigt, Punkte gebucht.")
            services.ablehnen(instanz, von=benutzer)
            return _("Abgelehnt.")
        if typ == events.INTERESSE:
            if aktion == "ablehnen":
                services.reservierung_loesen(instanz, von=benutzer)
                return _("Abgelehnt, die Aufgabe ist wieder frei.")
            return _("Erlaubt.")
        if typ == events.KONFLIKT:
            services.zuteilen(instanz, eintrag.ereignis.kind, von=benutzer)
            return _("Zugeteilt.")
    except services.AblaufFehler as fehler:
        raise AktionFehler(str(fehler)) from fehler
    raise AktionFehler(_("Das ist nicht mehr möglich."))


def _geloeschte(eintraege) -> set:
    """Einträge zu einem gelöschten Vorgang: verschwinden aus Liste, Zählern und Pop-ups."""
    daten = {e.pk: e.ereignis.daten or {} for e in eintraege}
    ids = {d.get("instanz_id") for d in daten.values()}
    ids = {i for i in ids if isinstance(i, int)}
    weg = (
        set(
            AufgabenInstanz.alle.filter(pk__in=ids, geloescht_am__isnull=False).values_list(
                "pk", flat=True
            )
        )
        if ids
        else set()
    )
    # Serienbonus-Pop-up u. Ä.: verweist nur auf die Buchung, nicht auf die Instanz
    buchungen = {d.get("buchung") for d in daten.values()}
    buchungen = {b for b in buchungen if isinstance(b, int)}
    weg_buchungen = punkte_selectors.ausgeblendete_buchungen(buchungen) if buchungen else set()
    return {
        pk
        for pk, d in daten.items()
        if d.get("instanz_id") in weg or d.get("buchung") in weg_buchungen
    }


def registrieren():
    aktionen.ausblender_registrieren(_geloeschte)
    aktionen.registrieren(events.GEMELDET, zustaende=_melden_zustaende, ausfuehren=_ausfuehren)
    aktionen.registrieren(events.ANTWORT, zustaende=_melden_zustaende, ausfuehren=_ausfuehren)
    aktionen.registrieren(events.INTERESSE, zustaende=_interesse_zustaende, ausfuehren=_ausfuehren)
    aktionen.registrieren(events.KONFLIKT, zustaende=_konflikt_zustaende, ausfuehren=_ausfuehren)
