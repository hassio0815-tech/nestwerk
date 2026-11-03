"""Startwert: Merker, dass die Start-Schnell-Knöpfe noch nicht angelegt wurden."""

from django.db import migrations

from apps.aufgaben.einstellungen import STARTWERTE_SCHNELLKNOEPFE
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_SCHNELLKNOEPFE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("aufgaben", "0011_startwerte_schnellknoepfe"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
