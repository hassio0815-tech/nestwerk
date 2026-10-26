"""Startwert Aufbewahrung (B-15, Review AP31)."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben

STARTWERTE = {"ereignisse.aufbewahrung_tage": 180}


def vorwaerts(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("ereignisse", "0003_ereignis_kind_akteur"),
        ("kern", "0001_initial"),
    ]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
