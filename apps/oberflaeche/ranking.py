"""Familien-Ranking (AP30, SPEC 8.2, Entscheidung 25): Fortschritts-Schaufenster statt Rangliste.

Drei Modi (``oberflaeche.ranking_modus``, Eltern schalten um):

- ``schaufenster`` (Standard): alle Kinder nebeneinander mit Avatar, Rang, Serie, Abzeichen,
  Ausbaustufe. Keine Reihenfolge nach Leistung, kein "letzter Platz".
- ``held``: Held der Woche (größter Zuwachs gegenüber dem eigenen Schnitt) und Vorwoche.
- ``rohpunkte``: XP-Tabelle (Woche und Gesamt), sichtbar, aber nachrangig.

Kinder bekommen nur Anzeigewerte; Eltern-Details (Zuwachs in Prozent aller Kinder, Pausen) liefert
``eltern_zusatz``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from apps.avatar import selectors as avatar
from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.konten import akzent
from apps.konten import selectors as konten
from apps.punkte import selectors as punkte
from apps.spielregeln import selectors as spielregeln

from .einstellungen import RANKING_MODI  # noqa: F401 (auch für Views)

MODUS_TEXTE = {
    "schaufenster": _("Schaufenster"),
    "held": _("Held der Woche"),
    "rohpunkte": _("Rohpunkte"),
}
TOP_ABZEICHEN = 3


@dataclass
class Eintrag:
    kind: object
    akzent: str
    rang: object
    serie: int
    abzeichen: list
    abzeichen_anzahl: int
    ausbau: object | None
    xp_woche: int
    xp_gesamt: int
    pausiert: bool
    held_titel: int
    ist_held: bool = False
    war_held: bool = False


@dataclass
class Ansicht:
    modus: str
    modus_text: str
    eintraege: list[Eintrag] = field(default_factory=list)
    helden: list[Eintrag] = field(default_factory=list)  # Held der Vorwoche (zuletzt bewertet)
    vorwoche_helden: list[Eintrag] = field(default_factory=list)
    woche: IsoWoche | None = None
    vorwoche: IsoWoche | None = None
    nach_woche: list[Eintrag] = field(default_factory=list)
    nach_gesamt: list[Eintrag] = field(default_factory=list)

    @property
    def leer(self):
        return not self.eintraege


def modus() -> str:
    wert = einstellungen.wert("oberflaeche.ranking_modus")
    return wert if wert in RANKING_MODI else "schaufenster"


def _ausbau(kind):
    if not avatar.hat_avatar(kind):
        return None
    try:
        stufe = avatar.ausbaustufe(kind)
    except Exception:  # Darstellung darf nie am Avatar scheitern
        return None
    return stufe if stufe.slots else None


def _eintrag(kind, woche: IsoWoche, jetzt) -> Eintrag:
    fortschritt = spielregeln.rang_fortschritt(kind)
    vitrine = spielregeln.vitrine(kind)
    return Eintrag(
        kind=kind,
        akzent=akzent.akzent_name(kind),
        rang=fortschritt.rang,
        serie=spielregeln.stand(kind, jetzt).wochenserie,
        abzeichen=vitrine.verdient[:TOP_ABZEICHEN],
        abzeichen_anzahl=len(vitrine.verdient),
        ausbau=_ausbau(kind),
        xp_woche=punkte.xp_zeitraum(woche.montag, woche.sonntag, kind=kind),
        xp_gesamt=fortschritt.xp,
        pausiert=spielregeln.ist_pausiert(kind, zeit.heute(jetzt)),
        held_titel=spielregeln.held_titel(kind),
    )


def ansicht(jetzt=None, *, modus_wert: str | None = None) -> Ansicht:
    jetzt = jetzt or zeit.jetzt()
    woche = IsoWoche.von(jetzt)
    letzte, davor = woche.vorherige(), woche.vorherige().vorherige()
    a = Ansicht(modus=modus_wert or modus(), modus_text="", woche=woche, vorwoche=letzte)
    a.modus_text = MODUS_TEXTE[a.modus]
    a.eintraege = [_eintrag(kind, woche, jetzt) for kind in konten.aktive_kinder()]
    nach_id = {e.kind.pk: e for e in a.eintraege}
    for w, ziel, flag in ((letzte, a.helden, "ist_held"), (davor, a.vorwoche_helden, "war_held")):
        for zeile in spielregeln.helden(w):
            e = nach_id.get(zeile.kind_id)
            if e is not None:
                ziel.append(e)
                if flag == "ist_held":
                    e.ist_held = True
                else:
                    e.war_held = True
    a.nach_woche = sorted(a.eintraege, key=lambda e: (-e.xp_woche, e.kind.anzeigename))
    a.nach_gesamt = sorted(a.eintraege, key=lambda e: (-e.xp_gesamt, e.kind.anzeigename))
    return a


def eltern_zusatz(jetzt=None) -> dict:
    """Nur Eltern: Zuwächse aller Kinder in der letzten bewerteten Woche."""
    jetzt = jetzt or zeit.jetzt()
    letzte = IsoWoche.von(jetzt).vorherige()
    zeilen = [
        {
            "kind": z.kind,
            "xp": z.xp_woche,
            "prozent": int(z.zuwachs_relativ * 100),
            "held": z.held_der_woche,
        }
        for z in spielregeln.zuwaechse(letzte)
    ]
    return {"woche": letzte, "zuwaechse": zeilen, "modi": list(MODUS_TEXTE.items())}
