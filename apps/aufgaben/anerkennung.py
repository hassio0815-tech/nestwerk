"""Anerkennung: Eltern schenken einem Kind Punkte ohne Aufgabe (Lob, Hilfe, Extra-Einsatz).

- 1 Punkt = 1 Guthaben + 1 XP (Buchungsart ``anerkennung``), Bemerkung Pflicht, nur Eltern.
- Grenzen (Elterneinstellungen): je Vergabe 1 bis ``aufgaben.anerkennung_max_punkte``, je Kind
  und Woche (Montag bis Sonntag, Fach-Zeitzone) höchstens ``aufgaben.anerkennung_woche_max``
  Punkte netto. Ein Storno (``punkte.gegenbuchen``) gibt den Platz in der Woche wieder frei.
- Prüfung und Buchung laufen unter der Schreibsperre des Kindes in einer Transaktion
  (zwei gleichzeitige Vergaben können das Wochenlimit nicht überschreiten).
- ``vorgang``: Kennung des Formulars; ein zweiter Absendeklick bucht nicht doppelt.
"""

import uuid

from django.db import transaction
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte

from . import events
from .zustand import AblaufFehler

QUELLE = "anerkennung"
BEMERKUNG_MAX = 200


class AnerkennungFehler(AblaufFehler):
    """Eingabe oder Limit der Anerkennung ungültig."""


def grenzen():
    """``(je Vergabe, je Woche)`` aus den Einstellungen."""
    werte = einstellungen.werte("aufgaben.anerkennung_max_punkte", "aufgaben.anerkennung_woche_max")
    return werte["aufgaben.anerkennung_max_punkte"], werte["aufgaben.anerkennung_woche_max"]


def _woche(bezugsdatum):
    woche = zeit.IsoWoche.von(bezugsdatum)
    return woche.montag, woche.sonntag


def woche_bisher(kind, bezugsdatum=None):
    """Netto vergebene Anerkennung (inkl. Stornos) in der Woche von ``bezugsdatum``."""
    von, bis = _woche(bezugsdatum or zeit.heute())
    return punkte_selectors.netto_summe(kind, von, bis, quelle_modul=QUELLE)


def woche_rest(kind, bezugsdatum=None):
    _je_vergabe, je_woche = grenzen()
    return max(je_woche - woche_bisher(kind, bezugsdatum), 0)


def uebersicht(kinder):
    """Für die Maske: ``[{"kind", "bisher", "rest"}]``."""
    _je_vergabe, je_woche = grenzen()
    zeilen = []
    for kind in kinder:
        bisher = woche_bisher(kind)
        zeilen.append({"kind": kind, "bisher": bisher, "rest": max(je_woche - bisher, 0)})
    return zeilen


def neuer_vorgang():
    return uuid.uuid4().hex


def vergeben(kind, punktzahl, bemerkung, *, von, vorgang=None):
    """Bucht Anerkennung und benachrichtigt das Kind. Gibt die Buchung zurück."""
    if getattr(von, "rolle", None) != "eltern":
        raise AnerkennungFehler(_("Anerkennung vergeben nur Eltern."))
    if getattr(kind, "rolle", None) != "kind" or not getattr(kind, "aktiv", False):
        raise AnerkennungFehler(_("Bitte ein Kind auswählen."))
    if isinstance(punktzahl, bool) or not isinstance(punktzahl, int):
        raise AnerkennungFehler(_("Bitte eine ganze Zahl für die Punkte eingeben."))
    bemerkung = " ".join(str(bemerkung or "").split())
    if not bemerkung:
        raise AnerkennungFehler(_("Bitte eine kurze Bemerkung eingeben."))
    if len(bemerkung) > BEMERKUNG_MAX:
        raise AnerkennungFehler(
            _("Die Bemerkung ist zu lang (höchstens %(n)s Zeichen).") % {"n": BEMERKUNG_MAX}
        )
    je_vergabe, je_woche = grenzen()
    if not 1 <= punktzahl <= je_vergabe:
        raise AnerkennungFehler(_("Bitte 1 bis %(max)s Punkte eingeben.") % {"max": je_vergabe})
    schluessel = f"anerkennung:{vorgang or neuer_vorgang()}"
    heute = zeit.heute()
    with transaction.atomic():
        punkte.schreibsperre(kind)
        bestehend = punkte_selectors.buchung_zu_schluessel(schluessel)
        if bestehend is not None:
            if bestehend.kind_id == kind.pk:
                return bestehend  # doppelter Absendeklick
            schluessel = f"anerkennung:{neuer_vorgang()}"  # fremde Kennung: neue Vergabe
        rest = je_woche - woche_bisher(kind, heute)
        if punktzahl > rest:
            raise AnerkennungFehler(
                _("Diese Woche sind für %(name)s nur noch %(rest)s Anerkennungs-Punkte möglich.")
                % {"name": kind.anzeigename, "rest": max(rest, 0)}
            )
        buchung = punkte.buchen(
            kind,
            punkte.Art.ANERKENNUNG,
            punktzahl,
            schluessel=schluessel,
            quelle_modul=QUELLE,
            bezugsdatum=heute,
            begruendung=bemerkung,
            von=von,
        )
        ereignisse.veroeffentlichen(
            events.ANERKENNUNG,
            kind=kind,
            akteur=von if hasattr(von, "pk") else None,
            daten={"buchung": buchung.pk, "punkte": punktzahl, "begruendung": bemerkung},
            schluessel=f"{events.ANERKENNUNG}:{buchung.pk}",
        )
        audit.protokollieren(
            "aufgabe.anerkennung",
            akteur=von,
            objekt=buchung,
            kind=kind,
            details={"punkte": punktzahl, "begruendung": bemerkung},
        )
    return buchung
