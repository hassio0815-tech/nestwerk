"""Schreibende Schnittstelle von sondertag (AP27, ARCHITECTURE 7.6, Entscheidungen 1/27, K6).

- **Anspruch** entsteht aus ``meilenstein.erreicht`` mit ``belohnungsart = sondertag``
  (synchroner Handler, idempotent über ``unique(meilenstein)``). Früh verdiente Ansprüche bleiben
  als "verdient, einlösbar ab Datum X" stehen (Warteschlange, ``grenzen``).
- **Wunsch** (K6): sofort möglich (Einstellung), nur für den ersten offenen Anspruch des Kindes;
  Freitext + Begleitung Mama/Papa/egal. Beide Eltern bekommen ``sondertag.wunsch``.
- **Annahme** durch einen Elternteil erst ab ``einloesbar_ab``; der Service rechnet in derselben
  Transaktion neu (serverseitige Durchsetzung). Annehmender Elternteil = Begleitung; Übergabe an
  den anderen Elternteil ändert nur ``begleitung`` (Audit).
- **Bezugsdatum** für Abstand und App-Jahr = Annahmedatum; Eltern können es korrigieren. Nach
  jeder Annahme/Korrektur/Historien-Änderung werden alle offenen Ansprüche neu eingeplant.
- **Historie** editierbar, inkl. manueller Einträge (z. B. Sondertag vor Go-live).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import formats
from django.utils.translation import gettext, gettext_noop
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.konten import selectors as konten
from apps.spielregeln.services import datum_parameter

from . import events, grenzen
from .models import ANGENOMMEN, OFFEN, BegleitungWunsch, Quelle, SondertagAnspruch, Status

logger = logging.getLogger("nestwerk.sondertag")

NOTIZ_MAX = 200


class SondertagFehler(ValueError):
    """Fachlicher Fehler (Meldung ist für Kinder bzw. Eltern lesbar)."""


# --- Grenzen und Warteschlange ----------------------------------------------------------------


def regeln() -> grenzen.Regeln:
    w = einstellungen.werte(
        "allgemein.go_live_datum", "sondertag.max_pro_appjahr", "sondertag.mindestabstand_tage"
    )
    return grenzen.Regeln(
        go_live=w["allgemein.go_live_datum"],
        max_pro_jahr=w["sondertag.max_pro_appjahr"],
        abstand=w["sondertag.mindestabstand_tage"],
    )


def angenommene_daten(kind, *, ausser=None) -> list[date]:
    qs = SondertagAnspruch.objects.filter(
        kind=kind, status__in=ANGENOMMEN, annahme_datum__isnull=False
    )
    if ausser is not None:
        qs = qs.exclude(pk=ausser)
    return list(qs.values_list("annahme_datum", flat=True))


def offene(kind):
    return SondertagAnspruch.objects.filter(kind=kind, status__in=OFFEN).order_by(
        "verdient_am", "id"
    )


def plan(kind, heute: date | None = None, *, r: grenzen.Regeln | None = None) -> list[tuple]:
    """``[(anspruch, einloesbar_ab), ...]`` der offenen Ansprüche in Warteschlangen-Reihenfolge
    (live gerechnet, ohne zu speichern)."""
    heute = heute or zeit.heute()
    r = r or regeln()
    liste = list(offene(kind))
    daten = grenzen.plan(
        [zeit.heute(a.verdient_am) for a in liste], angenommene_daten(kind), r, heute
    )
    return list(zip(liste, daten, strict=True))


def neu_berechnen(kind, heute: date | None = None) -> list[tuple]:
    """Speichert ``einloesbar_ab`` aller offenen Ansprüche (nach Annahme/Korrektur/neu)."""
    ergebnis = plan(kind, heute)
    for anspruch, ab in ergebnis:
        if anspruch.einloesbar_ab != ab:
            SondertagAnspruch.objects.filter(pk=anspruch.pk).update(einloesbar_ab=ab)
            anspruch.einloesbar_ab = ab
    return ergebnis


def datum_text(tag: date | None) -> str:
    """Kurzes Datum in der aktiven Sprache (de: 30.10.2026, en: 10/30/2026)."""
    return formats.date_format(tag, "SHORT_DATE_FORMAT") if tag else ""


def _hinweis_daten(msgid: str, **parameter) -> dict:
    """Hinweis als msgid + Parameter (gerendert in der Sprache des Empfängers); ``hinweis``
    bleibt als deutscher Rückfall für ältere Leser. Datumswerte siehe ``datum_parameter``."""
    return {
        "hinweis": msgid % parameter,
        "hinweis_msgid": msgid,
        "hinweis_parameter": parameter,
    }


# Platzhalter ``datum`` (deutsch) und ``datum_en`` (englisch): siehe spielregeln.services.
H_AB_SCHICKEN = gettext_noop(
    # xgettext:no-python-format
    "Einlösbar ab %(datum)s. Deinen Wunsch kannst du schon jetzt schicken."
)
# xgettext:no-python-format
H_IN_REIHE = gettext_noop("Er wartet in der Reihe, einlösbar ab %(datum)s.")
# xgettext:no-python-format
H_AB = gettext_noop("Einlösbar ab %(datum)s.")
# xgettext:no-python-format
H_ANNEHMEN_AB = gettext_noop("Annehmen könnt ihr ihn ab %(datum)s.")
H_WUENSCHEN = gettext_noop("Du darfst dir jetzt etwas wünschen!")
H_ANNEHMEN_JETZT = gettext_noop("Ihr könnt ihn jetzt annehmen.")
H_ELTERN_KOENNEN = gettext_noop("Deine Eltern können deinen Wunsch jetzt annehmen.")
H_WUNSCH_EINLOESBAR = gettext_noop("Wunsch: „%(wunsch)s“. Ihr könnt ihn jetzt annehmen.")
H_KEIN_WUNSCH = gettext_noop("Noch kein Wunsch gesendet.")
TITEL_MANUELL = gettext_noop("manuell erfasst")
TITEL_MEILENSTEIN = gettext_noop("Meilenstein")


def _hinweis(ab: date, heute: date) -> dict:
    if ab <= heute:
        return _hinweis_daten(H_WUENSCHEN)
    return _hinweis_daten(H_AB_SCHICKEN, **datum_parameter("datum", ab))


# --- Anspruch aus Meilenstein -----------------------------------------------------------------


def nach_meilenstein(ereignis):
    """Synchroner Handler auf ``meilenstein.erreicht``: nur ``belohnungsart = sondertag``."""
    daten = ereignis.daten or {}
    if daten.get("belohnungsart") != events.BELOHNUNGSART or ereignis.kind_id is None:
        return None
    erreicht = daten.get("erreicht")
    if not isinstance(erreicht, int):
        logger.warning("meilenstein.erreicht ohne Fakt-ID (Ereignis %s)", ereignis.pk)
        return None
    titel = str(daten.get("meilenstein") or TITEL_MEILENSTEIN)[:80]
    return anspruch_anlegen(ereignis.kind, erreicht, titel=titel)


def anspruch_anlegen(kind, meilenstein_id: int, *, titel="", jetzt: datetime | None = None):
    """Anspruch zu einem Meilenstein-Fakt (idempotent: doppelte Ereignisse -> ein Anspruch)."""
    jetzt = jetzt or zeit.jetzt()
    with transaction.atomic():
        vorhanden = SondertagAnspruch.objects.filter(meilenstein_id=meilenstein_id).first()
        if vorhanden is not None:
            return vorhanden
        try:
            with transaction.atomic():
                anspruch = SondertagAnspruch.objects.create(
                    kind=kind,
                    meilenstein_id=meilenstein_id,
                    quelle=Quelle.MEILENSTEIN,
                    titel=titel,
                    verdient_am=jetzt,
                )
        except IntegrityError:  # parallel angelegt
            return SondertagAnspruch.objects.get(meilenstein_id=meilenstein_id)
        heute = zeit.heute(jetzt)
        eingeplant = dict((a.pk, ab) for a, ab in neu_berechnen(kind, heute))
        ab = eingeplant.get(anspruch.pk, heute)
        anspruch.einloesbar_ab = ab
        erster = next(iter(eingeplant), None) == anspruch.pk
        if erster and ab <= heute:  # sofort einlösbar: die Freischaltung ist die Meldung
            SondertagAnspruch.objects.filter(pk=anspruch.pk).update(einloesbar_gemeldet_am=jetzt)
        audit.protokollieren(
            "sondertag.verdient",
            akteur=None,
            objekt=anspruch,
            kind=kind,
            details={"meilenstein": meilenstein_id, "einloesbar_ab": ab.isoformat()},
        )
        hinweis = (
            _hinweis(ab, heute)
            if erster
            else _hinweis_daten(H_IN_REIHE, **datum_parameter("datum", ab))
        )
        ereignisse.veroeffentlichen(
            events.FREIGESCHALTET,
            kind=kind,
            daten={
                "anspruch": anspruch.pk,
                "titel": titel,
                "einloesbar_ab": ab.isoformat(),
                **hinweis,
            },
            schluessel=f"{events.FREIGESCHALTET}:{anspruch.pk}",
        )
        ereignisse.veroeffentlichen(
            events.VERDIENT_ELTERN,
            kind=kind,
            daten={
                "anspruch": anspruch.pk,
                "titel": titel,
                **_hinweis_daten(H_AB, **datum_parameter("datum", ab)),
            },
            schluessel=f"{events.VERDIENT_ELTERN}:{anspruch.pk}",
        )
    return anspruch


def nachholen() -> int:
    """Catch-up (Kommando ``sondertag_sicherstellen``): Ansprüche zu Sondertag-Meilensteinen,
    deren Ereignis verloren ging oder vor der Installation lag."""
    from apps.spielregeln import selectors as spielregeln

    neu = 0
    for kind in konten.aktive_kinder():
        for fakt in (
            spielregeln.meilensteine_erreicht(kind)
            .filter(regel__belohnungsart=events.BELOHNUNGSART, sondertag__isnull=True)
            .order_by("erreicht_am", "id")
        ):
            anspruch_anlegen(kind, fakt.pk, titel=fakt.regel.name, jetzt=fakt.erreicht_am)
            neu += 1
    return neu


def einloesbar_melden(jetzt: datetime | None = None) -> int:
    """Job (``sondertag_sicherstellen``): Wird der erste offene Anspruch eines Kindes einlösbar
    (Grenzen erlauben ihn ab heute), bekommen Kind und Eltern genau eine Meldung. Bedingtes Update
    auf ``einloesbar_gemeldet_am`` + Ereignis-Schlüssel: Doppellauf meldet nichts erneut."""
    jetzt = jetzt or zeit.jetzt()
    heute = zeit.heute(jetzt)
    gemeldet = 0
    for kind in konten.aktive_kinder():
        with transaction.atomic():
            geplant = plan(kind, heute)
            if not geplant:
                continue
            anspruch, ab = geplant[0]
            if ab > heute or anspruch.einloesbar_gemeldet_am is not None:
                continue
            if not SondertagAnspruch.objects.filter(
                pk=anspruch.pk, einloesbar_gemeldet_am__isnull=True, status__in=OFFEN
            ).update(einloesbar_gemeldet_am=jetzt):
                continue
            wunsch_da = anspruch.status == Status.WUNSCH_OFFEN
            ereignisse.veroeffentlichen(
                events.EINLOESBAR,
                kind=kind,
                daten={
                    "anspruch": anspruch.pk,
                    "titel": anspruch.titel,
                    **_hinweis_daten(H_ELTERN_KOENNEN if wunsch_da else H_WUENSCHEN),
                },
                schluessel=f"{events.EINLOESBAR}:{anspruch.pk}",
            )
            ereignisse.veroeffentlichen(
                events.EINLOESBAR_ELTERN,
                kind=kind,
                daten={
                    "anspruch": anspruch.pk,
                    "titel": anspruch.titel,
                    **(
                        _hinweis_daten(H_WUNSCH_EINLOESBAR, wunsch=anspruch.wunsch[:120])
                        if wunsch_da
                        else _hinweis_daten(H_KEIN_WUNSCH)
                    ),
                },
                schluessel=f"{events.EINLOESBAR_ELTERN}:{anspruch.pk}",
            )
            gemeldet += 1
    return gemeldet


# --- Wunsch (Kind) ----------------------------------------------------------------------------


def eltern_mit_label(label: str):
    """Aktiver Elternteil mit Rolle Mama/Papa oder ``None``."""
    for e in konten.aktive_eltern().select_related("elternprofil"):
        profil = getattr(e, "elternprofil", None)
        if profil is not None and profil.rolle_label == label:
            return e
    return None


def _begleitung_msgid(wunsch: str) -> tuple[str, dict]:
    """Begleitung als (msgid, Parameter); die Namen "Mama"/"Papa" übersetzt die Anzeige."""
    if wunsch in (BegleitungWunsch.MAMA, BegleitungWunsch.PAPA):
        e = eltern_mit_label(wunsch)
        label = _BEGLEITUNG_LABEL[wunsch]
        if e and e.anzeigename != label:
            return _BEGLEITUNG_MIT_NAME[wunsch], {"name": e.anzeigename}
        return label, {}
    return gettext_noop("egal"), {}


_BEGLEITUNG_LABEL = {
    BegleitungWunsch.MAMA: gettext_noop("Mama"),
    BegleitungWunsch.PAPA: gettext_noop("Papa"),
}
_BEGLEITUNG_MIT_NAME = {
    BegleitungWunsch.MAMA: gettext_noop("Mama (%(name)s)"),
    BegleitungWunsch.PAPA: gettext_noop("Papa (%(name)s)"),
}


def begleitung_text(wunsch: str) -> str:
    """Begleitung in der aktiven Sprache."""
    msgid, parameter = _begleitung_msgid(wunsch)
    return gettext(msgid) % parameter


def _begleitung_daten(wunsch: str) -> dict:
    """``begleitung`` als deutscher Rückfall plus msgid + Parameter für den Empfänger."""
    msgid, parameter = _begleitung_msgid(wunsch)
    return {
        "begleitung": msgid % parameter,
        "begleitung_msgid": msgid,
        "begleitung_parameter": parameter,
    }


def wunsch_senden(kind, anspruch, *, wunsch, begleitung, jetzt=None) -> SondertagAnspruch:
    """Kind schickt (oder ändert) seinen Wunsch für den ersten offenen Anspruch."""
    if getattr(kind, "rolle", None) != "kind":
        raise SondertagFehler(_("Nur Kinder schicken einen Sondertag-Wunsch."))
    jetzt = jetzt or zeit.jetzt()
    heute = zeit.heute(jetzt)
    text = " ".join((wunsch or "").split())
    max_zeichen = einstellungen.wert("sondertag.wunsch_max_zeichen")
    if not text:
        raise SondertagFehler(_("Schreib auf, was du dir wünschst."))
    if len(text) > max_zeichen:
        raise SondertagFehler(
            _("Dein Wunsch ist zu lang (höchstens %(max)s Zeichen).") % {"max": max_zeichen}
        )
    if begleitung not in BegleitungWunsch.values:
        raise SondertagFehler(_("Wähle, mit wem du den Tag verbringen möchtest."))
    with transaction.atomic():
        geplant = plan(kind, heute)
        if not geplant or geplant[0][0].pk != getattr(anspruch, "pk", anspruch):
            raise SondertagFehler(
                _("Für diesen Sondertag kannst du gerade keinen Wunsch schicken.")
            )
        anspruch, ab = geplant[0]
        if ab > heute and not einstellungen.wert("sondertag.wunsch_vor_einloesbar_erlaubt"):
            raise SondertagFehler(
                _("Wünschen kannst du dir etwas ab %(datum)s.") % {"datum": datum_text(ab)}
            )
        if anspruch.kind_id != kind.pk:
            raise SondertagFehler(_("Das ist nicht dein Sondertag."))
        erneut = anspruch.status == Status.WUNSCH_OFFEN
        SondertagAnspruch.objects.filter(pk=anspruch.pk, status__in=OFFEN).update(
            wunsch=text,
            begleitung_wunsch=begleitung,
            wunsch_am=jetzt,
            status=Status.WUNSCH_OFFEN,
            einloesbar_ab=ab,
        )
        anspruch.refresh_from_db()
        audit.protokollieren(
            "sondertag.wunsch_geaendert" if erneut else "sondertag.wunsch",
            akteur=kind,
            objekt=anspruch,
            kind=kind,
            details={"begleitung_wunsch": begleitung, "zeichen": len(text)},
        )
        ereignisse.veroeffentlichen(
            events.WUNSCH,
            kind=kind,
            akteur=kind,
            daten={
                "anspruch": anspruch.pk,
                "wunsch": text,
                **_begleitung_daten(begleitung),
                **(
                    _hinweis_daten(H_ANNEHMEN_JETZT)
                    if ab <= heute
                    else _hinweis_daten(H_ANNEHMEN_AB, **datum_parameter("datum", ab))
                ),
                "geaendert": erneut,
            },
        )
    return anspruch


# --- Eltern -----------------------------------------------------------------------------------


def _eltern_pruefen(von):
    if getattr(von, "rolle", None) != "eltern":
        raise SondertagFehler(_("Das dürfen nur Eltern."))


def _laden(anspruch) -> SondertagAnspruch:
    pk = getattr(anspruch, "pk", anspruch)
    gefunden = SondertagAnspruch.objects.select_for_update().filter(pk=pk).first()
    if gefunden is None:
        raise SondertagFehler(_("Diesen Sondertag gibt es nicht."))
    return gefunden


def annehmen(anspruch, *, von, heute: date | None = None) -> SondertagAnspruch:
    """ "Wunsch angenommen" (K6): nur ab ``einloesbar_ab`` und nur der erste offene Anspruch.
    Der annehmende Elternteil ist die Begleitung; Annahmedatum = heute (Bezugsdatum)."""
    _eltern_pruefen(von)
    heute = heute or zeit.heute()
    with transaction.atomic():
        anspruch = _laden(anspruch)
        if anspruch.status != Status.WUNSCH_OFFEN:
            raise SondertagFehler(_("Hier gibt es keinen offenen Wunsch."))
        geplant = plan(anspruch.kind, heute)
        if not geplant or geplant[0][0].pk != anspruch.pk:
            raise SondertagFehler(_("Ein früherer Sondertag dieses Kindes ist noch offen."))
        ab = geplant[0][1]
        if ab > heute:
            raise SondertagFehler(_("Annehmen geht erst ab %(datum)s.") % {"datum": datum_text(ab)})
        r, daten = regeln(), angenommene_daten(anspruch.kind)
        if not grenzen.erlaubt(heute, daten, r):  # z. B. später datierte Korrektur
            frei = grenzen.einloesbar_ab(heute, daten, r)
            raise SondertagFehler(
                _("Annehmen geht erst ab %(datum)s.") % {"datum": datum_text(frei)}
            )
        SondertagAnspruch.objects.filter(pk=anspruch.pk, status=Status.WUNSCH_OFFEN).update(
            status=Status.ANGENOMMEN,
            angenommen_von=von,
            begleitung=von,
            annahme_datum=heute,
            einloesbar_ab=ab,
        )
        anspruch.refresh_from_db()
        audit.protokollieren(
            "sondertag.angenommen",
            akteur=von,
            objekt=anspruch,
            kind=anspruch.kind,
            details={"annahme_datum": heute.isoformat(), "begleitung": str(von.pk)},
        )
        ereignisse.veroeffentlichen(
            events.ANGENOMMEN,
            kind=anspruch.kind,
            akteur=von,
            daten={
                "anspruch": anspruch.pk,
                "wunsch": anspruch.wunsch[:200],
                "begleitung": von.name_mit_wappen,
            },
            schluessel=f"{events.ANGENOMMEN}:{anspruch.pk}",
        )
        neu_berechnen(anspruch.kind, heute)
    return anspruch


def _anderer_elternteil(an):
    pk = getattr(an, "pk", an)
    try:
        eltern = konten.aktive_eltern().filter(pk=pk).first()
    except (ValueError, ValidationError):
        eltern = None
    if eltern is None:
        raise SondertagFehler(_("Bitte einen Elternteil wählen."))
    return eltern


def uebergeben(anspruch, *, von, an) -> SondertagAnspruch:
    """Begleitung an einen anderen Elternteil übergeben (nur das Feld ``begleitung``, Audit)."""
    _eltern_pruefen(von)
    with transaction.atomic():
        anspruch = _laden(anspruch)
        if anspruch.status not in ANGENOMMEN:
            raise SondertagFehler(_("Übergeben geht erst nach der Annahme."))
        neu = _anderer_elternteil(an)
        if neu.pk == anspruch.begleitung_id:
            raise SondertagFehler(_("%(name)s begleitet schon.") % {"name": neu.anzeigename})
        alt = anspruch.begleitung_id
        SondertagAnspruch.objects.filter(pk=anspruch.pk).update(begleitung=neu)
        anspruch.refresh_from_db()
        audit.protokollieren(
            "sondertag.uebergeben",
            akteur=von,
            objekt=anspruch,
            kind=anspruch.kind,
            details={"alt": _json(alt), "neu": str(neu.pk)},
        )
        ereignisse.veroeffentlichen(
            events.UEBERGEBEN,
            kind=anspruch.kind,
            akteur=von,
            daten={"anspruch": anspruch.pk, "begleitung": neu.anzeigename},
        )
    return anspruch


def _datum(wert, feld, *, leer_erlaubt=False) -> date | None:
    if wert in (None, ""):
        if leer_erlaubt:
            return None
        raise SondertagFehler(_("%(feld)s: bitte ein Datum angeben.") % {"feld": feld})
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    try:
        return date.fromisoformat(str(wert).strip())
    except ValueError:
        raise SondertagFehler(_("%(feld)s: Datum im Format JJJJ-MM-TT.") % {"feld": feld}) from None


def _begleitung(wert):
    if wert in (None, ""):
        return None
    return _anderer_elternteil(wert)


def eintrag_aendern(
    anspruch,
    *,
    von,
    annahme_datum=None,
    begleitung=None,
    stattgefunden_am=None,
    notiz=None,
    heute: date | None = None,
) -> SondertagAnspruch:
    """Historie korrigieren (Audit): Bezugsdatum (Annahmedatum), Begleitung, Datum des Tages,
    Notiz. ``None`` = Feld unverändert. Danach werden offene Ansprüche neu eingeplant."""
    _eltern_pruefen(von)
    with transaction.atomic():
        anspruch = _laden(anspruch)
        if anspruch.status not in ANGENOMMEN:
            raise SondertagFehler(_("Nur angenommene oder vergangene Sondertage sind änderbar."))
        neu = {}
        if annahme_datum is not None:
            neu["annahme_datum"] = _datum(annahme_datum, _("Bezugsdatum"))
        if begleitung is not None:
            b = _begleitung(begleitung)
            neu["begleitung_id"] = b.pk if b else None
        if stattgefunden_am is not None:
            neu["stattgefunden_am"] = _datum(stattgefunden_am, _("Datum"), leer_erlaubt=True)
        if notiz is not None:
            notiz = notiz.strip()
            if len(notiz) > NOTIZ_MAX:
                raise SondertagFehler(_("Notiz: höchstens %(max)s Zeichen.") % {"max": NOTIZ_MAX})
            neu["notiz"] = notiz
        geaendert = {f: v for f, v in neu.items() if getattr(anspruch, f) != v}
        if not geaendert:
            return anspruch
        alt = {f: _json(getattr(anspruch, f)) for f in geaendert}
        SondertagAnspruch.objects.filter(pk=anspruch.pk).update(**geaendert)
        anspruch.refresh_from_db()
        audit.protokollieren(
            "sondertag.korrigiert",
            akteur=von,
            objekt=anspruch,
            kind=anspruch.kind,
            details={"alt": alt, "neu": {f: _json(v) for f, v in geaendert.items()}},
        )
        neu_berechnen(anspruch.kind, heute)
    return anspruch


def bezugsdatum_korrigieren(anspruch, datum, *, von, heute=None) -> SondertagAnspruch:
    return eintrag_aendern(anspruch, von=von, annahme_datum=datum, heute=heute)


def _json(wert):
    if isinstance(wert, date):
        return wert.isoformat()
    return str(wert) if isinstance(wert, uuid.UUID) else wert


def stattgefunden(anspruch, *, von, datum=None, heute: date | None = None) -> SondertagAnspruch:
    """Sondertag hat stattgefunden (optional mit Datum, Standard heute)."""
    _eltern_pruefen(von)
    tag = _datum(datum, _("Datum"), leer_erlaubt=True) or heute or zeit.heute()
    with transaction.atomic():
        anspruch = _laden(anspruch)
        if anspruch.status != Status.ANGENOMMEN:
            raise SondertagFehler(_("Erst annehmen, dann als erledigt markieren."))
        SondertagAnspruch.objects.filter(pk=anspruch.pk).update(
            status=Status.STATTGEFUNDEN, stattgefunden_am=tag
        )
        anspruch.refresh_from_db()
        audit.protokollieren(
            "sondertag.stattgefunden",
            akteur=von,
            objekt=anspruch,
            kind=anspruch.kind,
            details={"stattgefunden_am": tag.isoformat()},
        )
    return anspruch


def manuell_erfassen(
    kind, *, von, datum, begleitung=None, notiz="", heute: date | None = None
) -> SondertagAnspruch:
    """Historie nachtragen (z. B. Sondertag vor Go-live). Zählt für Abstand und App-Jahr."""
    _eltern_pruefen(von)
    if getattr(kind, "rolle", None) != "kind":
        raise SondertagFehler(_("Sondertage gibt es nur für Kinder."))
    tag = _datum(datum, _("Datum"))
    notiz = (notiz or "").strip()
    if len(notiz) > NOTIZ_MAX:
        raise SondertagFehler(_("Notiz: höchstens %(max)s Zeichen.") % {"max": NOTIZ_MAX})
    b = _begleitung(begleitung)
    with transaction.atomic():
        anspruch = SondertagAnspruch.objects.create(
            kind=kind,
            quelle=Quelle.MANUELL,
            titel=TITEL_MANUELL,
            verdient_am=zeit.tag_beginn(tag),
            status=Status.STATTGEFUNDEN,
            annahme_datum=tag,
            stattgefunden_am=tag,
            angenommen_von=von,
            begleitung=b,
            notiz=notiz,
        )
        audit.protokollieren(
            "sondertag.manuell_erfasst",
            akteur=von,
            objekt=anspruch,
            kind=kind,
            details={"datum": tag.isoformat(), "begleitung": str(b.pk) if b else None},
        )
        neu_berechnen(kind, heute)
    return anspruch


def manuell_loeschen(anspruch, *, von, heute: date | None = None) -> None:
    """Nur manuell erfasste Einträge dürfen gelöscht werden (Meilenstein-Ansprüche sind Fakten)."""
    _eltern_pruefen(von)
    with transaction.atomic():
        anspruch = _laden(anspruch)
        if anspruch.quelle != Quelle.MANUELL:
            raise SondertagFehler(_("Nur manuell erfasste Einträge lassen sich löschen."))
        kind = anspruch.kind
        audit.protokollieren(
            "sondertag.manuell_geloescht",
            akteur=von,
            objekt=anspruch,
            kind=kind,
            details={"datum": _json(anspruch.annahme_datum)},
        )
        anspruch.delete()
        neu_berechnen(kind, heute)
