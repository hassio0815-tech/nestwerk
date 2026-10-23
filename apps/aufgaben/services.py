"""Schreibende Operationen der Aufgaben-Stammdaten. Jede Änderung geht ins Audit-Log."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.kern import audit

from .models import Aufgabe, Kategorie, Status, Vorlage


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
        raise ValidationError("Unbekannter Status.")
    if aufgabe.status == Status.BEENDET and status != Status.BEENDET:
        raise ValidationError("Eine beendete Aufgabe kann nicht fortgesetzt werden.")
    alt = aufgabe.status
    if alt == status:
        return aufgabe
    aufgabe.status = status
    aufgabe.save(update_fields=["status", "geaendert_am"])
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
