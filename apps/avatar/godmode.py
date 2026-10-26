"""God-Mode-Zyklen und Mod-Sets (AP27, ARCHITECTURE 7.6/13.1 O3, Entscheidung 1).

- **Zyklus:** Nach dem Aufstieg in den höchsten Rang (God Mode) zählt jede aktive Woche *nach*
  der Aufstiegswoche. Zyklus K umfasst die aktiven Wochen ``(K-1)*L+1 … K*L`` (L = Einstellung
  ``avatar.godmode_zyklus_aktivwochen``, Startwert 26). Zyklus K ist ab Beginn freigeschaltet
  (aktive Wochen >= (K-1)*L), endlos.
- **Mod-Set K:** 6 Mods (1 je Slot) zum God-Mode-Rangpreis (``preis = NULL`` -> Rang-Standard),
  erzeugt aus den Seltenheit-6-Bauplänen des Themas mit Varianten-Parametern (Farbton-Drehung,
  Muster, Spiegelung). Entsteht beim ersten Bedarf (``set_sicherstellen``), danach sind es
  normale Daten (Eltern können sie bearbeiten). Kaufbar, sobald Zyklus K freigeschaltet ist.
- **Ausbaustufe des Sets:** zählende Slots wie bei den Seltenheiten (fertig, Zeitbremse,
  aktuelles Thema), getrennt von Seltenheit 6 (``mods.ausbaustufe(...).je_set``).
- **Metriken** (``registry``): ``godmode_aktivwochen``, ``godmode_zyklus`` (Bereiche
  ``zyklus-K`` -> 1 = Wochen des Zyklus geschafft), ``godmode_set_vollstaendig`` (Bereiche
  ``zyklus-K`` -> zählende Slots des Sets K). Die Meilenstein-Regel (``sondertag``) verknüpft
  beide je Bereich: Zyklus geschafft UND Set vollständig.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction

from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.spielregeln import selectors as spielregeln

from .generator import farben
from .generator.bibliothek import MUSTER
from .models import ModDefinition, ModSet, Slot

EINSTELLUNG_ZYKLUS = "avatar.godmode_zyklus_aktivwochen"
FARBTON_SCHRITT = 72  # Grad je Zyklus (5 verschiedene Farbwelten, dann mit anderem Muster)
SET_MUSTER = [m for m in MUSTER if m != "keins"]


def zyklus_laenge() -> int:
    return int(einstellungen.wert(EINSTELLUNG_ZYKLUS))


def godmode_stufe() -> int | None:
    stufen = [r.stufe for r in spielregeln.raenge()]
    return max(stufen) if stufen else None


@dataclass(frozen=True)
class Zyklus:
    """Stand eines Kindes in den God-Mode-Zyklen. ``aktuell`` = laufender Zyklus (ab 1)."""

    godmode: bool
    seit: object  # datetime des Aufstiegs oder None
    aktivwochen: int
    laenge: int

    @property
    def aktuell(self) -> int:
        return self.aktivwochen // self.laenge + 1 if self.godmode else 0

    @property
    def geschafft(self) -> int:
        """Abgeschlossene Zyklen (Wochen erfüllt)."""
        return self.aktivwochen // self.laenge if self.godmode else 0

    @property
    def wochen_im_zyklus(self) -> int:
        return self.aktivwochen % self.laenge if self.godmode else 0

    @property
    def wochen_fehlen(self) -> int:
        return self.laenge - self.wochen_im_zyklus if self.godmode else 0

    def freigeschaltet(self, nummer: int) -> bool:
        return self.godmode and 1 <= nummer <= self.aktuell


def zyklus(kind, jetzt=None) -> Zyklus:
    laenge = zyklus_laenge()
    stufe = godmode_stufe()
    fakt = None
    if stufe is not None:
        fakt = next((f for f in spielregeln.rang_aufstiege(kind) if f.rang.stufe == stufe), None)
    if fakt is None:
        return Zyklus(False, None, 0, laenge)
    heute = zeit.heute(jetzt)
    ab = IsoWoche.von(fakt.erreicht_am).sonntag + timedelta(days=1)
    if heute < ab:
        return Zyklus(True, fakt.erreicht_am, 0, laenge)
    wochen = {IsoWoche.von(tag) for tag in spielregeln.aktive_tage(kind, ab, heute)}
    return Zyklus(True, fakt.erreicht_am, len(wochen), laenge)


# --- Mod-Sets erzeugen ------------------------------------------------------------------------


def _farbton_drehen(farbe_hex: str, grad: int) -> str:
    r, g, b = farben.hex_zu_rgb(farbe_hex)
    h, l_, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    r2, g2, b2 = colorsys.hls_to_rgb((h + grad / 360) % 1.0, l_, s)
    return farben.rgb_zu_hex(round(r2 * 255), round(g2 * 255), round(b2 * 255))


def _farbe_variieren(angabe: str, palette: dict, grad: int) -> str:
    """Hex-Farben und Palette-Token (p1-p6) im Farbton drehen; Zusätze (+, -, @40) bleiben."""
    treffer = farben.FARBE_RE.match(angabe or "")
    if not treffer:
        return angabe
    roh, token, zusatz, alpha = treffer.groups()
    if roh:
        basis = "#" + roh.lower()
    elif token in palette:
        basis = palette[token]
    else:
        return angabe  # haut, haar, a/b/c bleiben
    return _farbton_drehen(basis, grad) + (zusatz or "") + (f"@{alpha}" if alpha else "")


def teile_variieren(teile: list, nummer: int, palette: dict, slot: str) -> list:
    """Varianten-Parameter je Zyklus: Farbton, Muster, Spiegelung (deterministisch)."""
    grad = (nummer * FARBTON_SCHRITT) % 360 or 36
    muster = SET_MUSTER[(nummer - 1) % len(SET_MUSTER)]
    ergebnis = []
    for t in teile:
        neu = dict(t)
        if t.get("farben"):
            neu["farben"] = {k: _farbe_variieren(v, palette, grad) for k, v in t["farben"].items()}
        if t.get("muster_farbe"):
            neu["muster_farbe"] = _farbe_variieren(t["muster_farbe"], palette, grad)
        if t is teile[0]:
            neu["muster"] = muster
        if slot != "hintergrund" and nummer % 2 == 0:
            neu["spiegeln"] = not t.get("spiegeln", False)
        ergebnis.append(neu)
    return ergebnis


def _set_name(thema, nummer) -> str:
    return f"{thema.name}: God-Mode-Set {nummer}"[:60]


def _mod_name(basis: str, nummer: int) -> str:
    zusatz = f" · Set {nummer}"
    return basis[: 60 - len(zusatz)] + zusatz


def set_sicherstellen(thema, nummer: int) -> ModSet | None:
    """Mod-Set ``nummer`` des Themas anlegen (idempotent, parallel-sicher). ``None``, wenn das
    Thema keine Seltenheit-6-Mods hat."""
    if nummer < 1:
        raise ValueError("Mod-Sets beginnen bei 1")
    vorhanden = ModSet.objects.filter(thema=thema, nummer=nummer).first()
    if vorhanden is not None:
        return vorhanden
    basis = list(
        ModDefinition.objects.filter(thema=thema, seltenheit=6, modset__isnull=True)
        .select_related("slot")
        .order_by("slot__ebene")
    )
    if not basis:
        return None
    try:
        with transaction.atomic():
            modset = ModSet.objects.create(
                thema=thema, nummer=nummer, name=_set_name(thema, nummer)
            )
            for mod in basis:
                ModDefinition.objects.create(
                    schluessel=f"{mod.schluessel}-set{nummer}"[:60],
                    thema=thema,
                    slot=mod.slot,
                    seltenheit=6,
                    modset=modset,
                    name=_mod_name(mod.name, nummer),
                    beschreibung=f"God-Mode-Set {nummer}: {mod.beschreibung}"[:200],
                    preis=None,
                    bauzeit_stunden=None,
                    bauplan={
                        "teile": teile_variieren(
                            (mod.bauplan or {}).get("teile", []),
                            nummer,
                            thema.palette or {},
                            mod.slot.schluessel,
                        )
                    },
                    svg_override="",
                )
    except IntegrityError:  # parallel angelegt
        return ModSet.objects.filter(thema=thema, nummer=nummer).first()
    return modset


def sets_sicherstellen(kind, thema, stand: Zyklus | None = None) -> list[ModSet]:
    """Alle freigeschalteten Sets des Kindes im Thema (für den Shop)."""
    stand = stand or zyklus(kind)
    if not stand.godmode or thema is None:
        return []
    sets = [set_sicherstellen(thema, n) for n in range(1, stand.aktuell + 1)]
    return [s for s in sets if s is not None]


def slots_je_set() -> int:
    return Slot.objects.count()


# --- Metriken (kern.registry) -----------------------------------------------------------------


def metrik_aktivwochen(kind) -> int:
    return zyklus(kind).aktivwochen


def metrik_zyklus(kind) -> int:
    return zyklus(kind).geschafft


def metrik_zyklus_bereiche(kind) -> dict[str, tuple[int, str]]:
    z = zyklus(kind)
    return {f"zyklus-{n}": (int(n <= z.geschafft), f"Zyklus {n}") for n in range(1, z.aktuell + 1)}


def metrik_set_bereiche(kind) -> dict[str, tuple[int, str]]:
    from .mods import ausbaustufe

    z = zyklus(kind)
    if not z.godmode:
        return {}
    je_set = ausbaustufe(kind).je_set
    return {f"zyklus-{n}": (je_set.get(n, 0), f"Set {n}") for n in range(1, z.aktuell + 1)}


def metrik_set_vollstaendig(kind) -> int:
    """Anzahl vollständiger Sets (alle Slots zählen)."""
    from .mods import ausbaustufe

    slots = slots_je_set()
    return sum(1 for wert in ausbaustufe(kind).je_set.values() if slots and wert >= slots)
