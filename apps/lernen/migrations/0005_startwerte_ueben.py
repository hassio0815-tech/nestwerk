"""Startwerte von lernen, Etappe 2 (SPEC 21.12): Schwellen für Üben, Tagesziel und Serie."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE_UEBEN


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_UEBEN)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("lernen", "0004_ueben"),
    ]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
