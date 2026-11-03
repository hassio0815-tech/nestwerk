"""Tagesziel, Anpassung, Schonung und Wochenserie (SPEC 21.2). Nur Rechnen und Lernstände
fortschreiben; Punkte und Ereignisse stehen in ``services``.

- Mindesttag (Einstellung ``lernen.mindesttag_minuten``): ab dort zählt der Tag als geübt.
- Das persönliche Tagesziel startet bei ``lernen.tagesziel_minuten`` und sinkt (nie unter den
  Mindesttag) nach ``lernen.ziel_senken_nach_tagen`` verfehlten Tagen. Höher geht es nur auf
  Vorschlag und mit Zustimmung des Kindes.
- Die Serie zählt in Wochen. Pausentage der Eltern und Ferien senken, was die Woche verlangt;
  eine gerissene Serie fängt bei null an und berührt nie vergebene Punkte.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q

from apps.kern.einstellungen import wert

from .models import Lernpause, Lerntag, Lernziel, PausenGrund

FENSTER_TAGE = 14  # "die letzten zwei Wochen"
SERIE_MAX_WOCHEN = 104


# --- Schonung ----------------------------------------------------------------------------------


def pausentage(kind, von, bis):
    """Alle Tage zwischen ``von`` und ``bis`` (einschließlich), die geschont werden."""
    tage = set()
    pausen = Lernpause.objects.filter(Q(kind__isnull=True) | Q(kind=kind), von__lte=bis)
    for p in pausen:
        ende = min(p.bis or bis, bis)
        tag = max(p.von, von)
        while tag <= ende:
            tage.add(tag)
            tag += timedelta(days=1)
    return tage


def ferien_abgleichen(heute):
    """Bringt die offene Ferien-Pause (alle Kinder) in Einklang mit dem Schalter. Idempotent.

    An: es gibt eine offene Pause ab heute (oder früher). Aus: eine offene Pause endet gestern
    (hat sie erst heute begonnen, entfällt sie)."""
    offen = Lernpause.objects.filter(kind__isnull=True, bis__isnull=True, grund=PausenGrund.FERIEN)
    if wert("lernen.ferien_schalter"):
        if not offen.exists():
            Lernpause.objects.create(von=heute, grund=PausenGrund.FERIEN)
        return
    for pause in offen:
        if pause.von >= heute:
            pause.delete()
        else:
            pause.bis = heute - timedelta(days=1)
            pause.save(update_fields=["bis"])


def ist_pausentag(kind, tag):
    return tag in pausentage(kind, tag, tag)


# --- Ziel und Tag ------------------------------------------------------------------------------


def ziel_holen(kind, heute):
    ziel, _neu = Lernziel.objects.get_or_create(
        kind=kind, defaults={"ziel_minuten": wert("lernen.tagesziel_minuten"), "seit": heute}
    )
    return ziel


def lerntag_holen(kind, heute):
    """Der Lerntag von heute; ein noch nicht erreichtes Ziel folgt dem persönlichen Ziel."""
    ziel = ziel_holen(kind, heute)
    tag, neu = Lerntag.objects.get_or_create(
        kind=kind, datum=heute, defaults={"ziel_minuten": ziel.ziel_minuten}
    )
    if not neu and not tag.erreicht and tag.ziel_minuten != ziel.ziel_minuten:
        tag.ziel_minuten = ziel.ziel_minuten
        tag.save(update_fields=["ziel_minuten"])
    return tag


@dataclass(frozen=True)
class Anpassung:
    art: str  # "gesenkt" | "vorschlag" | ""
    minuten: int = 0


KEINE = Anpassung("")


def ziel_anpassen(kind, heute):
    """Prüft die letzten zwei Wochen: Ziel senken (ohne Vorwurf) oder Erhöhung vorschlagen.

    Gezählt werden nur Tage nach dem ersten Lerntag und nach der letzten Änderung, ohne
    Schonungstage. Ein verfehlter Tag ist ein Tag ohne erreichtes Tagesziel."""
    ziel = ziel_holen(kind, heute)
    start = max(ziel.seit, ziel.geaendert_am or ziel.seit, heute - timedelta(days=FENSTER_TAGE))
    tage = [start + timedelta(days=i) for i in range(1, (heute - start).days)]
    if not tage:
        return KEINE
    pausen = pausentage(kind, tage[0], tage[-1])
    erreicht = set(
        Lerntag.objects.filter(kind=kind, datum__in=tage, erreicht=True).values_list(
            "datum", flat=True
        )
    )
    schritt = wert("lernen.ziel_schritt_minuten")
    nach = wert("lernen.ziel_senken_nach_tagen")
    verlangt = [t for t in tage if t not in pausen]
    letzte = verlangt[-nach:]
    mindest = wert("lernen.mindesttag_minuten")
    if len(letzte) == nach and not erreicht.intersection(letzte) and ziel.ziel_minuten > mindest:
        ziel.ziel_minuten = max(mindest, ziel.ziel_minuten - schritt)
        ziel.vorschlag_minuten = None
        ziel.geaendert_am = heute
        ziel.save()
        return Anpassung("gesenkt", ziel.ziel_minuten)
    basis = wert("lernen.tagesziel_minuten")
    if (
        ziel.vorschlag_minuten is None
        and ziel.ziel_minuten < basis
        and len(erreicht) >= wert("lernen.ziel_vorschlag_tage")
    ):
        ziel.vorschlag_minuten = min(ziel.ziel_minuten + schritt, basis)
        ziel.save(update_fields=["vorschlag_minuten"])
        return Anpassung("vorschlag", ziel.vorschlag_minuten)
    return KEINE


def vorschlag_entscheiden(kind, heute, *, annehmen):
    """Das Kind nimmt den Vorschlag an oder lässt ihn. Beides startet ein neues Zeitfenster."""
    ziel = ziel_holen(kind, heute)
    if ziel.vorschlag_minuten is None:
        return ziel
    if annehmen:
        ziel.ziel_minuten = ziel.vorschlag_minuten
    ziel.vorschlag_minuten = None
    ziel.geaendert_am = heute
    ziel.save()
    return ziel


# --- Wochenserie -------------------------------------------------------------------------------

GESCHAFFT, GESCHONT, VERFEHLT = "geschafft", "geschont", "verfehlt"


@dataclass(frozen=True)
class Serie:
    wochen: int  # Wochen in Folge, die zählen
    tage_diese_woche: int  # geübte Tage (ab Mindesttag) in der laufenden Woche
    bedarf: int  # so viele Tage verlangt die Woche (Schonung abgezogen)
    geschont: bool  # die laufende Woche verlangt nichts


def montag(tag):
    return tag - timedelta(days=tag.weekday())


def _woche(montag_tag, geuebt, pausen, bedarf):
    tage = [montag_tag + timedelta(days=i) for i in range(7)]
    anzahl = sum(1 for t in tage if t in geuebt)
    noetig = max(0, bedarf - sum(1 for t in tage if t in pausen))
    if anzahl >= bedarf:
        return GESCHAFFT, anzahl, bedarf
    if noetig == 0:
        return GESCHONT, anzahl, 0
    return (GESCHAFFT if anzahl >= noetig else VERFEHLT), anzahl, noetig


def serie(kind, heute):
    """Wochenserie bis heute. Die laufende Woche bricht nie ab, sie zählt erst, wenn sie reicht."""
    ziel = Lernziel.objects.filter(kind=kind).first()
    bedarf = wert("lernen.serie_tage_pro_woche")
    diese = montag(heute)
    if ziel is None:
        return Serie(0, 0, bedarf, False)
    erste = max(montag(ziel.seit), diese - timedelta(weeks=SERIE_MAX_WOCHEN))
    geuebt = set(
        Lerntag.objects.filter(kind=kind, datum__gte=erste, mindesttag=True).values_list(
            "datum", flat=True
        )
    )
    pausen = pausentage(kind, erste, heute + timedelta(days=6))
    if wert("lernen.ferien_schalter"):
        # Die offene Ferien-Pause entsteht erst beim nächsten Abgleich; bis dahin gilt der
        # Rest der Woche schon als geschont.
        pausen.update(heute + timedelta(days=i) for i in range(7 - heute.weekday()))
    status, anzahl, noetig = _woche(diese, geuebt, pausen, bedarf)
    wochen = 1 if status == GESCHAFFT else 0
    woche = diese - timedelta(weeks=1)
    while woche >= erste:
        status_alt, _anzahl, _noetig = _woche(woche, geuebt, pausen, bedarf)
        if status_alt == VERFEHLT:
            break
        wochen += 1 if status_alt == GESCHAFFT else 0
        woche -= timedelta(weeks=1)
    return Serie(wochen, anzahl, noetig, status == GESCHONT)
