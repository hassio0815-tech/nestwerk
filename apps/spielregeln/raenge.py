"""Ränge (AP22, ARCHITECTURE 7.4, SPEC 6.2/18.1, Entscheidung 14, K2/K3).

Öffentlich über ``selectors`` (lesen) und ``services`` (schreiben).

- Aufstieg verlangt **beide** Bedingungen: ``xp >= ceil(xp_schwelle * faktor)`` und
  ``aktive_wochen >= min_aktive_wochen`` (aktive Wochen = abgeschlossene Wochen, AP20).
- Wirksamer Faktor (K3) = global x Kind (Kind optional, nur für Eltern sichtbar); wirkt auf die
  XP-Schwelle.
- ``RangAufstieg`` ist ein Fakt: einmal erreicht bleibt erreicht (auch bei höheren Schwellen
  oder sinkenden XP nach Korrektur, K2). Mehrfachsprung: je Zwischenstufe ein Fakt.
- Die niedrigste Stufe ist der Startrang (kein Fakt, kein Ereignis).
- Prüfung: nach jeder XP-Buchung (``punkte.gebucht``, synchron) und in ``kind_auswerten``
  (``wochen_sicherstellen``, neue aktive Wochen) sowie nach Änderung von Schwellen/Faktoren.
- Ereignis ``rang.aufgestiegen`` (Kind: festliches Pop-up, Eltern: Benachrichtigung) einmal je
  Prüfung für die höchste neue Stufe; ``stufen`` nennt alle neuen Stufen.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils.formats import localize
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import audit, zeit
from apps.konten import selectors as konten

from . import auswertung, events
from .models import Kalibrierung, KindStand, Rang, RangAufstieg

logger = logging.getLogger("nestwerk.spielregeln")

FAKTOR_MIN = Decimal("0.25")
FAKTOR_MAX = Decimal("4.00")
NAME_MAX = 40
NOTIZ_MAX = 200


class RangFehler(ValueError):
    """Fachlicher Fehler (Meldung ist für Eltern lesbar)."""


# --- Lesen ----------------------------------------------------------------------------------


def raenge() -> list[Rang]:
    return list(Rang.objects.order_by("stufe"))


def startrang() -> Rang | None:
    return Rang.objects.order_by("stufe").first()


def globaler_faktor() -> Decimal:
    zeile = Kalibrierung.objects.filter(kind__isnull=True).first()
    return zeile.faktor_schwelle if zeile else Decimal("1.00")


def kind_faktor(kind) -> Decimal | None:
    """Eigener Faktor des Kindes oder ``None`` (nur Eltern-Ansicht)."""
    zeile = Kalibrierung.objects.filter(kind=kind).first()
    return zeile.faktor_schwelle if zeile else None


def kind_wochen_faktor(kind) -> Decimal | None:
    """AP32: eigener Faktor des Kindes auf die Mindestwochen oder ``None``."""
    zeile = Kalibrierung.objects.filter(kind=kind).first()
    return zeile.faktor_wochen if zeile and zeile.faktor_wochen != 1 else None


def wirksamer_faktor(kind) -> Decimal:
    return globaler_faktor() * (kind_faktor(kind) or Decimal("1"))


def wirksame_schwelle(rang: Rang, faktor: Decimal) -> int:
    return math.ceil(Decimal(rang.xp_schwelle) * faktor)


def wirksame_wochen(rang: Rang, faktor: Decimal) -> int:
    """AP32 (P-07): Mindest-Aktivwochen x Wochen-Faktor, aufgerundet."""
    return math.ceil(Decimal(rang.min_aktive_wochen) * faktor)


def wochen_faktor(kind=None) -> Decimal:
    """AP32: wirksamer Faktor auf die Mindest-Aktivwochen = global x Kind."""
    return _mod_faktor(kind, "faktor_wochen")


def rang_zur_stufe(stufe: int) -> Rang | None:
    """Rang einer Stufe (= Mod-Seltenheit, AP26)."""
    return Rang.objects.filter(stufe=stufe).first()


def _mod_faktor(kind, feld) -> Decimal:
    """AP26: wirksamer Preis-/Bauzeit-Faktor = global x Kind (Kind optional, K3)."""
    faktor = Decimal("1")
    for zeile in Kalibrierung.objects.filter(kind__isnull=True):
        faktor *= getattr(zeile, feld)
    if kind is not None:
        for zeile in Kalibrierung.objects.filter(kind=kind):
            faktor *= getattr(zeile, feld)
    return faktor


def preis_faktor(kind=None) -> Decimal:
    return _mod_faktor(kind, "faktor_preis")


def bauzeit_faktor(kind=None) -> Decimal:
    return _mod_faktor(kind, "faktor_bauzeit")


def _skaliert(wert: int, faktor: Decimal) -> int:
    return int((Decimal(wert) * faktor).quantize(Decimal("1"), ROUND_HALF_UP))


def mod_preis(grundwert: int, kind=None) -> int:
    """AP26: Mod-Preis = Grundwert (Bauplan oder Rang-Standard) x Preis-Faktor, kaufmännisch
    gerundet, mindestens 1 Punkt."""
    return max(1, _skaliert(grundwert, preis_faktor(kind)))


def mod_bauzeit_stunden(grundwert: int, kind=None) -> int:
    """AP26: Bauzeit = Grundwert x Bauzeit-Faktor, gerundet auf ganze Stunden (0 = sofort)."""
    return max(0, _skaliert(grundwert, bauzeit_faktor(kind)))


def rang_aufstiege(kind):
    """Rang-Fakten eines Kindes, aufsteigend nach Stufe (AP23/AP26/AP27)."""
    return RangAufstieg.objects.filter(kind=kind).select_related("rang").order_by("rang__stufe")


def aktueller_rang(kind) -> Rang | None:
    """Höchster erreichter Rang (Fakt), sonst Startrang."""
    fakt = rang_aufstiege(kind).last()
    return fakt.rang if fakt else startrang()


def rang_erreicht(kind, stufe: int) -> bool:
    start = startrang()
    if start is not None and stufe <= start.stufe:
        return True
    return RangAufstieg.objects.filter(kind=kind, rang__stufe__gte=stufe).exists()


def _xp(kind) -> int:
    from apps.punkte import selectors as punkte

    return punkte.xp(kind)


def berechneter_rang(kind, *, xp=None, aktive_wochen=None, faktor=None) -> Rang | None:
    """Höchste Stufe, deren beide Bedingungen jetzt erfüllt sind (ohne Fakten)."""
    xp = _xp(kind) if xp is None else xp
    wochen = (
        auswertung.auswerten(kind).stand.aktive_wochen_gesamt
        if aktive_wochen is None
        else (aktive_wochen)
    )
    faktor = wirksamer_faktor(kind) if faktor is None else faktor
    wf = wochen_faktor(kind)
    ziel = None
    for rang in raenge():
        if xp >= wirksame_schwelle(rang, faktor) and wochen >= wirksame_wochen(rang, wf):
            ziel = rang
    return ziel


@dataclass(frozen=True)
class RangFortschritt:
    rang: Rang | None
    naechster: Rang | None  # None = Endstufe erreicht
    xp: int
    aktive_wochen: int
    schwelle: int  # wirksame XP-Schwelle des nächsten Rangs
    xp_fehlt: int
    wochen_fehlen: int
    prozent: int  # Fortschritt 0–100 (das knappere der beiden Kriterien)


def rang_fortschritt(kind, *, xp=None, aktive_wochen=None) -> RangFortschritt:
    """Aktueller Rang und was zum nächsten fehlt ("noch X XP und Y Wochen")."""
    xp = _xp(kind) if xp is None else xp
    if aktive_wochen is None:
        aktive_wochen = auswertung.auswerten(kind).stand.aktive_wochen_gesamt
    rang = aktueller_rang(kind)
    naechster = (
        Rang.objects.filter(stufe__gt=rang.stufe).order_by("stufe").first() if rang else None
    )
    if naechster is None:
        return RangFortschritt(rang, None, xp, aktive_wochen, 0, 0, 0, 100)
    schwelle = wirksame_schwelle(naechster, wirksamer_faktor(kind))
    min_wochen = wirksame_wochen(naechster, wochen_faktor(kind))
    anteile = []
    if schwelle:
        anteile.append(min(1, max(0, xp) / schwelle))
    if min_wochen:
        anteile.append(min(1, aktive_wochen / min_wochen))
    prozent = int(min(anteile) * 100) if anteile else 100
    return RangFortschritt(
        rang=rang,
        naechster=naechster,
        xp=xp,
        aktive_wochen=aktive_wochen,
        schwelle=schwelle,
        xp_fehlt=max(0, schwelle - xp),
        wochen_fehlen=max(0, min_wochen - aktive_wochen),
        prozent=prozent,
    )


# --- Schreiben ------------------------------------------------------------------------------


def _stand_rang_setzen(kind, rang):
    KindStand.objects.filter(kind=kind).exclude(rang=rang).update(rang=rang)


@transaction.atomic
def raenge_pruefen(kind, *, jetzt=None, xp=None, aktive_wochen=None, melden=True):
    """Legt fehlende Rang-Fakten an (alle Stufen bis zum berechneten Rang) und gibt die neuen
    zurück. Idempotent (unique Kind+Rang). ``melden=False``: ohne Ereignis (Reparatur)."""
    if getattr(kind, "rolle", None) != "kind":
        return []
    jetzt = jetzt or zeit.jetzt()
    xp = _xp(kind) if xp is None else xp
    if aktive_wochen is None:
        aktive_wochen = auswertung.auswerten(kind, jetzt).stand.aktive_wochen_gesamt
    faktor = wirksamer_faktor(kind)
    ziel = berechneter_rang(kind, xp=xp, aktive_wochen=aktive_wochen, faktor=faktor)
    start = startrang()
    vorher = aktueller_rang(kind)
    neu = []
    if ziel is not None and start is not None:
        erreicht = set(RangAufstieg.objects.filter(kind=kind).values_list("rang_id", flat=True))
        for rang in Rang.objects.filter(stufe__gt=start.stufe, stufe__lte=ziel.stufe).order_by(
            "stufe"
        ):
            if rang.pk in erreicht:
                continue
            fakt, angelegt = RangAufstieg.objects.get_or_create(
                kind=kind,
                rang=rang,
                defaults={
                    "erreicht_am": jetzt,
                    "xp_bei_aufstieg": xp,
                    "aktive_wochen_bei_aufstieg": aktive_wochen,
                    "schwelle_bei_aufstieg": wirksame_schwelle(rang, faktor),
                },
            )
            if angelegt:
                neu.append(fakt)
    if neu:
        hoechster = neu[-1].rang
        _stand_rang_setzen(kind, hoechster)
        audit.protokollieren(
            "rang.aufgestiegen",
            akteur=None,
            objekt=neu[-1],
            kind=kind,
            details={
                "stufen": [f.rang.stufe for f in neu],
                "xp": xp,
                "aktive_wochen": aktive_wochen,
                "faktor": str(faktor),
            },
        )
        if melden:
            ereignisse.veroeffentlichen(
                events.RANG_AUFGESTIEGEN,
                kind=kind,
                daten={
                    "rang": hoechster.name,
                    "rang_schluessel": hoechster.schluessel,
                    "stufe": hoechster.stufe,
                    "selten": hoechster.selten,
                    "vorher": vorher.stufe if vorher else 0,
                    "stufen": [f.rang.stufe for f in neu],
                    "aufstiege": [f.pk for f in neu],
                    "xp": xp,
                    "aktive_wochen": aktive_wochen,
                },
                schluessel=f"{events.RANG_AUFGESTIEGEN}:{kind.pk}:{hoechster.pk}",
            )
    return neu


def raenge_pruefen_sicher(kind, **kwargs):
    """Savepoint: ein Fehler hier darf die auslösende Änderung (Buchung) nicht kippen; die
    nächste Prüfung (spätestens der Wochenjob) holt es nach."""
    try:
        with transaction.atomic():
            return raenge_pruefen(kind, **kwargs)
    except Exception:
        logger.exception("Rang von %s konnte nicht geprüft werden", getattr(kind, "pk", None))
        return []


def nach_buchung(ereignis):
    """Synchroner Handler ``punkte.gebucht``: bei XP-Zuwachs Rang prüfen."""
    if ereignis.kind_id is None or (ereignis.daten or {}).get("xp_delta", 0) <= 0:
        return
    raenge_pruefen_sicher(ereignis.kind)


def alle_pruefen(jetzt=None):
    for kind in konten.aktive_kinder():
        raenge_pruefen_sicher(kind, jetzt=jetzt)


def _ganzzahl(wert, feld):
    if isinstance(wert, str) and wert.strip().isdigit():
        wert = int(wert.strip())
    if isinstance(wert, bool) or not isinstance(wert, int) or wert < 0:
        raise RangFehler(_("%(feld)s: bitte eine ganze Zahl ab 0.") % {"feld": feld})
    return wert


def _eltern_pruefen(von):
    if getattr(von, "rolle", None) != "eltern":
        raise RangFehler(_("Ränge ändern nur Eltern."))


@transaction.atomic
def rang_aendern(rang, *, von, name, xp_schwelle, min_aktive_wochen, jetzt=None):
    """Eltern ändern Name, XP-Schwelle und Mindestwochen eines Rangs (Audit). Schwellen und
    Wochen müssen mit der Stufe steigen (nicht fallen). Erreichte Ränge bleiben (Fakt);
    niedrigere Schwellen können sofort Aufstiege auslösen."""
    _eltern_pruefen(von)
    rang = Rang.objects.select_for_update().get(pk=rang.pk)
    name = (name or "").strip()
    if not name or len(name) > NAME_MAX:
        raise RangFehler(_("Name: 1 bis %(max)s Zeichen.") % {"max": NAME_MAX})
    xp_schwelle = _ganzzahl(xp_schwelle, _("XP-Schwelle"))
    min_aktive_wochen = _ganzzahl(min_aktive_wochen, _("Aktive Wochen"))
    if min_aktive_wochen > 32767:
        raise RangFehler(_("Aktive Wochen: höchstens 32767."))
    neu = {"name": name, "xp_schwelle": xp_schwelle, "min_aktive_wochen": min_aktive_wochen}
    vorher = Rang.objects.filter(stufe__lt=rang.stufe).order_by("-stufe").first()
    nachher = Rang.objects.filter(stufe__gt=rang.stufe).order_by("stufe").first()
    for nachbar, unten in ((vorher, True), (nachher, False)):
        if nachbar is None:
            continue
        for feld, text in (
            ("xp_schwelle", _("XP-Schwelle")),
            ("min_aktive_wochen", _("Aktive Wochen")),
        ):
            wert = getattr(nachbar, feld)
            if (wert > neu[feld]) if unten else (neu[feld] > wert):
                raise RangFehler(
                    _("%(text)s muss mit dem Rang steigen: %(name)s hat %(wert)s.")
                    % {"text": text, "name": nachbar.name, "wert": wert}
                )
    alt = {f: getattr(rang, f) for f in neu}
    geaendert = {f: v for f, v in neu.items() if alt[f] != v}
    if not geaendert:
        return rang
    Rang.objects.filter(pk=rang.pk).update(**geaendert)
    rang.refresh_from_db()
    audit.protokollieren(
        "rang.geaendert",
        akteur=von,
        objekt=rang,
        details={"alt": {f: alt[f] for f in geaendert}, "neu": geaendert},
    )
    if {"xp_schwelle", "min_aktive_wochen"} & geaendert.keys():
        alle_pruefen(jetzt)
    return rang


@transaction.atomic
def mod_standard_aendern(rang, *, von, mod_preis, bauzeit_stunden):
    """AP26: Eltern ändern Standard-Mod-Preis und Bauzeit einer Seltenheit (Audit). Gilt für
    künftige Käufe; bezahlte Preise und laufende Bauaufträge bleiben."""
    _eltern_pruefen(von)
    rang = Rang.objects.select_for_update().get(pk=rang.pk)
    neu = {
        "mod_preis": _ganzzahl(mod_preis, _("Mod-Preis")),
        "bauzeit_stunden": _ganzzahl(bauzeit_stunden, _("Bauzeit")),
    }
    if neu["mod_preis"] < 1:
        raise RangFehler(_("Mod-Preis: mindestens 1 Punkt."))
    if neu["bauzeit_stunden"] > 24 * 365:
        raise RangFehler(_("Bauzeit: höchstens ein Jahr."))
    alt = {f: getattr(rang, f) for f in neu}
    geaendert = {f: v for f, v in neu.items() if alt[f] != v}
    if geaendert:
        Rang.objects.filter(pk=rang.pk).update(**geaendert)
        rang.refresh_from_db()
        audit.protokollieren(
            "rang.mod_standard_geaendert",
            akteur=von,
            objekt=rang,
            details={"alt": {f: alt[f] for f in geaendert}, "neu": geaendert},
        )
    return rang


@transaction.atomic
def mod_faktoren_setzen(*, von, faktor_preis, faktor_bauzeit, jetzt=None, kind=None):
    """AP26: Kalibrierung von Mod-Preisen und Bauzeiten (Audit, K3), global oder (AP32) je Kind."""
    _eltern_pruefen(von)
    if kind is not None and getattr(kind, "rolle", None) != "kind":
        raise RangFehler(_("Kalibrierung gibt es nur global oder für Kinder."))
    neu = {
        "faktor_preis": faktor_lesen(faktor_preis),
        "faktor_bauzeit": faktor_lesen(faktor_bauzeit),
    }
    zeile = Kalibrierung.objects.filter(kind=kind).first() or Kalibrierung(kind=kind)
    alt = {f: getattr(zeile, f) for f in neu}
    if zeile.pk and alt == neu:
        return zeile
    for feld, wert in neu.items():
        setattr(zeile, feld, wert)
    zeile.geaendert_von = von
    zeile.geaendert_am = jetzt or zeit.jetzt()
    zeile.save()
    audit.protokollieren(
        "kalibrierung.mod_geaendert",
        akteur=von,
        objekt_typ="spielregeln.kalibrierung",
        objekt_id=str(kind.pk) if kind else "global",
        kind=kind,
        details={
            "alt": {f: str(v) for f, v in alt.items()},
            "neu": {f: str(v) for f, v in neu.items()},
        },
    )
    return zeile


def faktor_lesen(wert) -> Decimal:
    try:
        faktor = Decimal(str(wert).replace(",", ".")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise RangFehler(_("Faktor: bitte eine Zahl wie 1,0 oder 0,8.")) from None
    if not FAKTOR_MIN <= faktor <= FAKTOR_MAX:
        raise RangFehler(
            _("Faktor: zwischen %(min)s und %(max)s.")
            % {"min": localize(FAKTOR_MIN), "max": localize(FAKTOR_MAX)}
        )
    return faktor


@transaction.atomic
def kalibrierung_setzen(kind, faktor, *, von, notiz="", jetzt=None):
    """K3: Schwellen-Faktor global (``kind=None``) oder je Kind setzen; ``faktor=None`` beim Kind
    entfernt den eigenen Faktor. Audit; danach Ränge prüfen (kleinerer Faktor kann Aufstiege
    auslösen, größerer nimmt nichts weg)."""
    _eltern_pruefen(von)
    jetzt = jetzt or zeit.jetzt()
    notiz = (notiz or "").strip()[:NOTIZ_MAX]
    if kind is not None and getattr(kind, "rolle", None) != "kind":
        raise RangFehler(_("Kalibrierung gibt es nur global oder für Kinder."))
    zeile = (
        Kalibrierung.objects.filter(kind=kind).first()
        if kind
        else (Kalibrierung.objects.filter(kind__isnull=True).first())
    )
    alt = str(zeile.faktor_schwelle) if zeile else None
    if faktor is None:
        if kind is None:
            raise RangFehler(_("Der globale Faktor ist Pflicht."))
        if zeile is None:
            return None
        if zeile.faktor_wochen != 1 or zeile.faktor_preis != 1 or zeile.faktor_bauzeit != 1:
            zeile.faktor_schwelle = Decimal("1.00")  # andere Faktoren des Kindes bleiben
            zeile.geaendert_von = von
            zeile.geaendert_am = jetzt
            zeile.save()
        else:
            zeile.delete()
        neu = None
    else:
        faktor = faktor_lesen(faktor)
        if zeile is not None and zeile.faktor_schwelle == faktor and zeile.notiz == notiz:
            return zeile
        if zeile is None:
            zeile = Kalibrierung(kind=kind)
        zeile.faktor_schwelle = faktor
        zeile.notiz = notiz
        zeile.geaendert_von = von
        zeile.geaendert_am = jetzt
        zeile.save()
        neu = str(faktor)
    audit.protokollieren(
        "kalibrierung.geaendert",
        akteur=von,
        objekt_typ="spielregeln.kalibrierung",
        objekt_id=str(kind.pk) if kind else "global",
        kind=kind,
        details={"alt": alt, "neu": neu, "notiz": notiz},
    )
    if kind is None:
        alle_pruefen(jetzt)
    else:
        raenge_pruefen_sicher(kind, jetzt=jetzt)
    return zeile if faktor is not None else None


@transaction.atomic
def wochen_faktor_setzen(kind, faktor, *, von, notiz="", jetzt=None):
    """AP32 (P-07): Faktor auf die Mindest-Aktivwochen der Ränge, global (``kind=None``) oder je
    Kind. ``faktor=None`` (oder 1,0) setzt zurück. Audit; danach Ränge prüfen (ein kleinerer
    Faktor kann Aufstiege auslösen, ein größerer nimmt nichts weg: Rang ist ein Fakt)."""
    _eltern_pruefen(von)
    jetzt = jetzt or zeit.jetzt()
    notiz = (notiz or "").strip()[:NOTIZ_MAX]
    if kind is not None and getattr(kind, "rolle", None) != "kind":
        raise RangFehler(_("Kalibrierung gibt es nur global oder für Kinder."))
    neu = Decimal("1.00") if faktor is None else faktor_lesen(faktor)
    zeile = Kalibrierung.objects.filter(kind=kind).first()
    alt = zeile.faktor_wochen if zeile else Decimal("1.00")
    if alt == neu:
        return zeile
    if zeile is None:
        zeile = Kalibrierung(kind=kind)
    zeile.faktor_wochen = neu
    if notiz:
        zeile.notiz = notiz
    zeile.geaendert_von = von
    zeile.geaendert_am = jetzt
    zeile.save()
    audit.protokollieren(
        "kalibrierung.wochen_geaendert",
        akteur=von,
        objekt_typ="spielregeln.kalibrierung",
        objekt_id=str(kind.pk) if kind else "global",
        kind=kind,
        details={"alt": str(alt), "neu": str(neu), "notiz": notiz},
    )
    if kind is None:
        alle_pruefen(jetzt)
    else:
        raenge_pruefen_sicher(kind, jetzt=jetzt)
    return zeile
