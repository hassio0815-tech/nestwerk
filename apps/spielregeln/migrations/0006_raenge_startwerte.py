"""Startwerte Ränge (Entscheidung 14) und globale Kalibrierung 1,00 (K3)."""

from django.db import migrations

from apps.spielregeln.raenge_start import anlegen


def startwerte(apps, schema_editor):
    anlegen(apps.get_model("spielregeln", "Rang"), apps.get_model("spielregeln", "Kalibrierung"))


class Migration(migrations.Migration):
    dependencies = [("spielregeln", "0005_raenge")]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
