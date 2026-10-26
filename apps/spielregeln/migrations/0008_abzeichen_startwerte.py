"""Startwerte Abzeichen (Entscheidung 12)."""

from django.db import migrations

from apps.spielregeln.abzeichen_start import anlegen


def startwerte(apps, schema_editor):
    anlegen(apps.get_model("spielregeln", "AbzeichenDefinition"))


class Migration(migrations.Migration):
    dependencies = [("spielregeln", "0007_abzeichen_meilensteine")]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
