"""Schreibende Schnittstelle von punkte: Buchungen ins Ledger (ARCHITECTURE 2.1, DATA_MODEL 3.1).

- ``buchen``: neue Buchung; ``punkte`` ist der Betrag (> 0), das Vorzeichen folgt aus der Art
  (``WIRKUNG``). Ausnahme ``korrektur``: ``punkte`` ist vorzeichenbehaftet (≠ 0) und wirkt
  gleich auf Guthaben und XP (K2: Korrektur mindert auch XP; der erreichte Rang bleibt).
- ``gegenbuchen``: Storno einer Buchung (kehrt Guthaben- und XP-Wirkung exakt um).
- Idempotenz: gibt es den Schlüssel schon, entsteht keine zweite Buchung; zurück kommt die
  bestehende.
- Ausgaben (Einlösung, Mod-Kauf) machen das Guthaben nie negativ. Prüfung und Einfügen laufen
  in einer Transaktion; SQLite startet sie mit ``BEGIN IMMEDIATE`` (Schreibsperre ab Beginn),
  parallele Ausgaben werden dadurch serialisiert.
- Je Buchung: Audit-Eintrag (``kern.audit``, Standard-Akteur = angemeldeter Benutzer) und
  Ereignis ``punkte.gebucht`` (Outbox), beides in derselben Transaktion (Rollback = nichts).
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import IntegrityError, connection, models, transaction
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import audit, zeit

from .events import GEBUCHT
from .models import Art, Buchung
from .selectors import guthaben, verfuegbar

__all__ = [
    "AUSGABEN",
    "Art",
    "GuthabenUnzureichend",
    "IdempotenzKonflikt",
    "PunkteFehler",
    "UngueltigeBuchung",
    "WIRKUNG",
    "buchen",
    "gegenbuchen",
    "schreibsperre",
]

# Art -> (Faktor Guthaben, Faktor XP) für einen positiven Betrag
WIRKUNG = {
    Art.AUFGABE: (1, 1),
    Art.SERIENBONUS: (1, 1),
    Art.SONDERPUNKTE: (1, 1),
    Art.MODUL: (1, 1),
    Art.EINLOESUNG: (-1, 0),
    Art.MODKAUF: (-1, 0),
    Art.KORREKTUR: (1, 1),  # Betrag vorzeichenbehaftet
}
# Ausgaben: Guthaben darf nicht negativ werden. Wert = Standard für "verfügbar prüfen"
# (Einlösung ist selbst schon als offener Antrag reserviert, Mod-Kauf nicht).
AUSGABEN = {Art.EINLOESUNG: False, Art.MODKAUF: True}
BEGRUENDUNG_PFLICHT = frozenset({Art.SONDERPUNKTE, Art.KORREKTUR})
NUR_ELTERN = frozenset({Art.SONDERPUNKTE, Art.KORREKTUR, Art.STORNO})


class PunkteFehler(ValueError):
    """Basis der fachlichen Fehler von punkte."""


class UngueltigeBuchung(PunkteFehler):
    """Eingaben passen nicht zur Buchungsart."""


class GuthabenUnzureichend(PunkteFehler):
    """Die Ausgabe würde das (verfügbare) Guthaben unter 0 bringen."""


class IdempotenzKonflikt(PunkteFehler):
    """Schlüssel existiert bereits für ein anderes Kind oder eine andere Art."""


def buchen(
    kind,
    art,
    punkte,
    *,
    schluessel,
    quelle_modul,
    bezugsdatum=None,
    referenz=None,
    referenz_typ="",
    referenz_id="",
    begruendung="",
    von=audit.AKTUELL,
    verfuegbar_pruefen=None,
):
    """Bucht ``punkte`` für ``kind`` und gibt die Buchung zurück (bei bekanntem Schlüssel die
    bestehende).

    - ``schluessel``: fachlicher Idempotenz-Schlüssel, z. B. ``aufgabe:<instanz>:basis``.
    - ``referenz``: Modell-Instanz (setzt ``referenz_typ``/``referenz_id``) oder beides direkt.
    - ``bezugsdatum``: fachlicher Tag (Standard: heute, Fach-Zeitzone).
    - ``von``: handelnder Benutzer (Standard: angemeldeter Benutzer, sonst System).
    - ``verfuegbar_pruefen``: nur Ausgaben; ``True`` = gegen Guthaben minus Reservierungen
      prüfen. ``None`` = Standard der Art (``AUSGABEN``).
    """
    art = _art_pruefen(art)
    if art == Art.STORNO:
        raise UngueltigeBuchung("Storno nur über gegenbuchen()")
    punkte = _betrag_pruefen(art, punkte)
    schluessel = _text_pruefen("schluessel", schluessel, 120, pflicht=True)
    quelle_modul = _text_pruefen("quelle_modul", quelle_modul, 40, pflicht=True)
    referenz_typ, referenz_id = _referenz(referenz, referenz_typ, referenz_id)
    begruendung = _text_pruefen("begruendung", begruendung, 200, pflicht=art in BEGRUENDUNG_PFLICHT)
    _kind_pruefen(kind)
    akteur = _akteur(von, art)
    if verfuegbar_pruefen is not None and art not in AUSGABEN:
        raise UngueltigeBuchung("verfuegbar_pruefen gilt nur für Ausgaben")
    g_faktor, x_faktor = WIRKUNG[art]

    with transaction.atomic():
        schreibsperre(kind)
        bestehend = _bestehende(schluessel, kind=kind, art=art)
        if bestehend is not None:
            return bestehend
        if art in AUSGABEN:
            pruefe_verfuegbar = AUSGABEN[art] if verfuegbar_pruefen is None else verfuegbar_pruefen
            stand = verfuegbar(kind) if pruefe_verfuegbar else guthaben(kind)
            if stand < punkte:
                raise GuthabenUnzureichend(
                    (
                        _("Verfügbar %(stand)s, benötigt %(punkte)s")
                        if pruefe_verfuegbar
                        else _("Guthaben %(stand)s, benötigt %(punkte)s")
                    )
                    % {"stand": stand, "punkte": punkte}
                )
        buchung = Buchung(
            kind=kind,
            bezugsdatum=bezugsdatum or zeit.heute(),
            art=art,
            guthaben_delta=g_faktor * punkte,
            xp_delta=x_faktor * punkte,
            idempotenz_schluessel=schluessel,
            quelle_modul=quelle_modul,
            referenz_typ=referenz_typ,
            referenz_id=referenz_id,
            begruendung=begruendung,
            erstellt_von=_benutzer(akteur),
        )
        return _speichern(buchung, akteur, "punkte.gebucht")


def gegenbuchen(original, *, begruendung="", von=audit.AKTUELL, bezugsdatum=None, schluessel=None):
    """Storniert ``original`` (Buchung oder ID) durch eine Gegenbuchung mit umgekehrten Deltas.

    Eine Buchung wird höchstens einmal storniert (``storno_von`` unique); ein zweiter Aufruf
    gibt die bestehende Gegenbuchung zurück. Stornos selbst sind nicht stornierbar.
    Ein Storno ist keine Ausgabe: Es darf das Guthaben unter 0 bringen (z. B. Korrektur einer
    Vertrauens-Aufgabe, deren Punkte schon ausgegeben sind).
    """
    begruendung = _text_pruefen("begruendung", begruendung, 200, pflicht=False)
    akteur = _akteur(von, Art.STORNO)
    with transaction.atomic():
        if not isinstance(original, Buchung):
            original = Buchung.objects.get(pk=original)
        if original.art == Art.STORNO:
            raise UngueltigeBuchung("Ein Storno kann nicht storniert werden")
        schluessel = _text_pruefen(
            "schluessel", schluessel or f"storno:{original.pk}", 120, pflicht=True
        )
        schreibsperre(original.kind)
        bestehend = Buchung.objects.filter(storno_von=original).first()
        if bestehend is not None:
            return bestehend
        if _bestehende(schluessel, kind=original.kind, art=Art.STORNO) is not None:
            raise IdempotenzKonflikt(f"Schlüssel '{schluessel}' gehört zu einem anderen Storno")
        buchung = Buchung(
            kind=original.kind,
            bezugsdatum=bezugsdatum or zeit.heute(),
            art=Art.STORNO,
            guthaben_delta=-original.guthaben_delta,
            xp_delta=-original.xp_delta,
            idempotenz_schluessel=schluessel,
            storno_von=original,
            quelle_modul=original.quelle_modul,
            referenz_typ=original.referenz_typ,
            referenz_id=original.referenz_id,
            begruendung=begruendung,
            erstellt_von=_benutzer(akteur),
        )
        return _speichern(buchung, akteur, "punkte.storniert")


# --- intern ----------------------------------------------------------------------------------


def _speichern(buchung, akteur, aktion):
    try:
        with transaction.atomic():
            buchung.save()
    except IntegrityError:
        # Schlüssel parallel vergeben (nur ohne Schreibsperre möglich, z. B. andere DB)
        bestehend = _bestehende(buchung.idempotenz_schluessel, kind=buchung.kind, art=buchung.art)
        if bestehend is None:
            raise
        return bestehend
    details = {
        "art": buchung.art,
        "guthaben_delta": buchung.guthaben_delta,
        "xp_delta": buchung.xp_delta,
        "schluessel": buchung.idempotenz_schluessel,
        "quelle_modul": buchung.quelle_modul,
    }
    if buchung.storno_von_id:
        details["storno_von"] = buchung.storno_von_id
    if buchung.begruendung:
        details["begruendung"] = buchung.begruendung
    audit.protokollieren(aktion, akteur=akteur, objekt=buchung, kind=buchung.kind, details=details)
    ereignisse.veroeffentlichen(
        GEBUCHT,
        daten={
            "buchung": buchung.pk,
            "kind": str(buchung.kind.pk),
            "art": buchung.art,
            "guthaben_delta": buchung.guthaben_delta,
            "xp_delta": buchung.xp_delta,
            "bezugsdatum": buchung.bezugsdatum.isoformat(),
            "quelle_modul": buchung.quelle_modul,
            "storno_von": buchung.storno_von_id,
        },
        schluessel=f"{GEBUCHT}:{buchung.pk}",
        kind=buchung.kind,
    )
    return buchung


def _bestehende(schluessel, *, kind, art):
    bestehend = Buchung.objects.filter(idempotenz_schluessel=schluessel).first()
    if bestehend is not None and (bestehend.kind_id != kind.pk or bestehend.art != art):
        raise IdempotenzKonflikt(
            f"Schlüssel '{schluessel}' gehört zu Buchung {bestehend.pk} ({bestehend.art})"
        )
    return bestehend


def schreibsperre(kind):
    """Serialisiert schreibende Vorgänge eines Kindes (Buchungen, Einlöseanträge).

    Muss innerhalb von ``transaction.atomic()`` laufen. SQLite: Die Sperre hält schon das
    ``BEGIN IMMEDIATE`` der **äußersten** Transaktion (``transaction_mode`` gilt für jede
    äußerste ``atomic()``-Ebene, auch wenn ein Aufrufer sie öffnet); hier wird nur die
    Konfiguration geprüft. Andere DBs: Zeilensperre auf das Kind. Öffentlich, damit Fach-Module
    (belohnung) dieselbe Regel nutzen statt sie zu kopieren (Review AP19, B-10).
    """
    if not connection.in_atomic_block:
        raise ImproperlyConfigured("schreibsperre nur innerhalb transaction.atomic()")
    if connection.vendor == "sqlite":
        modus = connection.settings_dict.get("OPTIONS", {}).get("transaction_mode")
        if str(modus).upper() != "IMMEDIATE":
            raise ImproperlyConfigured("punkte braucht SQLite transaction_mode IMMEDIATE")
    else:  # pragma: no cover - Produktion ist SQLite
        get_user_model().objects.select_for_update().filter(pk=kind.pk).first()


def _art_pruefen(art):
    try:
        return Art(art)
    except ValueError:
        raise UngueltigeBuchung(f"Unbekannte Buchungsart '{art}'") from None


def _betrag_pruefen(art, punkte):
    if not isinstance(punkte, int) or isinstance(punkte, bool):
        raise UngueltigeBuchung("punkte muss eine ganze Zahl sein")
    if art == Art.KORREKTUR:
        if punkte == 0:
            raise UngueltigeBuchung("Korrektur mit 0 Punkten")
    elif punkte <= 0:
        raise UngueltigeBuchung(f"{art.label}: punkte muss > 0 sein")
    return punkte


def _text_pruefen(name, wert, max_laenge, *, pflicht):
    if not isinstance(wert, str):
        raise UngueltigeBuchung(f"{name} muss Text sein")
    wert = wert.strip()
    if pflicht and not wert:
        raise UngueltigeBuchung(f"{name} ist Pflicht")
    if len(wert) > max_laenge:
        raise UngueltigeBuchung(f"{name} ist zu lang (max. {max_laenge})")
    return wert


def _referenz(referenz, referenz_typ, referenz_id):
    if referenz is not None:
        if not isinstance(referenz, models.Model) or referenz.pk is None:
            raise UngueltigeBuchung("referenz muss eine gespeicherte Modell-Instanz sein")
        referenz_typ, referenz_id = referenz._meta.label_lower, referenz.pk
    referenz_typ = _text_pruefen("referenz_typ", referenz_typ, 60, pflicht=False)
    referenz_id = _text_pruefen("referenz_id", str(referenz_id), 40, pflicht=False)
    return referenz_typ, referenz_id


def _kind_pruefen(kind):
    if getattr(kind, "pk", None) is None or getattr(kind, "rolle", None) != "kind":
        raise UngueltigeBuchung("Buchungen gibt es nur für Kinder")


def _akteur(von, art):
    akteur = audit.aktueller_akteur() if von is audit.AKTUELL else von
    if akteur is not None and art in NUR_ELTERN and getattr(akteur, "rolle", None) != "eltern":
        raise PermissionDenied(f"{Art(art).label} dürfen nur Eltern buchen")
    return akteur


def _benutzer(akteur):
    """``erstellt_von``: nur echte Benutzer (Audit nimmt auch Akteure ohne Modell)."""
    return akteur if isinstance(akteur, models.Model) else None
