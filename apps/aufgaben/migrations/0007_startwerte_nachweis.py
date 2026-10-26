"""Startwerte der Nachweis-Fotos (Review AP19, B-09): Größe und Anzahl sind Familienwerte."""

from django.db import migrations

from apps.aufgaben.einstellungen import STARTWERTE_NACHWEIS
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_NACHWEIS)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("aufgaben", "0006_startwerte_ablauf"),
    ]

    # Rückwärts bleiben die Werte stehen (Einstellungen gehen nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
