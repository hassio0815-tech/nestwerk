"""Lesen für lernen. Geschwister sehen die Fragen, die Mappe und die Sitzungen nie."""

from dataclasses import dataclass

from django.db.models import Q

from apps.kern.einstellungen import wert

from . import tagesziel
from .models import (
    Erwartung,
    Fach,
    Frage,
    Freigabe,
    Leistungsstufe,
    Lernpause,
    Lernsitzung,
    Lerntag,
    Lernziel,
    Thema,
)


def faecher(nur_aktive=True):
    return Fach.objects.filter(aktiv=True) if nur_aktive else Fach.objects.all()


def themen(fach, klassenstufe=None):
    """Themen eines Fachs; mit ``klassenstufe`` auch die stufenlosen."""
    qs = Thema.objects.filter(fach=fach)
    if klassenstufe is not None:
        qs = qs.filter(Q(klassenstufe=klassenstufe) | Q(klassenstufe__isnull=True))
    return qs


def themen_bis(fach, klassenstufe=None):
    """Themen bis zur Klassenstufe (frühere zum Wiederholen) und die stufenlosen.
    Ohne Klassenstufe alle Themen des Fachs."""
    qs = Thema.objects.filter(fach=fach)
    if klassenstufe is not None:
        qs = qs.filter(Q(klassenstufe__lte=klassenstufe) | Q(klassenstufe__isnull=True))
    return qs


def nutzbare_fragen(thema, kind):
    """Freigegebene Fragen: Startdaten und die eigenen des Kindes (nie die eines Geschwisters)."""
    return Frage.objects.filter(thema=thema, freigabe=Freigabe.FREIGEGEBEN).filter(
        Q(kind__isnull=True) | Q(kind=kind)
    )


def offene_fragen(kind=None):
    """Fragen, die auf die Freigabe durch die Eltern warten."""
    qs = Frage.objects.filter(freigabe=Freigabe.OFFEN)
    return qs.filter(kind=kind) if kind is not None else qs


def leistungsstufe(kind, fach):
    return Leistungsstufe.objects.filter(kind=kind, fach=fach).first()


def klassenstufe(kind, fach):
    """Klassenstufe des Kindes im Fach (Eltern tragen sie ein); ``None`` = unbekannt."""
    eintrag = leistungsstufe(kind, fach)
    return eintrag.klassenstufe if eintrag else None


def sprachstufe(kind, fach=None):
    """Sprachstufe der Texte (1 bis Klasse 4, 2 Klasse 5-7, 3 ab Klasse 8; unbekannt 2)."""
    from .texte import stufe_fuer

    if fach is not None:
        return stufe_fuer(klassenstufe(kind, fach))
    stufen = [
        s.klassenstufe for s in Leistungsstufe.objects.filter(kind=kind, klassenstufe__isnull=False)
    ]
    return stufe_fuer(min(stufen) if stufen else None)


def sitzung(kind, pk):
    """Sitzung eines Kindes oder ``None`` (fremde Sitzungen gibt es hier nicht)."""
    return Lernsitzung.objects.filter(kind=kind, pk=pk).select_related("fach", "thema").first()


def offene_sitzung(kind):
    """Die letzte noch nicht beendete Sitzung des Kindes."""
    return Lernsitzung.objects.filter(kind=kind, ende__isnull=True).select_related("fach").first()


def zustand(sitzung_):
    """Wo steht die Sitzung? ``frage`` (läuft), ``rueckschau`` (beendet) oder ``fertig``."""
    if sitzung_.ende is None:
        return "frage"
    return "fertig" if sitzung_.rueckschau_fertig else "rueckschau"


def quote(sitzung_):
    """Anteil richtiger Antworten (0 bis 1) oder ``None`` ohne Antworten."""
    return sitzung_.richtig / sitzung_.versuche if sitzung_.versuche else None


def _niveau(anteil):
    return 0 if anteil < 0.4 else (1 if anteil <= 0.75 else 2)


def vergleich(sitzung_):
    """Selbsteinschätzung vorher gegen das Ergebnis: ``passt``, ``mehr``, ``weniger`` oder leer."""
    anteil = quote(sitzung_)
    if anteil is None or not sitzung_.erwartung:
        return ""
    erwartet = [Erwartung.WENIGES, Erwartung.EINIGES, Erwartung.VIELES].index(sitzung_.erwartung)
    echt = _niveau(anteil)
    return "passt" if echt == erwartet else ("mehr" if echt > erwartet else "weniger")


@dataclass(frozen=True)
class Tagesbild:
    """Alles für Kachel und Startseite: Zeit, Ziel, Serie, Vorschlag, Schonung."""

    ziel_minuten: int
    minuten: int  # heute geübt, abgerundet
    mindest_minuten: int
    mindesttag: bool
    erreicht: bool
    serie: tagesziel.Serie
    vorschlag_minuten: int | None
    pause: bool  # heute wird kein Ziel verlangt


def tagesbild(kind, heute):
    ziel = Lernziel.objects.filter(kind=kind).first()
    tag = Lerntag.objects.filter(kind=kind, datum=heute).first()
    return Tagesbild(
        ziel_minuten=ziel.ziel_minuten if ziel else wert("lernen.tagesziel_minuten"),
        minuten=(tag.sekunden // 60) if tag else 0,
        mindest_minuten=wert("lernen.mindesttag_minuten"),
        mindesttag=bool(tag and tag.mindesttag),
        erreicht=bool(tag and tag.erreicht),
        serie=tagesziel.serie(kind, heute),
        vorschlag_minuten=ziel.vorschlag_minuten if ziel else None,
        pause=wert("lernen.ferien_schalter") or tagesziel.ist_pausentag(kind, heute),
    )


def tage_geuebt(kind):
    """Metrik "Tage geübt": Tage ab dem Mindesttag (Beteiligung, nicht Menge)."""
    return Lerntag.objects.filter(kind=kind, mindesttag=True).count()


def lern_beteiligung(kind):
    """Metrik "Lern-Beteiligung": Tage mit erreichtem EIGENEM Tagesziel (relativ, nicht Menge)."""
    return Lerntag.objects.filter(kind=kind, erreicht=True).count()


def tage_der_woche(kind, heute):
    """Geübte Tage (ab Mindesttag) von Montag bis heute."""
    return Lerntag.objects.filter(
        kind=kind, mindesttag=True, datum__gte=tagesziel.montag(heute), datum__lte=heute
    ).count()


def pausen(kind=None):
    """Pausen für die Eltern-Seite: die eines Kindes und die für alle."""
    qs = Lernpause.objects.all()
    return qs.filter(Q(kind=kind) | Q(kind__isnull=True)) if kind is not None else qs
