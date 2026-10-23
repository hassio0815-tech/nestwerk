"""Startwerte des Kinderablaufs (AP12): Sonderpunkte-Deckel, Konflikt, Vorschau."""

from django.db import migrations

from apps.aufgaben.einstellungen import STARTWERTE_ABLAUF
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_ABLAUF)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("aufgaben", "0005_kinderablauf"),
    ]

    # Rückwärts bleiben die Werte stehen (Einstellungen gehen nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
