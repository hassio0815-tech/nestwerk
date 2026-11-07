"""Schreibende Operationen von aufgaben. Jede Änderung geht ins Audit-Log.

- Instanzen (AP11): ``instanzen_erzeugen``, ``verfall_pruefen``, ``instanz_verschieben`` (AP14),
  ``reservierung_frist``, ``reservierungen_pruefen``, ``reservierungsablauf_hook_registrieren``.
- Kinderablauf (AP12, ``ablauf``): Interesse, Zuteilung, Meldung, Bestätigung, Sonderpunkte,
  Korrektur; Zustandsautomat in ``zustand``. Hooks für AP13 (Nachweis), Phase 2 (Aktivität)
  und AP21 (Serienbonus): ``erledigung_hook_registrieren``, ``storno_hook_registrieren``,
  ``nachweis_speicher_registrieren``, ``nachweis_loescher_registrieren``.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.kern import audit
from apps.konten import selectors as konten_selectors

from . import doppelt
from .ablauf import (
    Erledigung,
    LimitErreicht,
    NichtErlaubt,
    ablehnen,
    alle_passen,
    bestaetigen,
    erledigt_melden,
    erledigung_hook_registrieren,
    interesse_zeigen,
    kind_darf_sehen,
    korrigieren,
    limit_stand,
    nachbessern_pruefen,
    nachweis_loescher_registrieren,
    nachweis_speicher_registrieren,
    passt,
    reservierung_loesen,
    rueckfrage_beantworten,
    rueckfrage_stellen,
    sonderpunkte_deckel,
    sonderpunkte_vergeben,
    storno_hook_registrieren,
    zu_pruefen,
    zurueckgeben,
    zuteilen,
)
from .instanzen import (
    instanz_verschieben,
    instanzen_erzeugen,
    offene_entfernen,
    reservierung_frist,
    reservierungen_pruefen,
    reservierungsablauf_hook_registrieren,
    verfall_pruefen,
)
from .models import Aufgabe, AufgabenInstanz, Kategorie, Status
from .uebernahme import uebernehmen as aus_woche_uebernehmen
from .zustand import AblaufFehler, UngueltigerUebergang

__all__ = [
    "nachbessern_pruefen",
    "alle_passen",
    "passt",
    "zu_pruefen",
    "AblaufFehler",
    "Erledigung",
    "LimitErreicht",
    "NichtErlaubt",
    "UngueltigerUebergang",
    "ablehnen",
    "bestaetigen",
    "erledigt_melden",
    "erledigung_hook_registrieren",
    "interesse_zeigen",
    "kind_darf_sehen",
    "korrigieren",
    "limit_stand",
    "nachweis_loescher_registrieren",
    "nachweis_speicher_registrieren",
    "reservierung_loesen",
    "rueckfrage_beantworten",
    "rueckfrage_stellen",
    "sonderpunkte_deckel",
    "sonderpunkte_vergeben",
    "storno_hook_registrieren",
    "zurueckgeben",
    "zuteilen",
    "aus_woche_uebernehmen",
    "aufgabe_speichern",
    "aufgabe_status_setzen",
    "instanz_verschieben",
    "instanzen_erzeugen",
    "kategorie_speichern",
    "reservierung_frist",
    "reservierungen_pruefen",
    "reservierungsablauf_hook_registrieren",
    "verfall_pruefen",
]


def _instanzen_neu_planen(aufgabe, *, verschobene_behalten=False):
    """Freie Instanzen verwerfen und (falls aktiv) sofort nach aktuellem Plan neu anlegen.

    Plan-Änderung: manuell verschobene bleiben (``offene_entfernen``). Pause/Ende: alle freien
    gehen weg (die Eltern haben die Aufgabe bewusst gestoppt); Begonnenes bleibt immer.
    """
    offene_entfernen(aufgabe, verschobene_behalten=verschobene_behalten)
    instanzen_erzeugen(aufgaben=Aufgabe.objects.filter(pk=aufgabe.pk))


def _diff(form):
    """Geänderte Felder (nur Namen und neue Werte als Text) für das Audit-Log."""
    if form is None:
        return {}
    return {
        name: str(form.cleaned_data.get(name, ""))[:200]
        for name in form.changed_data
        if name in form.cleaned_data
    }


@transaction.atomic
def aufgabe_speichern(form, *, von) -> Aufgabe:
    """Legt eine Aufgabe an oder ändert sie (``form`` ist ein gültiges ``AufgabeForm``).

    Neu mit ``je_kind``: je aktivem Kind eine eigene, ihm zugewiesene Aufgabe (Rückgabe: die
    erste)."""
    neu = form.instance.pk is None
    aufgabe = form.save(commit=False)
    if neu:
        _doppel_pruefen(form)
        aufgabe.erstellt_von = von
        if form.cleaned_data.get("je_kind"):
            kinder = list(konten_selectors.aktive_kinder())
            if not kinder:
                raise ValidationError(_JE_KIND_OHNE_KINDER)
            return _je_kind_anlegen(aufgabe, kinder, von=von, details=_diff(form))
    aufgabe.save()
    _instanzen_neu_planen(aufgabe, verschobene_behalten=not neu)
    audit.protokollieren(
        "aufgabe.angelegt" if neu else "aufgabe.geaendert",
        akteur=von,
        objekt=aufgabe,
        kind=aufgabe.zugewiesen_an,
        details={"titel": aufgabe.titel, "punkte": aufgabe.punkte, "geaendert": _diff(form)},
    )
    return aufgabe


_JE_KIND_OHNE_KINDER = gettext_lazy(
    "Es gibt keine aktiven Kinder, für die die Aufgabe angelegt werden könnte."
)


def _doppel_pruefen(form) -> None:
    """Doppel-Schutz noch einmal in der Transaktion (zwei gleichzeitig gesendete Formulare).

    Das Formular prüft vorab; hier gilt dasselbe, falls inzwischen eine gleiche Aufgabe
    entstanden ist. ``trotzdem_anlegen`` im Formular schaltet beides ab."""
    daten = form.cleaned_data
    if daten.get("trotzdem_anlegen"):
        return
    vorhanden = doppelt.finden(
        daten.get("titel"),
        daten.get("wiederholungsart"),
        daten.get("zugewiesen_an"),
        je_kind=bool(daten.get("je_kind")),
    )
    if vorhanden is not None:
        form.doppelt = vorhanden
        raise ValidationError(doppelt.meldung(vorhanden))


def _je_kind_anlegen(muster, kinder, *, von, details=None, uebernehmen=None) -> Aufgabe:
    """Speichert ``muster`` (ungespeichert) einmal je Kind als eigene Aufgabe.

    ``uebernehmen(kopie, kind)``: läuft nach dem Speichern, vor dem Planen (z. B. Instanzen des
    Kindes an die Kopie hängen, damit ihre Plan-Tage das Planen nicht doppeln)."""
    erste = None
    for kind in kinder:
        muster.pk = None
        muster._state.adding = True
        muster.zugewiesen_an = kind
        muster.save()
        if uebernehmen is not None:
            uebernehmen(muster, kind)
        _instanzen_neu_planen(muster)
        audit.protokollieren(
            "aufgabe.angelegt",
            akteur=von,
            objekt=muster,
            kind=kind,
            details={
                "titel": muster.titel,
                "punkte": muster.punkte,
                "je_kind": True,
                "geaendert": details or {},
            },
        )
        erste = erste or Aufgabe.objects.get(pk=muster.pk)
    return erste


@transaction.atomic
def je_kind_aufteilen(aufgabe, *, von=None) -> list[Aufgabe]:
    """Bestehende Aufgabe "für alle Kinder" in je eine eigene Aufgabe pro Kind aufteilen.

    Nur aktive Aufgaben. Das Original geht an das erste aktive Kind; für die übrigen entstehen
    Kopien. Instanzen, die schon einem Kind gehören (reserviert, gemeldet, bestätigt ...), samt
    Interessen und Meldungen folgen diesem Kind in dessen Kopie. Freie (offene) Instanzen des
    Originals werden neu geplant; sie sind jetzt nur noch für das erste Kind.
    """
    if aufgabe.status != Status.AKTIV:
        raise ValidationError(_("Nur aktive Aufgaben können aufgeteilt werden."))
    if aufgabe.zugewiesen_an_id:
        raise ValidationError(_("Die Aufgabe ist schon einem Kind zugewiesen."))
    kinder = list(konten_selectors.aktive_kinder())
    if not kinder:
        raise ValidationError(_("Es gibt keine aktiven Kinder."))
    erstes, *rest = kinder
    original_pk = aufgabe.pk
    aufgabe.zugewiesen_an = erstes
    aufgabe.save(update_fields=["zugewiesen_an", "geaendert_am"])
    audit.protokollieren(
        "aufgabe.geaendert",
        akteur=von,
        objekt=aufgabe,
        kind=erstes,
        details={"titel": aufgabe.titel, "je_kind_aufgeteilt": True},
    )
    ergebnis = [aufgabe]
    if rest:
        muster = Aufgabe.objects.get(pk=aufgabe.pk)
        muster.erstellt_von = von or aufgabe.erstellt_von

        def instanzen_mitnehmen(kopie, kind):
            AufgabenInstanz.objects.filter(aufgabe_id=original_pk, kind=kind).update(aufgabe=kopie)

        for kind in rest:
            ergebnis.append(
                _je_kind_anlegen(muster, [kind], von=von, uebernehmen=instanzen_mitnehmen)
            )
    _instanzen_neu_planen(aufgabe, verschobene_behalten=True)
    return ergebnis


@transaction.atomic
def aufgabe_status_setzen(aufgabe, status, *, von) -> Aufgabe:
    """pausieren / fortsetzen / beenden. 'Beendet' ist endgültig; Punkte bleiben unberührt."""
    if status not in Status.values:
        raise ValidationError(_("Unbekannter Status."))
    if aufgabe.status == Status.BEENDET and status != Status.BEENDET:
        raise ValidationError(_("Eine beendete Aufgabe kann nicht fortgesetzt werden."))
    alt = aufgabe.status
    if alt == status:
        return aufgabe
    aufgabe.status = status
    aufgabe.save(update_fields=["status", "geaendert_am"])
    _instanzen_neu_planen(aufgabe)  # Pause/Ende: offene weg; Fortsetzen: sofort neu
    audit.protokollieren(
        "aufgabe.status_geaendert",
        akteur=von,
        objekt=aufgabe,
        kind=aufgabe.zugewiesen_an,
        details={"titel": aufgabe.titel, "von": alt, "nach": status},
    )
    return aufgabe


@transaction.atomic
def kategorie_speichern(form, *, von) -> Kategorie:
    neu = form.instance.pk is None
    kategorie = form.save()
    audit.protokollieren(
        "kategorie.angelegt" if neu else "kategorie.geaendert",
        akteur=von,
        objekt=kategorie,
        details={"name": kategorie.name, "geaendert": _diff(form)},
    )
    return kategorie
