"""Startwerte von lernen (SPEC 21.12): Einstellungen. Fächer und Fragen: 0003."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("lernen", "0001_initial"),
    ]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
