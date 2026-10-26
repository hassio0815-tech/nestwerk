"""Charakter-Bildschirm der Dungeon-Seite: Figur in der Mitte, die 6 Slots des aktuellen Rangs
als Kacheln (gefüllt / im Bau / leer), Ausbaustufe und ein nächstes Ziel."""

from dataclasses import dataclass

from django.urls import reverse

from apps.punkte import selectors as punkte_selectors

from . import services
from .models import BesitzStatus, Slot
from .mods import _aktive_besitze, _raenge_nach_stufe, ausbaustufe, bauauftraege


@dataclass
class SlotKachel:
    slot: Slot
    zustand: str  # gefuellt | im_bau | leer
    mod: object = None
    besitz: object = None
    bau: dict | None = None
    selten: str = "common"
    link: str = ""


def _ziel_text(stufe, raenge_map, kind) -> str:
    fehlt = max(0, stufe.slots - stufe.aktuell)
    if fehlt:
        from apps.sondertag import selectors as sondertag

        f = sondertag.fortschritt(kind)
        if f.art in ("unterwegs", "ab_rang") and f.text:
            return f.text
        return f"Noch {fehlt} {'Slot' if fehlt == 1 else 'Slots'} bis zur vollen Ausbaustufe!"
    naechster = raenge_map.get(stufe.rang_stufe + 1)
    if naechster is not None:
        return f"Alle Slots voll! Als Nächstes: Rang {naechster.name}."
    return "Alles ausgebaut. Höchster Rang erreicht!"


def charakter(kind, jetzt=None) -> dict | None:
    """Kontext für ``avatar/_charakter.html``; ``None``, solange es keinen Avatar gibt."""
    stufe = ausbaustufe(kind, jetzt)
    if stufe.thema is None:
        return None
    raenge_map = _raenge_nach_stufe()
    selten = stufe.rang_selten
    fertig = {
        b.mod.slot_id: b
        for b in _aktive_besitze(kind, stufe.thema.pk).filter(
            status=BesitzStatus.FERTIG, mod__modset__isnull=True, mod__seltenheit=stufe.rang_stufe
        )
    }
    bau = {}
    for eintrag in bauauftraege(kind, jetzt):
        if eintrag["mod"].thema_id == stufe.thema.pk:
            bau.setdefault(eintrag["mod"].slot_id, eintrag)
    kacheln = []
    for slot in Slot.objects.all():
        if slot.pk in fertig:
            b = fertig[slot.pk]
            kacheln.append(SlotKachel(slot, "gefuellt", b.mod, b, selten=selten))
        elif slot.pk in bau:
            e = bau[slot.pk]
            kacheln.append(
                SlotKachel(slot, "im_bau", e["mod"], e["besitz"], e, selten=selten)
            )
        else:
            link = f"{reverse('avatar:shop')}?slot={slot.schluessel}"
            kacheln.append(SlotKachel(slot, "leer", link=link))
    haelfte = (len(kacheln) + 1) // 2
    return {
        "name": services.avatar_name(kind),
        "label": f"Ausbaustufe {stufe.aktuell}/{stufe.slots}",
        "kind": kind,
        "stufe": stufe,
        "links": kacheln[:haelfte],
        "rechts": kacheln[haelfte:],
        "guthaben": punkte_selectors.verfuegbar(kind),
        "ziel": _ziel_text(stufe, raenge_map, kind),
    }
