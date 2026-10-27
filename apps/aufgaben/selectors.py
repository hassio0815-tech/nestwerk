"""Lesende Abfragen von aufgaben (öffentliche Schnittstelle für Dashboards, AP12/AP14/AP17)."""

from datetime import date, timedelta

from django.db.models import Count, Prefetch, Q

from apps.kern import einstellungen, zeit
from apps.punkte import selectors as punkte_selectors

from . import schluessel
from .models import (
    INTERESSE_LAUFEND,
    LAUFENDE_STATUS,
    MELDUNG_LAUFEND,
    AufgabenInstanz,
    InstanzStatus,
    Interesse,
    InteresseStatus,
    Meldung,
    MeldungStatus,
    Status,
    Vorlage,
)


def laufende_instanzen():
    """Nicht abgeschlossene Instanzen aktiver Aufgaben (offen bis Rückfrage)."""
    return AufgabenInstanz.objects.filter(
        status__in=LAUFENDE_STATUS, aufgabe__status=Status.AKTIV
    ).select_related("aufgabe")


def instanzen_im_zeitraum(von: date, bis: date):
    """Instanzen mit wirksamem Datum in ``[von, bis]`` (Wochenplan, AP14)."""
    return AufgabenInstanz.objects.filter(faellig_am__range=(von, bis)).select_related("aufgabe")


def nicht_uebernommene(seit=None):
    """Verfallene Instanzen für die Eltern-Ansicht ("nicht übernommen")."""
    qs = AufgabenInstanz.objects.filter(status=InstanzStatus.NICHT_UEBERNOMMEN)
    if seit is not None:
        qs = qs.filter(abgeschlossen_am__gte=seit)
    return qs.order_by("-abgeschlossen_am")


# --- Kinderablauf (AP12) ----------------------------------------------------------------------

ABGESCHLOSSEN_ZEIGEN_TAGE = 7


def _sichtbar_fuer_kind(kind):
    return Q(aufgabe__zugewiesen_an__isnull=True) | Q(aufgabe__zugewiesen_an=kind)


def kind_offene(kind, *, jetzt=None):
    """Freie Aufgaben für ``kind`` (große Kacheln): offen, für alle oder ihm zugewiesen, Fenster
    nicht vorbei, Termin höchstens ``aufgaben.kind_vorschau_tage`` voraus.

    Mit ``aufgaben.mitbewerben_erlaubt`` auch von anderen Kindern reservierte (noch nicht
    gemeldete) Instanzen und Konflikte (``vergeben_an_andere = True``, ohne Namen). Jede Instanz
    trägt ``limit_erreicht`` (K10).
    """
    from . import ablauf

    jetzt = jetzt or zeit.jetzt()
    bis = zeit.heute(jetzt) + timedelta(days=einstellungen.wert("aufgaben.kind_vorschau_tage"))
    status = [InstanzStatus.OFFEN]
    mitbewerben = einstellungen.wert("aufgaben.mitbewerben_erlaubt")
    if mitbewerben:
        status += [InstanzStatus.RESERVIERT, InstanzStatus.KONFLIKT]
    qs = (
        AufgabenInstanz.objects.filter(status__in=status, aufgabe__status=Status.AKTIV)
        .filter(_sichtbar_fuer_kind(kind))
        .filter(Q(fenster_ende__isnull=True) | Q(fenster_ende__gt=jetzt))
        .filter(Q(faellig_am__isnull=True) | Q(faellig_am__lte=bis))
        .exclude(
            pk__in=Interesse.objects.filter(kind=kind, status__in=INTERESSE_LAUFEND).values(
                "instanz"
            )
        )
        .select_related("aufgabe", "aufgabe__kategorie")
        .order_by("faellig_am", "fenster_ende", "sortierung", "id")
    )
    ergebnis = []
    limits = {}
    for instanz in qs:
        instanz.vergeben_an_andere = instanz.status != InstanzStatus.OFFEN
        if instanz.aufgabe_id not in limits:
            stand = ablauf.limit_stand(instanz.aufgabe, kind, jetzt=jetzt)
            limits[instanz.aufgabe_id] = stand is not None and stand[0] >= stand[1]
        instanz.limit_erreicht = limits[instanz.aufgabe_id]
        ergebnis.append(instanz)
    return ergebnis


def kind_eigene(kind, *, jetzt=None):
    """Eigene Aufgaben: laufend (reserviert, Konflikt mit eigenem Interesse, gemeldet,
    Rückfrage) und kürzlich abgeschlossene (bestätigt inkl. Bonus, abgelehnt, korrigiert) sowie
    "vergeben" (Konflikt an ein anderes Kind). Jede Instanz trägt ``anzeige_status``, bei
    Rückfrage ``rueckfrage_text`` und ``serienbonus`` (Buchung oder ``None``, AP21).
    """
    jetzt = jetzt or zeit.jetzt()
    seit = jetzt - timedelta(days=ABGESCHLOSSEN_ZEIGEN_TAGE)
    laufend = AufgabenInstanz.objects.filter(
        Q(
            kind=kind,
            status__in=(
                InstanzStatus.RESERVIERT,
                InstanzStatus.NACHBESSERN,
                InstanzStatus.GEMELDET,
                InstanzStatus.RUECKFRAGE,
            ),
        )
        | Q(
            status=InstanzStatus.KONFLIKT,
            interessen__kind=kind,
            interessen__status=InteresseStatus.AKTIV,
        )
    )
    fertig = AufgabenInstanz.objects.filter(
        kind=kind,
        status__in=(InstanzStatus.BESTAETIGT, InstanzStatus.ABGELEHNT, InstanzStatus.STORNIERT),
        abgeschlossen_am__gte=seit,
    )
    vergeben = AufgabenInstanz.objects.filter(
        interessen__kind=kind,
        interessen__status=InteresseStatus.VERDRAENGT,
        interessen__geaendert_am__gte=seit,
    ).exclude(kind=kind)
    instanzen = list(
        (laufend | fertig | vergeben)
        .distinct()
        .select_related("aufgabe", "aufgabe__kategorie")
        .order_by("-id")
    )
    fragen = dict(
        Meldung.objects.filter(instanz__in=instanzen, status=MeldungStatus.RUECKFRAGE).values_list(
            "instanz_id", "rueckfrage_text"
        )
    )
    boni = punkte_selectors.buchungen_zu_schluesseln(
        schluessel.buchung(i.pk, "serienbonus", i.nachbessern_anzahl)
        for i in instanzen
        if i.status == InstanzStatus.BESTAETIGT
    )
    for instanz in instanzen:
        instanz.serienbonus = boni.get(
            schluessel.buchung(instanz.pk, "serienbonus", instanz.nachbessern_anzahl)
        )
        if instanz.kind_id != kind.pk and instanz.status != InstanzStatus.KONFLIKT:
            instanz.anzeige_status = "vergeben"
        else:
            instanz.anzeige_status = instanz.status
        instanz.rueckfrage_text = fragen.get(instanz.pk, "")
    reihenfolge = {
        "rueckfrage": 0,
        "nachbessern": 0,
        "reserviert": 1,
        "konflikt": 2,
        "gemeldet": 3,
        "bestaetigt": 4,
        "abgelehnt": 5,
        "storniert": 6,
        "vergeben": 7,
    }
    return sorted(instanzen, key=lambda i: reihenfolge.get(i.anzeige_status, 9))


def eltern_entscheidungen(*, jetzt=None) -> dict:
    """Offene Eltern-Entscheidungen und Korrekturmöglichkeiten (Eltern-Dashboard)."""
    jetzt = jetzt or zeit.jetzt()
    basis = AufgabenInstanz.objects.select_related("aufgabe", "kind", "bestaetigt_von")
    konflikte = list(
        basis.filter(status=InstanzStatus.KONFLIKT).prefetch_related(
            Prefetch(
                "interessen",
                queryset=Interesse.objects.filter(status=InteresseStatus.AKTIV).select_related(
                    "kind"
                ),
                to_attr="aktive_interessen",
            )
        )
    )
    meldungen = list(
        basis.filter(status__in=(InstanzStatus.GEMELDET, InstanzStatus.RUECKFRAGE))
        .prefetch_related(
            Prefetch(
                "meldungen",
                queryset=Meldung.objects.filter(status__in=MELDUNG_LAUFEND),
                to_attr="offene_meldungen",
            )
        )
        .order_by("gemeldet_am", "id")
    )
    for instanz in meldungen:
        instanz.meldung = instanz.offene_meldungen[0] if instanz.offene_meldungen else None
    seit = jetzt - timedelta(days=ABGESCHLOSSEN_ZEIGEN_TAGE)
    return {
        "konflikte": konflikte,
        "meldungen": meldungen,
        "reserviert": list(
            basis.filter(status=InstanzStatus.RESERVIERT).order_by("reserviert_bis")
        ),
        "bestaetigt": list(
            basis.filter(status=InstanzStatus.BESTAETIGT, abgeschlossen_am__gte=seit).order_by(
                "-abgeschlossen_am"
            )
        ),
    }


def offene_entscheidungen_anzahl() -> int:
    """Badge-Zahl: Konflikte + Meldungen (gemeldet; Rückfragen warten aufs Kind)."""
    return AufgabenInstanz.objects.filter(
        status__in=(InstanzStatus.KONFLIKT, InstanzStatus.GEMELDET)
    ).count()


def vorlagen():
    """Aufgabenbibliothek (Vorlagen) in Anzeige-Reihenfolge."""
    return Vorlage.objects.select_related("kategorie")


def zahlen_je_kind(kinder, von, bis) -> dict:
    """Je Kind (Benutzer-PK): laufende Aufgaben (reserviert/gemeldet/Rückfrage) und im
    Intervall ``[von, bis)`` bestätigte. Eine Abfrage, unabhängig von der Kinderzahl."""
    zeilen = (
        AufgabenInstanz.objects.filter(kind__in=kinder)
        .values("kind")
        .annotate(
            laufend=Count(
                "id",
                filter=Q(
                    status__in=(
                        InstanzStatus.RESERVIERT,
                        InstanzStatus.GEMELDET,
                        InstanzStatus.RUECKFRAGE,
                    )
                ),
            ),
            heute=Count(
                "id",
                filter=Q(
                    status=InstanzStatus.BESTAETIGT,
                    abgeschlossen_am__gte=von,
                    abgeschlossen_am__lt=bis,
                ),
            ),
        )
    )
    return {z["kind"]: z for z in zeilen}
