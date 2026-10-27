"""Schreibende Schnittstelle von ereignisse (ARCHITECTURE 5.1)."""

import json
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.kern import audit, einstellungen
from apps.kern.einstellungen import Typ
from apps.konten.models import Benutzer, Rolle

from . import registry
from .models import Ereignis, EreignisTyp, EreignisVerarbeitung, Status

DATEN_MAX_ZEICHEN = 4000


class KeineTransaktion(RuntimeError):
    """``veroeffentlichen`` außerhalb von ``transaction.atomic()`` aufgerufen."""


def veroeffentlichen(typ, *, kind=None, akteur=None, daten=None, schluessel=None):
    """Schreibt ein Ereignis in die Outbox, in der Transaktion des Aufrufers.

    - Muss innerhalb von ``transaction.atomic()`` laufen (Rollback = kein Ereignis).
    - ``schluessel`` (optional, eindeutig): gibt es ihn schon, wird kein zweites Ereignis
      erzeugt; zurück kommt das bestehende.
    - Synchrone Handler laufen sofort (gleiche Transaktion); asynchrone im Worker.
    - ``kind``: betroffenes Kind (Benutzer mit Rolle Kind), ``akteur``: Auslöser (None = System).
    - ``daten``: JSON-dict mit IDs und Anzeigetexten, nie Nachweis-Inhalte.
    """
    if not connection.in_atomic_block:
        raise KeineTransaktion("ereignisse.veroeffentlichen nur innerhalb transaction.atomic()")
    _benutzer_pruefen("kind", kind, rolle=Rolle.KIND)
    _benutzer_pruefen("akteur", akteur)
    definition = registry.typ(typ)
    daten = {} if daten is None else daten
    _daten_pruefen(daten)
    if schluessel is not None and not (isinstance(schluessel, str) and 0 < len(schluessel) <= 150):
        raise ValueError("schluessel: Text mit 1–150 Zeichen erwartet")

    _typ_sicherstellen(definition)
    if schluessel is not None:
        try:
            with transaction.atomic():
                ereignis = Ereignis.objects.create(
                    typ_id=typ, daten=daten, schluessel=schluessel, kind=kind, akteur=akteur
                )
        except IntegrityError:
            return Ereignis.objects.get(schluessel=schluessel)
    else:
        ereignis = Ereignis.objects.create(typ_id=typ, daten=daten, kind=kind, akteur=akteur)

    for h in registry.handler_fuer(typ, synchron=True):
        h.funktion(ereignis)
    return ereignis


def _benutzer_pruefen(name, benutzer, *, rolle=None):
    if benutzer is None:
        return
    if not isinstance(benutzer, Benutzer) or benutzer.pk is None:
        raise ValueError(f"{name}: gespeicherter Benutzer erwartet")
    if rolle is not None and benutzer.rolle != rolle:
        raise ValueError(f"{name}: Benutzer mit Rolle '{rolle}' erwartet")


def _daten_pruefen(daten):
    if not isinstance(daten, dict):
        raise ValueError("daten muss ein dict sein")
    try:
        text = json.dumps(daten)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"daten ist nicht JSON-serialisierbar: {exc}") from exc
    if len(text) > DATEN_MAX_ZEICHEN:
        raise ValueError(f"daten ist zu groß (max. {DATEN_MAX_ZEICHEN} Zeichen)")


def _typ_sicherstellen(definition):
    """Fehlt die DB-Zeile (Sync noch nicht gelaufen), wird sie aus der Definition angelegt."""
    if not EreignisTyp.objects.filter(pk=definition.slug).exists():
        _typ_anlegen(definition)


def _typ_anlegen(definition):
    _typ, erstellt = EreignisTyp.objects.get_or_create(
        slug=definition.slug,
        defaults={
            "modul": definition.modul,
            "bezeichnung": definition.bezeichnung,
            "zielgruppe": definition.zielgruppe,
            "standard_kanaele": list(definition.standard_kanaele),
            "deep_link_muster": definition.deep_link_muster,
            "push_ttl_sekunden": definition.push_ttl_sekunden,
            "aktiv": True,
        },
    )
    return erstellt


def typen_synchronisieren(**_signal_kwargs):
    """Code-Katalog -> Tabelle ``EreignisTyp`` (idempotent, läuft bei ``post_migrate``).

    Neue Typen werden angelegt; bestehende behalten ihre editierbaren Werte, nur ``modul``
    wird nachgeführt. Nicht mehr deklarierte Typen bleiben stehen (Historie, PROTECT).
    Gibt ``{"angelegt": n, "aktualisiert": m}`` zurück.
    """
    angelegt = aktualisiert = 0
    if EreignisTyp._meta.db_table not in connection.introspection.table_names():
        return {"angelegt": 0, "aktualisiert": 0}  # z. B. nach "migrate ereignisse zero"
    with transaction.atomic():
        for definition in registry.typen():
            if _typ_anlegen(definition):
                angelegt += 1
            else:
                aktualisiert += (
                    EreignisTyp.objects.filter(pk=definition.slug)
                    .exclude(modul=definition.modul)
                    .update(modul=definition.modul)
                )
    return {"angelegt": angelegt, "aktualisiert": aktualisiert}


def neu_einplanen(*, akteur=None, ids=None):
    """Setzt fehlerhafte/aufgegebene Verarbeitungen auf ``offen`` zurück (Systemstatus-Button).

    ``ids=None`` = alle aufgegebenen. Gibt die Anzahl zurück und protokolliert im Audit-Log.
    """
    with transaction.atomic():
        qs = EreignisVerarbeitung.objects.filter(status__in=[Status.FEHLER, Status.AUFGEGEBEN])
        qs = qs.filter(status=Status.AUFGEGEBEN) if ids is None else qs.filter(pk__in=ids)
        anzahl = qs.update(status=Status.OFFEN, versuche=0, naechster_versuch=timezone.now())
        if anzahl:
            audit.protokollieren(
                "ereignisse.neu_eingeplant", akteur=akteur, details={"anzahl": anzahl}
            )
    return anzahl


def aufraeumen(*, behalten=None, jetzt=None) -> int:
    """Aufbewahrung (B-15, Review AP31): löscht Ereignisse älter als
    ``ereignisse.aufbewahrung_tage``,
    die verteilt sind und deren Verarbeitungen alle ``ok`` sind (Verarbeitungen per CASCADE).
    Offene, fehlerhafte oder aufgegebene bleiben (Systemstatus). ``behalten``: Ereignis-IDs
    (Queryset/Liste), die noch referenziert werden (z. B. Benachrichtigungen, PROTECT).
    Fachliche Fakten hängen nie an Ereignissen (Ledger, Audit, Aktivitäten, Ansprüche)."""
    tage = einstellungen.wert("ereignisse.aufbewahrung_tage")
    grenze = (jetzt or timezone.now()) - timedelta(days=tage)
    offen = EreignisVerarbeitung.objects.exclude(status=Status.OK).values("ereignis_id")
    qs = Ereignis.objects.filter(zeit__lt=grenze, verteilt=True).exclude(pk__in=offen)
    if behalten is not None:
        qs = qs.exclude(pk__in=behalten)
    anzahl = 0
    for ids in _stapel(qs.values_list("pk", flat=True)):
        anzahl += Ereignis.objects.filter(pk__in=ids).delete()[1].get("ereignisse.Ereignis", 0)
    return anzahl


def _stapel(werte, groesse=500):
    stapel = []
    for wert in werte.iterator():
        stapel.append(wert)
        if len(stapel) >= groesse:
            yield stapel
            stapel = []
    if stapel:
        yield stapel


def einstellungen_definieren():
    """Einstellungen des Workers (Startwerte per Datenmigration 0002/0004)."""
    einstellungen.definieren(
        "ereignisse.aufbewahrung_tage",
        Typ.GANZZAHL,
        _("Aufbewahrung verarbeiteter Ereignisse"),
        beschreibung=_(
            "Erfolgreich verarbeitete Ereignisse (internes Protokoll) werden danach "
            "gelöscht. Punkte, Protokoll (Audit) und Spielstände bleiben immer."
        ),
        einheit=_("Tage"),
        minimum=30,
        maximum=3650,
    )
    einstellungen.definieren(
        "ereignisse.max_versuche",
        Typ.GANZZAHL,
        _("Max. Versuche je Ereignis-Handler"),
        beschreibung=_("Danach gilt die Verarbeitung als aufgegeben (Systemstatus)."),
        minimum=1,
        maximum=50,
    )
    einstellungen.definieren(
        "ereignisse.backoff_basis_sekunden",
        Typ.GANZZAHL,
        _("Wartezeit vor dem 1. Wiederholversuch"),
        einheit="s",
        minimum=1,
        maximum=3600,
    )
    einstellungen.definieren(
        "ereignisse.backoff_max_sekunden",
        Typ.GANZZAHL,
        _("Max. Wartezeit zwischen Versuchen"),
        einheit="s",
        minimum=1,
        maximum=86400,
    )
