"""Lesen für die Prüfungsvorbereitung (SPEC 21.7). Prüfungen gehören genau einem Kind: alle
Funktionen für Kinder filtern nach dem Kind (Geschwister sehen nie fremde Pläne). Nur
``fuer_eltern`` und ``alle_fuer_eltern`` lesen über Kinder hinweg."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q, Sum

from apps.kern.einstellungen import wert

from . import plan, selectors, tagesziel
from .models import (
    Frage,
    Freigabe,
    Lernsitzung,
    Lernziel,
    Material,
    MaterialStatus,
    PortionArt,
    PortionStatus,
    ProbePruefung,
    Pruefung,
    Pruefungsportion,
    PruefungStatus,
    Versuch,
)

AKTIVE = (PruefungStatus.GEPLANT, PruefungStatus.AKTIV)


# --- Prüfungen -----------------------------------------------------------------------------------


def pruefungen(kind):
    return Pruefung.objects.filter(kind=kind).select_related("fach")


def pruefung(kind, pk):
    """Prüfung des Kindes oder ``None`` (fremde gibt es hier nicht)."""
    return pruefungen(kind).filter(pk=pk).first()


def aktive_pruefungen(kind):
    return pruefungen(kind).filter(status__in=AKTIVE)


def fuer_eltern(pk):
    return Pruefung.objects.filter(pk=pk).select_related("fach", "kind").first()


def alle_fuer_eltern(kind):
    return Pruefung.objects.filter(kind=kind).select_related("fach")


def portion(kind, pk):
    """Portion einer Prüfung des Kindes oder ``None``."""
    return (
        Pruefungsportion.objects.filter(pk=pk, pruefung__kind=kind)
        .select_related("pruefung__fach", "stoff__thema", "stoff__material")
        .first()
    )


def probe(kind, pk):
    return (
        ProbePruefung.objects.filter(pk=pk, pruefung__kind=kind).select_related("pruefung").first()
    )


# --- Stoff ---------------------------------------------------------------------------------------


def stoff_fragen(stoff, kind):
    """Frage-IDs eines Stoffs, die das Kind nutzen darf (freigegeben, nie die von Geschwistern)."""
    if stoff.thema_id:
        qs = selectors.nutzbare_fragen(stoff.thema, kind)
    else:
        qs = Frage.objects.filter(
            material_id=stoff.material_id, kind=kind, freigabe=Freigabe.FREIGEGEBEN
        )
    return list(qs.order_by("id").values_list("id", flat=True))


def stoffe_fragen(pruefung_):
    """``{stoff-id (Text): (frage_id, ...)}``; eine Frage steht nur beim ersten Stoff."""
    gesehen = set()
    ergebnis = {}
    for s in pruefung_.stoffe.select_related("thema", "material"):
        ids = tuple(i for i in stoff_fragen(s, pruefung_.kind) if i not in gesehen)
        gesehen.update(ids)
        ergebnis[str(s.pk)] = ids
    return ergebnis


def themen_zur_auswahl(kind, fach):
    """Themen des Fachs mit Fragen, die das Kind nutzen darf."""
    return [
        t
        for t in selectors.themen_bis(fach, selectors.klassenstufe(kind, fach))
        if selectors.nutzbare_fragen(t, kind).exists()
    ]


def materialien_zur_auswahl(kind, fach):
    """Fertige Materialien des Kindes (zum Fach oder ohne Fach) mit freigegebenen Fragen."""
    qs = Material.objects.filter(kind=kind, status=MaterialStatus.BEREIT).filter(
        Q(fach__isnull=True) | Q(fach=fach)
    )
    return [
        m
        for m in qs
        if Frage.objects.filter(material=m, kind=kind, freigabe=Freigabe.FREIGEGEBEN).exists()
    ]


def portion_fragen(portion_):
    """Die Fragen einer Portion, die jetzt nutzbar sind (Reihenfolge wie im Plan)."""
    erlaubt = set(
        Frage.objects.filter(pk__in=portion_.fragen, freigabe=Freigabe.FREIGEGEBEN)
        .filter(Q(kind__isnull=True) | Q(kind=portion_.pruefung.kind))
        .values_list("pk", flat=True)
    )
    return [i for i in portion_.fragen if i in erlaubt]


# --- Planen: Eingabe für den reinen Planer --------------------------------------------------------


def parameter(kind, heute):
    ziel = Lernziel.objects.filter(kind=kind).first()
    return plan.Parameter(
        tagesziel=ziel.ziel_minuten if ziel else wert("lernen.tagesziel_minuten"),
        portion_minuten=wert("lernen.pruefung_portion_minuten"),
        sekunden_pro_frage=wert("lernen.pruefung_sekunden_pro_frage"),
        wdh_prozent=wert("lernen.pruefung_wiederholung_prozent"),
        leicht_minuten=wert("lernen.pruefung_leicht_minuten"),
        puffer_rhythmus=wert("lernen.pruefung_puffer_rhythmus"),
        abstaende=tuple(wert("lernen.box_abstaende_tage")),
        wochentage=frozenset(wert("lernen.pruefung_wochentage")),
        max_laenge=wert("lernen.pruefung_max_planlaenge"),
        vorlauf=wert("lernen.pruefung_vorlauf_tage"),
        ziel_zuschlag_max=wert("lernen.pruefung_ziel_zuschlag_max"),
    )


def pausentage_im_plan(kind, heute, termin):
    """Pausentage (Krankheit, Ferien) von heute bis zum Tag vor dem Termin."""
    if termin <= heute:
        return set()
    bis = termin - timedelta(days=1)
    tage = tagesziel.pausentage(kind, heute, bis)
    if wert("lernen.ferien_schalter"):
        tage.update(heute + timedelta(days=i) for i in range((bis - heute).days + 1))
    return tage


def eingabe(pruefung_, heute, *, nachholen=False):
    """Alle Argumente für ``plan.plane``: Stoff ohne schon Gelerntes, offene Pflicht-Wiederholungen,
    Pausentage. ``nachholen``: die vorhandenen Puffertage bleiben als Puffer stehen."""
    kind = pruefung_.kind
    p = parameter(kind, heute)
    stoffe = stoffe_fragen(pruefung_)
    erledigt = defaultdict(set)
    wdh_offen = []
    portionen = list(pruefung_.portionen.exclude(status=PortionStatus.VERSCHOBEN))
    for x in portionen:
        if x.art == PortionArt.NEU and x.status == PortionStatus.ERLEDIGT and x.stoff_id:
            erledigt[str(x.stoff_id)].update(x.fragen)
    neu_stoffe = {k: tuple(i for i in v if i not in erledigt[k]) for k, v in stoffe.items()}
    for x in portionen:
        if (
            x.art == PortionArt.WIEDERHOLUNG
            and x.status == PortionStatus.OFFEN
            and x.pflicht
            and x.stoff_id
            and set(x.fragen) <= erledigt[str(x.stoff_id)]
        ):
            wdh_offen.append(
                plan.WdhOffen(str(x.stoff_id), tuple(x.fragen), x.minuten, max(x.datum, heute))
            )
    puffer_fest = None
    if nachholen:
        puffer_fest = frozenset(
            x.datum
            for x in portionen
            if x.art == PortionArt.PUFFER and x.status == PortionStatus.OFFEN and x.datum >= heute
        )
    return {
        "p": p,
        "start": heute,
        "termin": pruefung_.termin,
        "blockiert": frozenset(pausentage_im_plan(kind, heute, pruefung_.termin)),
        "teile": plan.teilen(neu_stoffe, p),
        "stoffe": stoffe,
        "wdh_offen": wdh_offen,
        "puffer_fest": puffer_fest,
    }


def realitaetscheck(pruefung_, heute):
    """Rechnet den Plan frisch durch, ohne etwas zu speichern (für Vorschläge und Prüfung)."""
    return plan.plane(**eingabe(pruefung_, heute))


# --- Plan lesen ----------------------------------------------------------------------------------


def plan_portionen(pruefung_):
    """Alle sichtbaren Portionen (ohne verschobene), nach Datum."""
    return pruefung_.portionen.exclude(status=PortionStatus.VERSCHOBEN).select_related(
        "stoff__thema", "stoff__material"
    )


def heute_dran(pruefung_, heute):
    """Offene Portionen von heute und ältere, die noch nicht geschafft sind (ohne Puffer)."""
    return list(
        plan_portionen(pruefung_)
        .filter(status=PortionStatus.OFFEN, datum__lte=heute)
        .exclude(art=PortionArt.PUFFER)
    )


def heute_puffer(pruefung_, heute):
    return plan_portionen(pruefung_).filter(art=PortionArt.PUFFER, datum=heute).exists()


@dataclass(frozen=True)
class Fortschritt:
    erledigt: int
    gesamt: int
    minuten_erledigt: int
    minuten_gesamt: int

    @property
    def prozent(self):
        return round(100 * self.erledigt / self.gesamt) if self.gesamt else 0


def fortschritt(pruefung_):
    portionen = [x for x in plan_portionen(pruefung_) if x.art != PortionArt.PUFFER]
    erledigt = [x for x in portionen if x.status == PortionStatus.ERLEDIGT]
    return Fortschritt(
        len(erledigt),
        len(portionen),
        sum(x.minuten for x in erledigt),
        sum(x.minuten for x in portionen),
    )


def tagesuebersicht(pruefung_):
    """``[(Datum, [Portionen])]`` aufsteigend, ohne verschobene."""
    tage = defaultdict(list)
    for x in plan_portionen(pruefung_):
        tage[x.datum].append(x)
    return sorted(tage.items())


def portion_zaehler(portion_):
    """``(Antworten, Sekunden)`` aus allen Sitzungen zu dieser Portion. Ein Tippfehler-Versuch
    ("fast richtig") zählt nicht als Antwort."""
    antworten = Versuch.objects.filter(sitzung__portion=portion_).exclude(ergebnis="fast").count()
    sekunden = Lernsitzung.objects.filter(portion=portion_).aggregate(s=Sum("dauer_sekunden"))["s"]
    return antworten, sekunden or 0


def wochen(pruefung_):
    """``{Montag: [Portionen]}`` ohne Puffer und verschobene."""
    ergebnis = defaultdict(list)
    for x in plan_portionen(pruefung_).exclude(art=PortionArt.PUFFER):
        ergebnis[tagesziel.montag(x.datum)].append(x)
    return ergebnis


def offene_probe(pruefung_):
    return pruefung_.proben.filter(ende__isnull=True).first()


def letzte_probe(pruefung_):
    return pruefung_.proben.filter(ende__isnull=False).first()
