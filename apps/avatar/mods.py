"""Mod-Shop, Kauf, Bauzeit, Ausbaustufe und Themenwechsel (AP26, SPEC 11, ARCHITECTURE 7.6).

Öffentlich über ``services`` (schreiben) und ``selectors`` (lesen).

- **Preis/Bauzeit:** Grundwert = Bauplan (``ModDefinition.preis``/``bauzeit_stunden``) oder
  Rang-Standard der Seltenheit; wirksam = Grundwert x Kalibrierungsfaktor (global x Kind),
  gerundet (``spielregeln.selectors.mod_preis``/``mod_bauzeit_stunden``).
- **Kauf:** Seltenheit <= aktueller Rang; genau eine Ledger-Buchung ``modkauf`` mit Schlüssel
  ``modkauf:<kind>:<mod>:<n>`` (n = wievielter Kauf dieses Mods, z. B. nach Themenwechsel
  zurück); Prüfung gegen verfügbares Guthaben (offene Einlöse-Anträge sind reserviert); alles in
  einer Transaktion unter der Schreibsperre des Kindes (SQLite ``BEGIN IMMEDIATE``).
- **Fertigstellung:** bedingtes Update ``im_bau -> fertig`` (idempotent), ``fertig_am`` =
  geplanter Zeitpunkt (Catch-up: ein verspäteter Job ändert die Wertungswoche nicht).
- **Zeitbremse:** je ISO-Woche zählen höchstens N neu fertige Mods (Einstellung
  ``avatar.max_zaehlende_mods_woche``, Startwert 1). Weitere sind sofort nutzbar und zählen ab
  der nächsten freien Woche (Warteschlange ``zaehlt_ab_iso_*``, ARCHITECTURE 7.6). Nie-Zählen
  wäre eine Sackgasse: je Slot und Seltenheit gibt es genau einen Mod, Ausbaustufe 6 wäre dann
  nur noch per Themenwechsel erreichbar.
- **Ausbaustufe (K4):** je Seltenheit die Anzahl Slots, in denen das Kind im aktuellen Thema
  einen fertigen, schon zählenden Mod dieser Seltenheit besitzt (Besitz zählt, nicht angelegt).
- **Themenwechsel:** alle Mods des alten Themas (fertig und im Bau) verfallen, keine Erstattung,
  Slots leer, Ausbaustufe 0, Rang und verdiente Sondertage bleiben (Fakten).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Sum

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.konten import selectors as konten
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte_services
from apps.spielregeln import selectors as spielregeln

from . import events
from .models import AKTIV, Avatar, BesitzStatus, ModBesitz, ModDefinition, Slot, Thema

logger = logging.getLogger("nestwerk.avatar")

EINSTELLUNG_PRO_WOCHE = "avatar.max_zaehlende_mods_woche"
MAX_WARTESCHLANGE_WOCHEN = 520


class ModFehler(ValueError):
    """Fachlicher Fehler (Meldung ist für Kinder bzw. Eltern lesbar)."""


# --- Inszenierung je Thema ---------------------------------------------------------------------

# bau_inszenierung -> (Ort, Tätigkeit im Bau)
INSZENIERUNG = {
    "schmiede": ("Schmiede", "wird geschmiedet"),
    "raumdock": ("Raumdock", "wird montiert"),
    "dojo": ("Dojo-Werkstatt", "wird gefertigt"),
    "werkstatt": ("Roboter-Werkstatt", "wird zusammengeschraubt"),
    "werft": ("Werft", "wird gezimmert"),
    "langhaus": ("Langhaus-Schmiede", "wird geschmiedet"),
    "trainingsplatz": ("Zeugwart-Kabine", "wird vorbereitet"),
    "trainingshalle": ("Ausrüster", "wird vorbereitet"),
    "boxengasse": ("Boxengasse", "wird geschraubt"),
    "basislager": ("Basislager", "wird gebastelt"),
}
STANDARD_INSZENIERUNG = ("Werkstatt", "wird gebaut")


def inszenierung(thema) -> tuple[str, str]:
    return INSZENIERUNG.get(getattr(thema, "bau_inszenierung", ""), STANDARD_INSZENIERUNG)


def dauer_text(stunden: int) -> str:
    """Bauzeit lesbar: "3 Tage", "1 Tag", "5 Stunden", "sofort"."""
    if stunden <= 0:
        return "sofort"
    if stunden >= 36 or stunden % 24 == 0:
        tage = max(1, round(stunden / 24))
        return "1 Tag" if tage == 1 else f"{tage} Tage"
    return "1 Stunde" if stunden == 1 else f"{stunden} Stunden"


def rest_text(bis: datetime, jetzt: datetime | None = None) -> str:
    """ "fertig in 2 Tagen" ohne "fertig": "in 2 Tagen", "in 5 Stunden", "gleich"."""
    sekunden = (bis - (jetzt or zeit.jetzt())).total_seconds()
    if sekunden <= 0:
        return "gleich"
    stunden = math.ceil(sekunden / 3600)
    if stunden >= 36:
        return f"in {round(stunden / 24)} Tagen"
    if stunden >= 24:
        return "in 1 Tag"
    if sekunden < 3600:
        return "in weniger als 1 Stunde"
    return "in 1 Stunde" if stunden == 1 else f"in {stunden} Stunden"


# --- Preise und Bauzeiten -------------------------------------------------------------------


@dataclass(frozen=True)
class Konditionen:
    preis: int
    bauzeit_stunden: int
    rang_name: str
    rang_selten: str

    @property
    def bauzeit_text(self):
        return dauer_text(self.bauzeit_stunden)


def _raenge_nach_stufe():
    return {r.stufe: r for r in spielregeln.raenge()}


def konditionen(mod: ModDefinition, kind=None, *, raenge_map=None) -> Konditionen:
    """Wirksamer Preis und Bauzeit eines Mods für ein Kind (Bauplan oder Rang-Standard x
    Kalibrierungsfaktor, gerundet)."""
    raenge_map = raenge_map if raenge_map is not None else _raenge_nach_stufe()
    rang = raenge_map.get(mod.seltenheit)
    if rang is None:
        raise ModFehler("Für diese Seltenheit gibt es keinen Rang.")
    grund_preis = mod.preis if mod.preis is not None else rang.mod_preis
    grund_bauzeit = mod.bauzeit_stunden if mod.bauzeit_stunden is not None else rang.bauzeit_stunden
    return Konditionen(
        preis=spielregeln.mod_preis(grund_preis, kind),
        bauzeit_stunden=spielregeln.mod_bauzeit_stunden(grund_bauzeit, kind),
        rang_name=rang.name,
        rang_selten=rang.selten,
    )


def rang_stufe(kind) -> int:
    rang = spielregeln.aktueller_rang(kind)
    return rang.stufe if rang else 1


# --- Ausbaustufe ----------------------------------------------------------------------------


def _woche_von(besitz) -> IsoWoche | None:
    if besitz.zaehlt_ab_iso_jahr is None:
        return None
    return IsoWoche(besitz.zaehlt_ab_iso_jahr, besitz.zaehlt_ab_iso_woche)


@dataclass
class Ausbaustufe:
    """Ausbaustufe eines Kindes im aktuellen Thema. ``je_seltenheit[n]`` = zählende Slots."""

    thema: Thema | None
    rang_stufe: int
    rang_name: str
    rang_selten: str
    slots: int
    je_seltenheit: dict[int, int] = field(default_factory=dict)
    wartend: list = field(default_factory=list)  # fertig, zählt erst ab späterer Woche
    je_set: dict[int, int] = field(default_factory=dict)  # God-Mode-Set-Nummer -> Slots (AP27)
    halle_ab: int = 6  # Einstellung avatar.ruhmeshalle_ausbaustufe (P3-A)

    @property
    def halle_bereit(self) -> bool:
        return self.thema is not None and self.aktuell >= self.halle_ab

    @property
    def aktuell(self) -> int:
        return self.je_seltenheit.get(self.rang_stufe, 0)

    @property
    def prozent(self) -> int:
        return int(100 * self.aktuell / self.slots) if self.slots else 0


def _aktive_besitze(kind, thema_id=None):
    qs = ModBesitz.objects.filter(kind=kind, status__in=AKTIV).select_related(
        "mod", "mod__slot", "mod__modset"
    )
    if thema_id is not None:
        qs = qs.filter(mod__thema_id=thema_id)
    return qs


def ausbaustufe(kind, jetzt=None) -> Ausbaustufe:
    jetzt = jetzt or zeit.jetzt()
    avatar = Avatar.objects.select_related("thema").filter(pk=kind.pk).first()
    raenge_map = _raenge_nach_stufe()
    stufe = rang_stufe(kind)
    rang = raenge_map.get(stufe)
    ergebnis = Ausbaustufe(
        thema=avatar.thema if avatar else None,
        rang_stufe=stufe,
        rang_name=rang.name if rang else "",
        rang_selten=rang.selten if rang else "common",
        slots=Slot.objects.count(),
        je_seltenheit=dict.fromkeys(raenge_map, 0),
        halle_ab=einstellungen.wert("avatar.ruhmeshalle_ausbaustufe"),
    )
    if avatar is None:
        return ergebnis
    woche = zeit.aktuelle_woche(jetzt)
    gezaehlt, je_set = {}, {}
    for b in _aktive_besitze(kind, avatar.thema_id).filter(status=BesitzStatus.FERTIG):
        ab = _woche_von(b)
        if ab is None or ab > woche:
            ergebnis.wartend.append(b)
        elif b.mod.modset_id is not None:  # God-Mode-Set zählt getrennt (AP27)
            je_set.setdefault(b.mod.modset.nummer, set()).add(b.mod.slot_id)
        else:
            gezaehlt.setdefault(b.mod.seltenheit, set()).add(b.mod.slot_id)
    for seltenheit, slots in gezaehlt.items():
        ergebnis.je_seltenheit[seltenheit] = len(slots)
    ergebnis.je_set = {nummer: len(slots) for nummer, slots in je_set.items()}
    ergebnis.wartend.sort(key=lambda b: (b.zaehlt_ab_iso_jahr or 0, b.zaehlt_ab_iso_woche or 0))
    return ergebnis


# Metrik-Provider (kern.registry, AP23/AP27)


def metrik_ausbaustufe(kind) -> int:
    """Ausbaustufe im aktuellen Rang (0 bis Anzahl Slots)."""
    return ausbaustufe(kind).aktuell


def metrik_ausbaustufe_bereiche(kind) -> dict[str, tuple[int, str]]:
    """``{"seltenheit-<n>": (zählende Slots, Rangname)}`` je Seltenheit."""
    a = ausbaustufe(kind)
    namen = {r.stufe: r.name for r in spielregeln.raenge()}
    return {f"seltenheit-{n}": (wert, namen.get(n, str(n))) for n, wert in a.je_seltenheit.items()}


def metrik_seltenheit(n: int):
    def wert(kind) -> int:
        return ausbaustufe(kind).je_seltenheit.get(n, 0)

    return wert


# --- Shop -----------------------------------------------------------------------------------


@dataclass
class ShopKarte:
    mod: ModDefinition
    konditionen: Konditionen
    zustand: str  # kaufbar | zu_teuer | gesperrt | im_bau | besitzt
    besitz: ModBesitz | None = None
    fehlt: int = 0


@dataclass
class ShopGruppe:
    stufe: int
    rang_name: str
    rang_selten: str
    gesperrt: bool
    karten: list[ShopKarte]
    zaehlend: int = 0
    set_nummer: int | None = None  # God-Mode-Set (AP27)
    titel: str = ""


def shop(kind) -> list[ShopGruppe]:
    """Mods des eigenen Themas je Seltenheit (Karten in Slot-Reihenfolge)."""
    avatar = Avatar.objects.select_related("thema").filter(pk=kind.pk).first()
    if avatar is None:
        return []
    raenge_map = _raenge_nach_stufe()
    stufe = rang_stufe(kind)
    verfuegbar = punkte_selectors.verfuegbar(kind)
    besitz = {b.mod_id: b for b in _aktive_besitze(kind, avatar.thema_id)}
    stand = ausbaustufe(kind)
    gruppen = {}
    for mod in (
        ModDefinition.objects.filter(thema=avatar.thema, aktiv=True, modset__isnull=True)
        .select_related("slot", "thema")
        .order_by("seltenheit", "slot__ebene")
    ):
        rang = raenge_map.get(mod.seltenheit)
        if rang is None:
            continue
        k = konditionen(mod, kind, raenge_map=raenge_map)
        b = besitz.get(mod.pk)
        if b is not None:
            zustand = "im_bau" if b.status == BesitzStatus.IM_BAU else "besitzt"
        elif mod.seltenheit > stufe:
            zustand = "gesperrt"
        elif k.preis > verfuegbar:
            zustand = "zu_teuer"
        else:
            zustand = "kaufbar"
        gruppe = gruppen.setdefault(
            mod.seltenheit,
            ShopGruppe(
                mod.seltenheit,
                rang.name,
                rang.selten,
                mod.seltenheit > stufe,
                [],
                stand.je_seltenheit.get(mod.seltenheit, 0),
            ),
        )
        gruppe.karten.append(ShopKarte(mod, k, zustand, b, max(0, k.preis - verfuegbar)))
    return [gruppen[n] for n in sorted(gruppen)] + _set_gruppen(
        kind, avatar, raenge_map, besitz, verfuegbar, stand
    )


def _set_gruppen(kind, avatar, raenge_map, besitz, verfuegbar, stand) -> list[ShopGruppe]:
    """God-Mode-Sets der freigeschalteten Zyklen (AP27), neuestes zuerst."""
    from . import godmode

    gruppen = []
    for modset in reversed(godmode.sets_sicherstellen(kind, avatar.thema)):
        karten = []
        for mod in modset.mods.filter(aktiv=True).select_related("slot", "thema"):
            rang = raenge_map.get(mod.seltenheit)
            if rang is None:
                continue
            k = konditionen(mod, kind, raenge_map=raenge_map)
            b = besitz.get(mod.pk)
            if b is not None:
                zustand = "im_bau" if b.status == BesitzStatus.IM_BAU else "besitzt"
            else:
                zustand = "zu_teuer" if k.preis > verfuegbar else "kaufbar"
            karten.append(ShopKarte(mod, k, zustand, b, max(0, k.preis - verfuegbar)))
        karten.sort(key=lambda c: c.mod.slot.ebene)
        rang = raenge_map.get(6)
        gruppen.append(
            ShopGruppe(
                6,
                rang.name if rang else "God Mode",
                rang.selten if rang else "godmode",
                False,
                karten,
                stand.je_set.get(modset.nummer, 0),
                set_nummer=modset.nummer,
                titel=modset.name,
            )
        )
    return gruppen


def bauauftraege(kind, jetzt=None) -> list[dict]:
    """Laufende Bauaufträge mit Fortschritt (0-100) und Resttext."""
    jetzt = jetzt or zeit.jetzt()
    ergebnis = []
    for b in (
        ModBesitz.objects.filter(kind=kind, status=BesitzStatus.IM_BAU)
        .select_related("mod", "mod__slot", "mod__thema")
        .order_by("fertig_geplant_am", "id")
    ):
        gesamt = (b.fertig_geplant_am - b.gekauft_am).total_seconds()
        vergangen = (jetzt - b.gekauft_am).total_seconds()
        prozent = 100 if gesamt <= 0 else max(0, min(99, int(100 * vergangen / gesamt)))
        ort, taetigkeit = inszenierung(b.mod.thema)
        ergebnis.append(
            {
                "besitz": b,
                "mod": b.mod,
                "prozent": prozent,
                "rest": rest_text(b.fertig_geplant_am, jetzt),
                "ort": ort,
                "taetigkeit": taetigkeit,
            }
        )
    return ergebnis


def eigene_fertige(kind) -> list[ModBesitz]:
    """Fertige Mods des aktuellen Themas (zum Anlegen), nach Slot und Seltenheit."""
    avatar = Avatar.objects.filter(pk=kind.pk).first()
    if avatar is None:
        return []
    return list(
        _aktive_besitze(kind, avatar.thema_id)
        .filter(status=BesitzStatus.FERTIG)
        .order_by("mod__slot__ebene", "mod__seltenheit")
    )


# --- Kauf -----------------------------------------------------------------------------------


def _mod_laden(mod) -> ModDefinition:
    if isinstance(mod, ModDefinition):
        mod = mod.schluessel
    gefunden = (
        ModDefinition.objects.select_related("slot", "thema", "modset")
        .filter(schluessel=mod)
        .first()
    )
    if gefunden is None:
        raise ModFehler("Diesen Mod gibt es nicht.")
    return gefunden


def kaufen(kind, mod, *, jetzt=None) -> ModBesitz:
    """Kauft einen Mod: genau eine Buchung ``modkauf`` + Bauauftrag. Fehler -> ``ModFehler``."""
    if getattr(kind, "rolle", None) != "kind":
        raise ModFehler("Nur Kinder kaufen Mods.")
    jetzt = jetzt or zeit.jetzt()
    with transaction.atomic():
        punkte_services.schreibsperre(kind)
        avatar = Avatar.objects.select_related("thema").filter(pk=kind.pk).first()
        if avatar is None:
            raise ModFehler("Wähle zuerst deinen Avatar.")
        mod = _mod_laden(mod)
        if mod.thema_id != avatar.thema_id:
            raise ModFehler("Dieser Mod gehört zu einem anderen Thema.")
        if not mod.aktiv:
            raise ModFehler("Diesen Mod gibt es gerade nicht.")
        if ModBesitz.objects.filter(kind=kind, mod=mod, status__in=AKTIV).exists():
            raise ModFehler("Diesen Mod hast du schon.")
        k = konditionen(mod, kind)
        stufe = rang_stufe(kind)
        if mod.seltenheit > stufe:
            raise ModFehler(f"Diesen Mod gibt es ab Rang {k.rang_name}.")
        if mod.modset_id is not None:
            from . import godmode

            if not godmode.zyklus(kind, jetzt).freigeschaltet(mod.modset.nummer):
                raise ModFehler("Dieses God-Mode-Set ist noch nicht freigeschaltet.")
        verfuegbar = punkte_selectors.verfuegbar(kind)
        if k.preis > verfuegbar:
            raise ModFehler(f"Dafür fehlen dir noch {k.preis - verfuegbar} Punkte.")
        nummer = ModBesitz.objects.filter(kind=kind, mod=mod).count() + 1
        try:
            buchung = punkte_services.buchen(
                kind,
                punkte_services.Art.MODKAUF,
                k.preis,
                schluessel=f"modkauf:{kind.pk}:{mod.pk}:{nummer}",
                quelle_modul="avatar",
                referenz_typ="avatar.moddefinition",
                referenz_id=str(mod.pk),
                von=kind,
                verfuegbar_pruefen=True,
            )
        except punkte_services.GuthabenUnzureichend:
            raise ModFehler("Dafür reichen deine Punkte nicht.") from None
        besitz = ModBesitz.objects.create(
            kind=kind,
            mod=mod,
            preis_bezahlt=k.preis,
            bauzeit_stunden=k.bauzeit_stunden,
            buchung=buchung,
            gekauft_am=jetzt,
            fertig_geplant_am=jetzt + timedelta(hours=k.bauzeit_stunden),
        )
        audit.protokollieren(
            "avatar.mod_gekauft",
            akteur=kind,
            objekt=besitz,
            kind=kind,
            details={"mod": mod.schluessel, "preis": k.preis, "bauzeit_stunden": k.bauzeit_stunden},
        )
        ereignisse.veroeffentlichen(
            events.MOD_GEKAUFT,
            daten={
                "besitz": besitz.pk,
                "mod": mod.name,
                "preis": k.preis,
                "bauzeit": k.bauzeit_text,
            },
            schluessel=f"{events.MOD_GEKAUFT}:{besitz.pk}",
            kind=kind,
            akteur=kind,
        )
        if k.bauzeit_stunden == 0:
            _fertig_setzen(besitz.pk, jetzt)
            besitz.refresh_from_db()
    return besitz


# --- Fertigstellung -------------------------------------------------------------------------


def zaehlwoche(kind, fertig_am, *, ausser=None) -> IsoWoche:
    """Erste ISO-Woche ab der Fertigstellungswoche mit freiem Platz für einen zählenden Mod."""
    pro_woche = einstellungen.wert(EINSTELLUNG_PRO_WOCHE)
    woche = zeit.aktuelle_woche(fertig_am)
    belegt = {}
    qs = ModBesitz.objects.filter(
        kind=kind, status=BesitzStatus.FERTIG, zaehlt_ab_iso_jahr__isnull=False
    )
    if ausser is not None:
        qs = qs.exclude(pk=ausser)
    for jahr, nr in qs.values_list("zaehlt_ab_iso_jahr", "zaehlt_ab_iso_woche"):
        belegt[(jahr, nr)] = belegt.get((jahr, nr), 0) + 1
    for _ in range(MAX_WARTESCHLANGE_WOCHEN):
        if belegt.get((woche.jahr, woche.woche), 0) < pro_woche:
            return woche
        woche = woche.naechste()
    return woche


def _fertig_setzen(besitz_id, fertig_am, *, von=None, sofort=False):
    """``im_bau -> fertig`` (bedingtes Update, idempotent). ``None`` = war schon fertig/verloren."""
    with transaction.atomic():
        besitz = ModBesitz.objects.select_related("kind", "mod", "mod__slot", "mod__thema").get(
            pk=besitz_id
        )
        punkte_services.schreibsperre(besitz.kind)
        if not ModBesitz.objects.filter(pk=besitz_id, status=BesitzStatus.IM_BAU).update(
            status=BesitzStatus.FERTIG, fertig_am=fertig_am
        ):
            return None
        woche = zaehlwoche(besitz.kind, fertig_am, ausser=besitz_id)
        ModBesitz.objects.filter(pk=besitz_id).update(
            zaehlt_ab_iso_jahr=woche.jahr, zaehlt_ab_iso_woche=woche.woche
        )
        besitz.refresh_from_db()
        kind = besitz.kind
        avatar = Avatar.objects.filter(pk=kind.pk).first()
        if (
            avatar is not None
            and avatar.thema_id == besitz.mod.thema_id
            and besitz.mod.slot.schluessel not in (avatar.angelegt or {})
        ):
            # Leerer Slot: der neue Mod wird gleich angelegt (sofort sichtbar)
            from .services import slot_belegen

            slot_belegen(kind, besitz.mod.slot.schluessel, besitz.mod)
        ort, _ = inszenierung(besitz.mod.thema)
        if sofort:
            audit.protokollieren(
                "avatar.bau_sofort_fertig",
                akteur=von,
                objekt=besitz,
                kind=kind,
                details={
                    "mod": besitz.mod.schluessel,
                    "geplant": besitz.fertig_geplant_am.isoformat(),
                },
            )
        ereignisse.veroeffentlichen(
            events.MOD_FERTIG,
            daten={
                "besitz": besitz.pk,
                "mod": besitz.mod.name,
                "slot": besitz.mod.slot.schluessel,
                "seltenheit": besitz.mod.seltenheit,
                "werkstatt": ort,
                "zaehlt_ab": str(woche),
            },
            schluessel=f"{events.MOD_FERTIG}:{besitz.pk}",
            kind=kind,
            akteur=von,
        )
    return besitz


def _abzeichen_pruefen(kinder):
    """Metrik ``ausbaustufe`` hat sich (evtl.) geändert: Abzeichen/Meilensteine prüfen, sofern die
    Engine (AP23) vorhanden ist. Fehler dort brechen die Fertigstellung nicht ab; der stündliche
    ``wochen_sicherstellen`` holt alles nach."""
    from apps.spielregeln import services as spielregeln_services

    pruefen = getattr(spielregeln_services, "abzeichen_pruefen", None)
    if pruefen is None:
        return
    for kind in kinder:
        try:
            with transaction.atomic():
                pruefen(kind)
        except Exception:  # noqa: BLE001 - Catch-up über den Wochenjob
            logger.exception("Abzeichen-Prüfung nach Mod-Fertigstellung fehlgeschlagen")


def fertigstellen(jetzt=None) -> dict:
    """Job ``mods_fertigstellen``: alle fälligen Bauaufträge (Catch-up, geplante Reihenfolge)."""
    jetzt = jetzt or zeit.jetzt()
    faellig = list(
        ModBesitz.objects.filter(status=BesitzStatus.IM_BAU, fertig_geplant_am__lte=jetzt)
        .order_by("fertig_geplant_am", "id")
        .values_list("pk", "fertig_geplant_am")
    )
    fertig = []
    for pk, geplant in faellig:
        besitz = _fertig_setzen(pk, geplant)
        if besitz is not None:
            fertig.append(besitz)
    woche = zeit.aktuelle_woche(jetzt)
    kinder = {b.kind_id: b.kind for b in fertig}
    for b in ModBesitz.objects.filter(
        status=BesitzStatus.FERTIG, zaehlt_ab_iso_jahr=woche.jahr, zaehlt_ab_iso_woche=woche.woche
    ).select_related("kind"):
        kinder.setdefault(b.kind_id, b.kind)
    _abzeichen_pruefen(kinder.values())
    return {"fertig": len(fertig), "faellig": len(faellig), "kinder_geprueft": len(kinder)}


def sofort_fertigstellen(besitz, *, von, jetzt=None) -> ModBesitz:
    """Eltern: Bau sofort fertigstellen (Audit). Die Zeitbremse gilt weiter."""
    if getattr(von, "rolle", None) != "eltern":
        raise ModFehler("Nur Eltern können einen Bau sofort fertigstellen.")
    pk = besitz.pk if isinstance(besitz, ModBesitz) else besitz
    ergebnis = _fertig_setzen(pk, jetzt or zeit.jetzt(), von=von, sofort=True)
    if ergebnis is None:
        raise ModFehler("Dieser Bau ist schon fertig.")
    _abzeichen_pruefen([ergebnis.kind])
    return ergebnis


# --- Anlegen --------------------------------------------------------------------------------


def anlegen(kind, mod):
    """Eigenen, fertigen Mod des aktuellen Themas in seinen Slot legen (tauscht den alten)."""
    from .services import AvatarFehler, slot_belegen

    mod = _mod_laden(mod)
    if not ModBesitz.objects.filter(kind=kind, mod=mod, status=BesitzStatus.FERTIG).exists():
        raise ModFehler("Diesen Mod hast du noch nicht fertig.")
    try:
        return slot_belegen(kind, mod.slot.schluessel, mod)
    except AvatarFehler as exc:
        raise ModFehler(str(exc)) from None


# --- Themenwechsel --------------------------------------------------------------------------


@dataclass(frozen=True)
class Themenwechsel:
    alt: Thema
    neu: Thema
    verlorene_mods: int
    davon_im_bau: int
    wert: int
    ausbaustufe_vorher: int
    rang_name: str
    rang_selten: str
    mods_bis_meilenstein: int
    wochen_mindestens: int

    @property
    def pruefwert(self) -> str:
        """Bestätigung gilt nur für genau diese Zahlen (Kauf im anderen Tab -> neue Warnung)."""
        return f"{self.neu.schluessel}:{self.verlorene_mods}:{self.davon_im_bau}:{self.wert}"


def _neues_thema(schluessel) -> Thema:
    thema = Thema.objects.filter(schluessel=schluessel, aktiv=True, nur_eltern=False).first()
    if thema is None:
        raise ModFehler("Bitte wähle ein Thema.")
    return thema


def themenwechsel_vorschau(kind, thema_schluessel) -> Themenwechsel:
    """Konkrete Zahlen für den Warn-Dialog."""
    avatar = Avatar.objects.select_related("thema").filter(pk=kind.pk).first()
    if avatar is None:
        raise ModFehler("Wähle zuerst deinen Avatar.")
    neu = _neues_thema(thema_schluessel)
    if neu.pk == avatar.thema_id:
        raise ModFehler("Das ist schon dein Thema.")
    besitz = ModBesitz.objects.filter(kind=kind, status__in=AKTIV, mod__thema=avatar.thema)
    stand = ausbaustufe(kind)
    benoetigt = (
        ModDefinition.objects.filter(
            thema=neu, aktiv=True, seltenheit=stand.rang_stufe, modset__isnull=True
        )
        .values("slot")
        .distinct()
        .count()
    )
    pro_woche = einstellungen.wert(EINSTELLUNG_PRO_WOCHE)
    return Themenwechsel(
        alt=avatar.thema,
        neu=neu,
        verlorene_mods=besitz.count(),
        davon_im_bau=besitz.filter(status=BesitzStatus.IM_BAU).count(),
        wert=besitz.aggregate(s=Sum("preis_bezahlt"))["s"] or 0,
        ausbaustufe_vorher=stand.aktuell,
        rang_name=stand.rang_name,
        rang_selten=stand.rang_selten,
        mods_bis_meilenstein=benoetigt,
        wochen_mindestens=math.ceil(benoetigt / pro_woche) if benoetigt else 0,
    )


def thema_wechseln(kind, thema_schluessel, *, pruefwert, jetzt=None) -> Themenwechsel:
    """Themenwechsel nach bestätigter Warnung. ``pruefwert`` muss zur aktuellen Vorschau passen."""
    from .services import AvatarFehler, figur_pruefen, hash_aktualisieren

    if getattr(kind, "rolle", None) != "kind":
        raise ModFehler("Nur Kinder wechseln ihr Thema.")
    jetzt = jetzt or zeit.jetzt()
    with transaction.atomic():
        punkte_services.schreibsperre(kind)
        vorschau = themenwechsel_vorschau(kind, thema_schluessel)
        if pruefwert != vorschau.pruefwert:
            raise ModFehler("Deine Mods haben sich geändert. Bitte lies die Warnung noch einmal.")
        avatar = Avatar.objects.select_related("thema").get(pk=kind.pk)
        verloren = ModBesitz.objects.filter(
            kind=kind, status__in=AKTIV, mod__thema=avatar.thema
        ).update(status=BesitzStatus.VERLOREN, verloren_am=jetzt)
        figur = dict(avatar.figur)
        try:
            figur = figur_pruefen(figur, vorschau.neu)
        except AvatarFehler:  # Frisur passt nicht zum neuen Thema
            figur = figur_pruefen({**figur, "frisur": (vorschau.neu.figur_varianten or [""])[0]})
        avatar.thema = vorschau.neu
        avatar.figur = figur
        avatar.angelegt = {}
        avatar.thema_gewaehlt_am = jetzt
        avatar.save(update_fields=["thema", "figur", "angelegt", "thema_gewaehlt_am"])
        hash_aktualisieren(avatar)
        details = {
            "alt": vorschau.alt.schluessel,
            "neu": vorschau.neu.schluessel,
            "verlorene_mods": verloren,
            "davon_im_bau": vorschau.davon_im_bau,
            "wert": vorschau.wert,
            "ausbaustufe_vorher": vorschau.ausbaustufe_vorher,
        }
        audit.protokollieren(
            "avatar.thema_gewechselt", akteur=kind, objekt=avatar, kind=kind, details=details
        )
        ereignisse.veroeffentlichen(
            events.THEMA_GEWECHSELT,
            daten={
                **details,
                "thema": vorschau.neu.name,
                "verloren": verloren,
            },
            kind=kind,
            akteur=kind,
        )
    return vorschau


# --- Eltern ---------------------------------------------------------------------------------


def eltern_uebersicht(jetzt=None) -> list[dict]:
    """Je aktivem Kind: Thema, Ausbaustufe, laufende Bauaufträge, zuletzt fertige Mods."""
    jetzt = jetzt or zeit.jetzt()
    zeilen = []
    for kind in konten.aktive_kinder():
        zeilen.append(
            {
                "kind": kind,
                "stufe": ausbaustufe(kind, jetzt),
                "bau": bauauftraege(kind, jetzt),
                "fertig": list(
                    ModBesitz.objects.filter(kind=kind, status=BesitzStatus.FERTIG)
                    .select_related("mod", "mod__slot")
                    .order_by("-fertig_am", "-id")[:6]
                ),
            }
        )
    return zeilen


def _tage_text(stunden: int) -> str:
    """Stunden als Tage für das Eingabefeld ("3", "1,5", "0,04")."""
    text = f"{stunden / 24:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def standards() -> list[dict]:
    """Rang-Standards je Seltenheit mit wirksamen Werten (globaler Faktor)."""
    return [
        {
            "rang": r,
            "preis_wirksam": spielregeln.mod_preis(r.mod_preis),
            "bauzeit_wirksam": dauer_text(spielregeln.mod_bauzeit_stunden(r.bauzeit_stunden)),
            "bauzeit_tage": _tage_text(r.bauzeit_stunden),
        }
        for r in spielregeln.raenge()
    ]
