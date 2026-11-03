"""Startwerte von lernen, Etappe 3 (SPEC 21.6/21.12): Schwellen der KI-Warteschlange."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE_KI


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_KI)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("lernen", "0006_ki"),
    ]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
