"""Startwerte der Instanz-, Verfall- und Reservierungs-Einstellungen (DATA_MODEL 15.2)."""

from django.db import migrations

from apps.aufgaben.einstellungen import STARTWERTE
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("aufgaben", "0003_aufgabeninstanz"),
    ]

    # Rückwärts bleiben die Werte stehen (Einstellungen gehen nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
