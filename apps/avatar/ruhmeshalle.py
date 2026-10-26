"""Ruhmeshalle (Phase 3, Entscheidung 33).

Ist die Ausbaustufe im aktuellen Rang auf der Einstellung ``avatar.ruhmeshalle_ausbaustufe``
(Startwert 6), kann das Kind seinen fertig ausgebauten Avatar als **Held** in die Ruhmeshalle
stellen und mit einem neuen Thema neu beginnen.

- Der Eintrag friert alles ein, was zum Zeichnen nötig ist (Thema-Daten, angelegte Mods, Figur),
  dazu Rang zum Zeitpunkt und Statistik. Er ist unveränderlich (nur die Widmung der Eltern) und
  wird nie gelöscht.
- Nichts geht verloren: die fertigen Mods werden ``eingefroren`` (zählen im neuen Thema nicht
  mehr), Rang, XP, Abzeichen und verdiente Sondertage bleiben. Es gibt keine Verlust-Warnung
  wie beim normalen Themenwechsel (``mods.thema_wechseln``).
- **Gesperrt, solange Bauaufträge im aktuellen Thema laufen** (AP36): sonst würden sie nach dem
  Einfrieren im alten Thema fertig. Das Kind sieht, wie viele noch laufen.
- **Idempotent:** ``bau_start`` (Start des Baus, wie der Dialog ihn sah) ist je Kind eindeutig.
  Ein Doppelklick liefert den bestehenden Eintrag, ohne zweite Ereignisse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count

from apps.ereignisse import services as ereignisse
from apps.kern import audit, zeit
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte_services

from . import events
from .generator import renderer
from .models import (
    WIDMUNG_MAX,
    Avatar,
    BesitzStatus,
    ModBesitz,
    RuhmeshallenEintrag,
    Thema,
)
from .mods import ModFehler, _abzeichen_pruefen, _neues_thema, ausbaustufe


@dataclass(frozen=True)
class Bereitschaft:
    bereit: bool  # ausgebaut und kein Bauauftrag im aktuellen Thema läuft
    ausgebaut: bool
    bau_laeuft: int  # laufende Bauaufträge im aktuellen Thema
    aktuell: int
    ab: int
    rang_name: str
    rang_selten: str
    bau_start: str  # Prüfwert für den Dialog (Start des laufenden Baus)

    @property
    def bau_hinweis(self) -> str:
        return bau_meldung(self.bau_laeuft) if self.bau_laeuft else ""


def bereitschaft(kind, jetzt=None) -> Bereitschaft:
    stufe = ausbaustufe(kind, jetzt)
    avatar = Avatar.objects.filter(pk=kind.pk).first()
    laufend = _laufende_bauauftraege(kind, avatar.thema_id) if avatar else 0
    return Bereitschaft(
        bereit=stufe.halle_bereit and not laufend,
        ausgebaut=stufe.halle_bereit,
        bau_laeuft=laufend,
        aktuell=stufe.aktuell,
        ab=stufe.halle_ab,
        rang_name=stufe.rang_name,
        rang_selten=stufe.rang_selten,
        bau_start=avatar.thema_gewaehlt_am.isoformat() if avatar else "",
    )


def _laufende_bauauftraege(kind, thema_id) -> int:
    return ModBesitz.objects.filter(
        kind=kind, status=BesitzStatus.IM_BAU, mod__thema_id=thema_id
    ).count()


def bau_meldung(laufend: int) -> str:
    if laufend == 1:
        was = "dein Bauauftrag fertig ist"
    else:
        was = f"deine {laufend} Bauaufträge fertig sind"
    return f"Warte, bis {was}. Dann darf dein Held in die Ruhmeshalle."


def _mods_snapshot(avatar) -> dict:
    from .selectors import angelegte_mods

    return {
        slot: {
            "schluessel": m.schluessel,
            "name": m.name,
            "seltenheit": m.seltenheit,
            **m.render_mod(),
        }
        for slot, m in sorted(angelegte_mods(avatar).items())
    }


def _vorhandener(kind, bau_start):
    return RuhmeshallenEintrag.objects.filter(kind=kind, themenstart=bau_start).first()


def in_ruhmeshalle_stellen(
    kind, thema_schluessel, *, bau_start, jetzt=None
) -> tuple[RuhmeshallenEintrag, bool]:
    """Held einfrieren, neues Thema setzen. ``(eintrag, neu)``; ``neu`` ist ``False``, wenn der
    Aufruf nur eine Wiederholung (Doppelklick) war."""
    from .services import AvatarFehler, figur_pruefen, hash_aktualisieren

    if getattr(kind, "rolle", None) != "kind":
        raise ModFehler("Nur Kinder stellen ihren Helden in die Ruhmeshalle.")
    jetzt = jetzt or zeit.jetzt()
    with transaction.atomic():
        punkte_services.schreibsperre(kind)
        avatar = Avatar.objects.select_for_update().select_related("thema").filter(pk=kind.pk)
        avatar = avatar.first()
        if avatar is None:
            raise ModFehler("Wähle zuerst deinen Avatar.")
        if bau_start and avatar.thema_gewaehlt_am.isoformat() != bau_start:
            vorhanden = _vorhandener(kind, bau_start)
            if vorhanden is not None:
                return vorhanden, False
            raise ModFehler("Dein Held hat sich geändert. Bitte öffne den Dialog noch einmal.")
        stand = ausbaustufe(kind, jetzt)
        if not stand.halle_bereit:
            raise ModFehler(
                f"Die Ruhmeshalle gibt es ab Ausbaustufe {stand.halle_ab} "
                f"(du hast {stand.aktuell})."
            )
        laufend = _laufende_bauauftraege(kind, avatar.thema_id)
        if laufend:
            raise ModFehler(bau_meldung(laufend))
        neu = _neues_thema(thema_schluessel)
        alt: Thema = avatar.thema
        bauzeit = max(1, math.ceil((jetzt - avatar.thema_gewaehlt_am).total_seconds() / 604800))
        mods = _mods_snapshot(avatar)
        eingefroren = ModBesitz.objects.filter(
            kind=kind, status=BesitzStatus.FERTIG, mod__thema=alt
        )
        anzahl_mods = eingefroren.count()
        eintrag = RuhmeshallenEintrag.objects.create(
            kind=kind,
            thema=alt,
            thema_daten=alt.als_dict(),
            mods=mods,
            figur=dict(avatar.figur),
            avatar_name=avatar.name,
            rang_stufe=stand.rang_stufe,
            rang_name=stand.rang_name,
            rang_selten=stand.rang_selten,
            themenstart=avatar.thema_gewaehlt_am,
            erstellt_am=jetzt,
            bauzeit_wochen=bauzeit,
            anzahl_mods=anzahl_mods,
            aufgaben_anzahl=punkte_selectors.aufgaben_anzahl(
                kind, zeit.heute(avatar.thema_gewaehlt_am), zeit.heute(jetzt)
            ),
        )
        eingefroren.update(status=BesitzStatus.EINGEFROREN)
        try:
            figur = figur_pruefen(avatar.figur, neu)
        except AvatarFehler:  # Frisur passt nicht zum neuen Thema
            figur = figur_pruefen({**avatar.figur, "frisur": (neu.figur_varianten or [""])[0]})
        avatar.thema = neu
        avatar.figur = figur
        avatar.angelegt = {}
        avatar.thema_gewaehlt_am = jetzt
        avatar.save(update_fields=["thema", "figur", "angelegt", "thema_gewaehlt_am"])
        hash_aktualisieren(avatar)
        details = {
            "eintrag": eintrag.pk,
            "thema": alt.schluessel,
            "neues_thema": neu.schluessel,
            "rang_stufe": stand.rang_stufe,
            "anzahl_mods": anzahl_mods,
            "bauzeit_wochen": bauzeit,
        }
        audit.protokollieren(
            "avatar.ruhmeshalle_eintrag", akteur=kind, objekt=eintrag, kind=kind, details=details
        )
        daten = {
            **details,
            "thema": alt.name,
            "neues_thema_name": neu.name,
            "rang": stand.rang_name,
        }
        for typ in (events.RUHMESHALLE_HELD, events.RUHMESHALLE_ELTERN):
            ereignisse.veroeffentlichen(
                typ,
                daten=daten,
                kind=kind,
                akteur=kind,
                schluessel=f"{typ}:{kind.pk}:{eintrag.pk}",
            )
    _abzeichen_pruefen([kind])
    return eintrag, True


def widmung_setzen(eintrag, text, *, von, jetzt=None) -> RuhmeshallenEintrag:
    """Eltern: Widmung schreiben oder ändern (leer = entfernen), mit Audit."""
    if getattr(von, "rolle", None) != "eltern":
        raise ModFehler("Nur Eltern schreiben eine Widmung.")
    text = " ".join((text or "").split())
    if len(text) > WIDMUNG_MAX:
        raise ModFehler(f"Die Widmung darf höchstens {WIDMUNG_MAX} Zeichen haben.")
    pk = eintrag.pk if isinstance(eintrag, RuhmeshallenEintrag) else eintrag
    with transaction.atomic():
        eintrag = RuhmeshallenEintrag.objects.select_for_update().filter(pk=pk).first()
        if eintrag is None:
            raise ModFehler("Diesen Eintrag gibt es nicht.")
        if eintrag.widmung == text:
            return eintrag
        alt = eintrag.widmung
        eintrag.widmung = text
        eintrag.widmung_von = von
        eintrag.widmung_am = jetzt or zeit.jetzt()
        eintrag.save(update_fields=["widmung", "widmung_von", "widmung_am"])
        audit.protokollieren(
            "avatar.ruhmeshalle_widmung",
            akteur=von,
            objekt=eintrag,
            kind=eintrag.kind,
            details={"eintrag": eintrag.pk, "alt": alt, "neu": text},
        )
    return eintrag


# --- Lesen und Darstellen ------------------------------------------------------------------------


def eintraege(kind=None):
    """Einträge (älteste zuerst), optional eines Kindes."""
    qs = RuhmeshallenEintrag.objects.select_related("kind", "thema")
    return qs.filter(kind=kind) if kind is not None else qs


def anzahl(kind=None) -> int:
    return eintraege(kind).count()


def svg_von(eintrag) -> str:
    """Held aus dem Snapshot gezeichnet (deterministisch, mit Render-Cache)."""
    from .services import zustand_rendern

    try:
        return zustand_rendern(eintrag.render_zustand())[1]
    except renderer.RenderFehler:
        return ""


def mit_bild(eintraege_):
    """Hängt ``svg`` an jeden Eintrag (für Templates)."""
    liste = list(eintraege_)
    for e in liste:
        e.svg = svg_von(e)
    return liste


def je_kind(eintraege_=None) -> list[dict]:
    """Familien-Ansicht: ``[{kind, eintraege}]`` nach Kind gruppiert (Name aufsteigend)."""
    gruppen: dict[int, dict] = {}
    for e in mit_bild(eintraege_ if eintraege_ is not None else eintraege()):
        gruppen.setdefault(e.kind_id, {"kind": e.kind, "eintraege": []})["eintraege"].append(e)
    return sorted(gruppen.values(), key=lambda g: g["kind"].anzeigename)


# --- Metriken (kern.registry) -------------------------------------------------------------------


def metrik_eintraege(kind) -> int:
    return RuhmeshallenEintrag.objects.filter(kind=kind).count()


def metrik_themen(kind) -> int:
    zeilen = RuhmeshallenEintrag.objects.filter(kind=kind).values("thema").annotate(n=Count("id"))
    return zeilen.count()


def metrik_hoechster_rang(kind) -> int:
    rang = (
        RuhmeshallenEintrag.objects.filter(kind=kind)
        .order_by("-rang_stufe")
        .values_list("rang_stufe", flat=True)
        .first()
    )
    return rang or 0
