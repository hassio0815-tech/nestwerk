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

from apps.kern import audit

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
from .models import Aufgabe, Kategorie, Status, Vorlage
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
    "aufgabe_speichern",
    "aufgabe_status_setzen",
    "instanz_verschieben",
    "instanzen_erzeugen",
    "kategorie_speichern",
    "reservierung_frist",
    "reservierungen_pruefen",
    "reservierungsablauf_hook_registrieren",
    "verfall_pruefen",
    "vorlage_loeschen",
    "vorlage_speichern",
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
    """Legt eine Aufgabe an oder ändert sie (``form`` ist ein gültiges ``AufgabeForm``)."""
    neu = form.instance.pk is None
    aufgabe = form.save(commit=False)
    if neu:
        aufgabe.erstellt_von = von
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
def vorlage_speichern(form, *, von) -> Vorlage:
    neu = form.instance.pk is None
    vorlage = form.save()
    audit.protokollieren(
        "vorlage.angelegt" if neu else "vorlage.geaendert",
        akteur=von,
        objekt=vorlage,
        details={"titel": vorlage.titel, "punkte": vorlage.punkte, "geaendert": _diff(form)},
    )
    return vorlage


@transaction.atomic
def vorlage_loeschen(vorlage, *, von) -> None:
    """Bereits angelegte Aufgaben bleiben erhalten (Verweis wird leer)."""
    details = {"titel": vorlage.titel, "punkte": vorlage.punkte}
    objekt_id = vorlage.pk
    vorlage.delete()
    audit.protokollieren(
        "vorlage.geloescht",
        akteur=von,
        objekt_typ="aufgaben.vorlage",
        objekt_id=str(objekt_id),
        details=details,
    )


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
