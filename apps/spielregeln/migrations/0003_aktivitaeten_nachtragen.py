"""Bestand aus Phase 1: Aktivitäten aus den Ereignissen ``aufgabe.erledigt`` (Fakt, K1) und
``aufgabe.korrigiert`` (Storno) nachtragen. Idempotent (unique modul/referenz). Die
Wochenauswertungen entstehen beim ersten Lauf von ``wochen_sicherstellen``."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.db import migrations

from apps.spielregeln.kontinuitaet import wirksames_datum


def nachtragen(apps, schema_editor):
    Ereignis = apps.get_model("ereignisse", "Ereignis")
    Aktivitaet = apps.get_model("spielregeln", "Aktivitaet")
    Einstellung = apps.get_model("kern", "Einstellung")
    erledigt = Ereignis.objects.filter(typ_id="aufgabe.erledigt").order_by("id")
    if not erledigt.exists():
        return
    werte = dict(
        Einstellung.objects.filter(
            schluessel__in=["allgemein.zeitzone", "spielregeln.puffer_stunden"]
        ).values_list("schluessel", "wert")
    )
    tz = ZoneInfo(werte["allgemein.zeitzone"])
    puffer = werte["spielregeln.puffer_stunden"]
    for e in erledigt:
        daten = e.daten or {}
        if e.kind_id is None or daten.get("instanz_id") is None or not daten.get("bezugsdatum"):
            continue
        erfasst = daten.get("bestaetigt_am")
        erfasst_am = datetime.fromisoformat(erfasst) if erfasst else e.zeit
        Aktivitaet.objects.get_or_create(
            modul="aufgaben",
            referenz=str(daten["instanz_id"]),
            defaults={
                "kind_id": e.kind_id,
                "datum": wirksames_datum(
                    date.fromisoformat(daten["bezugsdatum"]), erfasst_am, puffer, tz
                ),
                "erstellt_am": erfasst_am,
            },
        )
    for e in Ereignis.objects.filter(typ_id="aufgabe.korrigiert"):
        instanz = (e.daten or {}).get("instanz_id")
        if instanz is not None:
            Aktivitaet.objects.filter(modul="aufgaben", referenz=str(instanz)).update(
                storniert=True
            )


class Migration(migrations.Migration):
    dependencies = [
        ("ereignisse", "0003_ereignis_kind_akteur"),
        ("kern", "0001_initial"),
        ("spielregeln", "0002_startwerte"),
    ]

    operations = [migrations.RunPython(nachtragen, migrations.RunPython.noop)]
