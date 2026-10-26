"""Schreibende Schnittstelle von familienziel (AP29).

- ``erfolg_pruefen(iso)``: Ziel + Bedingung erfüllt -> Status ``erreicht`` **genau einmal**
  (bedingtes Update ``laufend -> erreicht``; nur der Gewinner veröffentlicht die Ereignisse).
- ``erfolg_nach_ereignis``: synchroner Handler für ``punkte.gebucht`` und ``aktivitaet.erfasst``.
- ``sicherstellen(jetzt)``: Job ``familienwoche_sicherstellen`` (idempotent, Catch-up): legt
  Wochen an, schließt Abstimmungen, wertet Wochen aus, schaltet das Großziel frei.
- ``stimme_abgeben(kind, belohnung)``; Eltern: ``belohnung_speichern``, ``belohnung_loeschen``,
  ``woche_festlegen`` (Ziel/Belohnung, auch Gleichstand), ``woche_einloesen``,
  ``grossziel_einloesen``.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta

from django.db import IntegrityError, transaction

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.konten import selectors as konten

from . import events, selectors, zeitplan
from .models import (
    AbstimmungStatus,
    Familienbelohnung,
    Familienwoche,
    Grossziel,
    Stimme,
    WochenStatus,
)

logger = logging.getLogger("nestwerk.familienziel")


class FamilienzielFehler(ValueError):
    """Fachlicher Fehler mit deutscher Meldung."""


def _nur_eltern(von):
    if getattr(von, "rolle", None) != "eltern":
        raise FamilienzielFehler("Das dürfen nur Eltern.")


def _iso(zeile: Familienwoche) -> IsoWoche:
    return IsoWoche(zeile.iso_jahr, zeile.iso_woche)


def _melden(zeile, jetzt) -> bool:
    """Nur aktuelle und letzte Woche lösen Benachrichtigungen aus (kein Lärm beim Catch-up)."""
    return zeile.montag >= IsoWoche.von(jetzt).montag - timedelta(days=7)


# --- Wochen ---------------------------------------------------------------------------------


def woche_sicherstellen(iso: IsoWoche) -> tuple[Familienwoche, bool]:
    """Legt die Zeile der Woche an (Snapshot des Ziels). ``(zeile, neu)``."""
    zeile = selectors.woche(iso)
    if zeile is not None:
        return zeile, False
    try:
        with transaction.atomic():
            zeile = Familienwoche.objects.create(
                iso_jahr=iso.jahr,
                iso_woche=iso.woche,
                montag=iso.montag,
                ziel_punkte=selectors.wochenziel_start(),
            )
        return zeile, True
    except IntegrityError:
        return selectors.woche(iso), False


def _kinder_ereignisse(typ, schluessel, daten):
    for kind in konten.aktive_kinder():
        ereignisse.veroeffentlichen(
            typ, kind=kind, daten=daten, schluessel=f"{schluessel}:{kind.pk}"
        )


def _belohnung_titel(zeile):
    return zeile.belohnung.titel if zeile.belohnung_id else "Wochenziel"


def erfolg_pruefen(iso: IsoWoche, jetzt=None, *, melden=None) -> bool:
    """``True``, wenn *dieser* Aufruf die Woche auf ``erreicht`` gesetzt hat."""
    jetzt = jetzt or zeit.jetzt()
    zeile = selectors.woche(iso)
    if zeile is None or zeile.status != WochenStatus.LAUFEND or zeile.montag > zeit.heute(jetzt):
        return False
    if not selectors.stand(iso, zeile.ziel_punkte).erreichbar:
        return False
    with transaction.atomic():
        geaendert = Familienwoche.objects.filter(pk=zeile.pk, status=WochenStatus.LAUFEND).update(
            status=WochenStatus.ERREICHT, erreicht_am=jetzt
        )
        if geaendert != 1:
            return False
        zeile.refresh_from_db()
        if melden is None:
            melden = _melden(zeile, jetzt)
        if melden:
            titel = _belohnung_titel(zeile)
            daten = {"belohnung": titel, "ziel": zeile.ziel_punkte, "woche": str(iso)}
            schluessel = f"{events.ERREICHT}:{iso}"
            ereignisse.veroeffentlichen(events.ERREICHT, daten=daten, schluessel=schluessel)
            _kinder_ereignisse(events.ERREICHT_KIND, f"{events.ERREICHT_KIND}:{iso}", daten)
        grossziel_pruefen(jetzt, melden=melden)
    return True


def erfolg_nach_ereignis(ereignis):
    """Synchroner Handler (``punkte.gebucht``, ``aktivitaet.erfasst``). Savepoint: ein Fehler
    kippt die Buchung nicht, der Job holt es nach."""
    try:
        with transaction.atomic():
            daten = ereignis.daten or {}
            tag = daten.get("bezugsdatum") or daten.get("datum")
            jetzt = zeit.jetzt()
            iso = IsoWoche.von(date.fromisoformat(tag)) if tag else IsoWoche.von(jetzt)
            if iso == IsoWoche.von(jetzt):
                woche_sicherstellen(iso)
            erfolg_pruefen(iso, jetzt)
    except Exception:
        logger.exception("Familienziel nach Ereignis %s nicht geprüft", ereignis.pk)


# --- Großziel -------------------------------------------------------------------------------


def grossziel_pruefen(jetzt=None, *, melden=True):
    """Schaltet das Großziel frei, wenn seit dem letzten Großziel genug Wochen in Folge erreicht
    wurden (neutrale Wochen zählen nicht, brechen nicht). Idempotent (unique je Woche).

    Review AP31: Auslösende Woche ist die **jüngste** erreichte Woche der laufenden Folge, und je
    Aufruf entsteht höchstens ein Großziel. Senken Eltern ``familienziel.grossziel_serie`` unter
    die schon erreichte Folge, gibt es genau ein Großziel (nicht rückwirkend eines je Teilfolge)."""
    jetzt = jetzt or zeit.jetzt()
    noetig = einstellungen.wert("familienziel.grossziel_serie")
    letzte = (
        Grossziel.objects.select_related("ausloesende_woche")
        .order_by("-ausloesende_woche__montag")
        .first()
    )
    qs = Familienwoche.objects.order_by("montag")
    if letzte:
        qs = qs.filter(montag__gt=letzte.ausloesende_woche.montag)
    zaehler, vorher, anker = 0, None, None
    for zeile in qs:
        luecke = vorher is not None and zeile.montag != vorher + timedelta(days=7)
        if luecke or zeile.status in (WochenStatus.VERFEHLT, WochenStatus.LAUFEND):
            if anker is not None and zaehler >= noetig:  # Folge endet: geschafft?
                break
            zaehler, anker = 0, None
            if zeile.status == WochenStatus.LAUFEND:
                break
        vorher = zeile.montag
        if zeile.status == WochenStatus.ERREICHT:
            zaehler += 1
            anker = zeile
    if anker is not None and zaehler >= noetig:
        return _grossziel_anlegen(anker, jetzt, melden)
    return None


def _grossziel_anlegen(zeile, jetzt, melden):
    wahl = Familienbelohnung.objects.filter(aktiv=True, ist_grossziel=True).first()
    name = wahl.titel if wahl else einstellungen.wert("familienziel.grossziel_name")
    with transaction.atomic():
        grossziel, neu = Grossziel.objects.get_or_create(
            ausloesende_woche=zeile,
            defaults={"belohnung": wahl, "name": name[:60], "freigeschaltet_am": jetzt},
        )
        if neu and melden:
            daten = {"grossziel": name, "woche": str(_iso(zeile))}
            ereignisse.veroeffentlichen(
                events.GROSSZIEL, daten=daten, schluessel=f"{events.GROSSZIEL}:{_iso(zeile)}"
            )
            _kinder_ereignisse(
                events.GROSSZIEL_KIND, f"{events.GROSSZIEL_KIND}:{_iso(zeile)}", daten
            )
    return grossziel if neu else None


# --- Abstimmung -----------------------------------------------------------------------------


def stimme_abgeben(kind, belohnung_id, jetzt=None) -> Stimme:
    """Eine Stimme je Kind und Zielwoche; Ändern ist bis zum Abstimmungsende möglich."""
    jetzt = jetzt or zeit.jetzt()
    if getattr(kind, "rolle", None) != "kind" or not kind.aktiv:
        raise FamilienzielFehler("Nur Kinder stimmen ab.")
    ziel = IsoWoche.von(jetzt).naechste()
    if not zeitplan.abstimmung_offen_zeitlich(ziel, jetzt):
        raise FamilienzielFehler("Gerade läuft keine Abstimmung.")
    with transaction.atomic():
        zeile, _ = woche_sicherstellen(ziel)
        if zeile.abstimmung_status != AbstimmungStatus.OFFEN:
            raise FamilienzielFehler("Die Abstimmung ist schon beendet.")
        wahl = selectors.wahl_optionen().filter(pk=belohnung_id).first()
        if wahl is None:
            raise FamilienzielFehler("Diese Belohnung steht nicht zur Wahl.")
        stimme, _ = Stimme.objects.update_or_create(
            woche=zeile, kind=kind, defaults={"belohnung": wahl, "abgegeben_am": jetzt}
        )
    return stimme


def abstimmung_abschliessen(zeile: Familienwoche, jetzt=None) -> str | None:
    """Wertet die Abstimmung aus, sobald das Fenster vorbei ist. Gibt den neuen Status zurück
    (oder ``None``, wenn nichts zu tun war). Bedingtes Update: genau einmal."""
    jetzt = jetzt or zeit.jetzt()
    iso = _iso(zeile)
    if zeile.abstimmung_status != AbstimmungStatus.OFFEN:
        return None
    if jetzt < zeitplan.abstimmung_fenster(iso)[1]:
        return None
    erlaubt = set(selectors.wahl_optionen().values_list("pk", flat=True))
    zaehlung = Counter(
        b for b in zeile.stimmen.values_list("belohnung_id", flat=True) if b in erlaubt
    )
    belohnung_id, hinweis = None, ""
    if zaehlung:
        spitze = max(zaehlung.values())
        sieger = sorted(b for b, n in zaehlung.items() if n == spitze)
        if len(sieger) == 1:
            belohnung_id = sieger[0]
        else:
            titel = Familienbelohnung.objects.filter(pk__in=sieger).values_list("titel", flat=True)
            hinweis = "Gleichstand zwischen " + ", ".join(sorted(titel)) + ". Bitte entscheidet."
    else:
        vorher = selectors.woche(iso.vorherige())
        if vorher is not None and vorher.belohnung_id in erlaubt:
            belohnung_id = vorher.belohnung_id
        else:
            hinweis = "Niemand hat abgestimmt. Bitte wählt das Ziel der Woche."
    with transaction.atomic():
        if belohnung_id is not None:
            geaendert = Familienwoche.objects.filter(
                pk=zeile.pk, abstimmung_status=AbstimmungStatus.OFFEN
            ).update(abstimmung_status=AbstimmungStatus.GESCHLOSSEN, belohnung_id=belohnung_id)
            neu = AbstimmungStatus.GESCHLOSSEN
        else:
            geaendert = Familienwoche.objects.filter(
                pk=zeile.pk, abstimmung_status=AbstimmungStatus.OFFEN
            ).update(abstimmung_status=AbstimmungStatus.GLEICHSTAND)
            neu = AbstimmungStatus.GLEICHSTAND
            if geaendert and zeile.montag >= IsoWoche.von(jetzt).montag:
                ereignisse.veroeffentlichen(
                    events.ABSTIMMUNG_GLEICHSTAND,
                    daten={"hinweis": hinweis, "woche": str(iso)},
                    schluessel=f"{events.ABSTIMMUNG_GLEICHSTAND}:{iso}",
                )
    return neu if geaendert else None


# --- Wochenabschluss ------------------------------------------------------------------------


def woche_abschliessen(zeile: Familienwoche, jetzt=None) -> str | None:
    jetzt = jetzt or zeit.jetzt()
    iso = _iso(zeile)
    if zeile.finalisiert_am is not None or jetzt < zeitplan.abschluss_zeitpunkt(iso):
        return None
    zeile.refresh_from_db()
    if zeile.status == WochenStatus.LAUFEND:
        erfolg_pruefen(iso, jetzt)
        zeile.refresh_from_db()
    with transaction.atomic():
        if zeile.status == WochenStatus.LAUFEND:
            st = selectors.stand(iso, zeile.ziel_punkte)
            neu = WochenStatus.NEUTRAL if st.alle_pausiert else WochenStatus.VERFEHLT
            Familienwoche.objects.filter(pk=zeile.pk, status=WochenStatus.LAUFEND).update(
                status=neu
            )
        Familienwoche.objects.filter(pk=zeile.pk, finalisiert_am__isnull=True).update(
            finalisiert_am=jetzt
        )
        grossziel_pruefen(jetzt, melden=_melden(zeile, jetzt))
    zeile.refresh_from_db()
    return zeile.status


def sicherstellen(jetzt=None) -> dict:
    """Job ``familienwoche_sicherstellen``: idempotent, mit Catch-up über beliebig viele Wochen."""
    jetzt = jetzt or zeit.jetzt()
    heute = IsoWoche.von(jetzt)
    vor = Familienwoche.objects.filter(montag__lte=heute.montag).order_by("-montag").first()
    start = IsoWoche.von(vor.montag).naechste() if vor else heute
    wochen = {
        IsoWoche(j, w)
        for j, w in Familienwoche.objects.filter(finalisiert_am__isnull=True).values_list(
            "iso_jahr", "iso_woche"
        )
    }
    woche = start
    while woche <= heute:
        wochen.add(woche)
        woche = woche.naechste()
    naechste = heute.naechste()
    if jetzt >= zeitplan.abstimmung_fenster(naechste)[0]:
        wochen.add(naechste)
    info = {"angelegt": 0, "abstimmungen": 0, "abgeschlossen": 0}
    for iso in sorted(wochen):
        zeile, neu = woche_sicherstellen(iso)
        info["angelegt"] += neu
        if neu and iso == naechste:
            _abstimmung_ankuendigen(zeile, jetzt)
        if abstimmung_abschliessen(zeile, jetzt):
            info["abstimmungen"] += 1
        if iso <= heute:
            if woche_abschliessen(selectors.woche(iso), jetzt):
                info["abgeschlossen"] += 1
            erfolg_pruefen(iso, jetzt)
    with transaction.atomic():
        grossziel_pruefen(jetzt)
    return info


def _abstimmung_ankuendigen(zeile, jetzt):
    if not zeitplan.abstimmung_offen_zeitlich(_iso(zeile), jetzt):
        return
    iso = _iso(zeile)
    with transaction.atomic():
        _kinder_ereignisse(
            events.ABSTIMMUNG_OFFEN,
            f"{events.ABSTIMMUNG_OFFEN}:{iso}",
            {"woche": str(iso)},
        )


# --- Eltern ---------------------------------------------------------------------------------


def belohnung_speichern(*, von, titel, symbol="", ist_grossziel=False, aktiv=True, pk=None):
    _nur_eltern(von)
    titel = (titel or "").strip()
    if not titel or len(titel) > 60:
        raise FamilienzielFehler("Der Titel ist Pflicht (höchstens 60 Zeichen).")
    with transaction.atomic():
        if pk is None:
            letzte = Familienbelohnung.objects.order_by("-reihenfolge").first()
            belohnung = Familienbelohnung.objects.create(
                titel=titel,
                symbol=symbol,
                ist_grossziel=ist_grossziel,
                aktiv=aktiv,
                reihenfolge=(letzte.reihenfolge + 1) if letzte else 1,
            )
            aktion = "familienziel.belohnung_angelegt"
        else:
            belohnung = Familienbelohnung.objects.get(pk=pk)
            belohnung.titel, belohnung.symbol = titel, symbol
            belohnung.ist_grossziel, belohnung.aktiv = ist_grossziel, aktiv
            belohnung.save()
            aktion = "familienziel.belohnung_geaendert"
        audit.protokollieren(aktion, akteur=von, objekt=belohnung, details={"titel": titel})
    return belohnung


def belohnung_aktiv_setzen(belohnung, aktiv, *, von):
    _nur_eltern(von)
    belohnung.aktiv = aktiv
    belohnung.save(update_fields=["aktiv"])
    audit.protokollieren(
        "familienziel.belohnung_geaendert", akteur=von, objekt=belohnung, details={"aktiv": aktiv}
    )


def belohnung_loeschen(belohnung, *, von) -> bool:
    """Löscht eine unbenutzte Belohnung; benutzte (Wochen, Stimmen) werden nur deaktiviert.
    ``True`` = gelöscht."""
    _nur_eltern(von)
    benutzt = belohnung.wochen.exists() or belohnung.stimmen.exists()
    pk, titel = belohnung.pk, belohnung.titel
    if benutzt:
        belohnung_aktiv_setzen(belohnung, False, von=von)
        return False
    belohnung.delete()
    audit.protokollieren(
        "familienziel.belohnung_geloescht",
        akteur=von,
        objekt_typ="familienziel.familienbelohnung",
        objekt_id=pk,
        details={"titel": titel},
    )
    return True


def woche_festlegen(zeile, *, von, belohnung=None, ziel_punkte=None, jetzt=None):
    """Eltern setzen Belohnung und/oder Ziel einer noch laufenden Woche (auch Gleichstand).
    Eine gewählte Belohnung beendet die Abstimmung (``eltern_entschieden``)."""
    _nur_eltern(von)
    jetzt = jetzt or zeit.jetzt()
    with transaction.atomic():
        zeile = Familienwoche.objects.select_for_update().get(pk=zeile.pk)
        if zeile.status != WochenStatus.LAUFEND:
            raise FamilienzielFehler("Diese Woche ist schon ausgewertet.")
        details = {"woche": str(_iso(zeile))}
        if ziel_punkte is not None:
            if not 1 <= int(ziel_punkte) <= 100000:
                raise FamilienzielFehler("Das Ziel muss zwischen 1 und 100000 Punkten liegen.")
            zeile.ziel_punkte = int(ziel_punkte)
            details["ziel_punkte"] = zeile.ziel_punkte
        if belohnung is not None:
            if not belohnung.aktiv or belohnung.ist_grossziel:
                raise FamilienzielFehler("Diese Belohnung steht nicht zur Wahl.")
            zeile.belohnung = belohnung
            zeile.abstimmung_status = AbstimmungStatus.ELTERN_ENTSCHIEDEN
            details["belohnung"] = belohnung.titel
        zeile.save(update_fields=["ziel_punkte", "belohnung", "abstimmung_status"])
        audit.protokollieren(
            "familienziel.woche_festgelegt", akteur=von, objekt=zeile, details=details
        )
    erfolg_pruefen(_iso(zeile), jetzt)
    return zeile


def woche_einloesen(zeile, *, von, jetzt=None):
    _nur_eltern(von)
    if zeile.status != WochenStatus.ERREICHT:
        raise FamilienzielFehler("Nur erreichte Ziele lassen sich einlösen.")
    Familienwoche.objects.filter(pk=zeile.pk, eingeloest_am__isnull=True).update(
        eingeloest_am=jetzt or zeit.jetzt()
    )


def grossziel_einloesen(grossziel, *, von, jetzt=None):
    _nur_eltern(von)
    Grossziel.objects.filter(pk=grossziel.pk, eingeloest_am__isnull=True).update(
        eingeloest_am=jetzt or zeit.jetzt()
    )
