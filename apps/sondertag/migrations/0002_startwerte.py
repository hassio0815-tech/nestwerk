"""Startwerte von sondertag (AP27): Einstellungen und Sondertag-Meilensteine (Entscheidung 1)."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.sondertag.einstellungen import STARTWERTE
from apps.sondertag.meilensteine_start import anlegen


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)
    anlegen(apps.get_model("spielregeln", "MeilensteinRegel"))


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("spielregeln", "0008_abzeichen_startwerte"),
        ("sondertag", "0001_initial"),
    ]

    # Rückwärts bleiben die Daten stehen (Konfiguration geht nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
