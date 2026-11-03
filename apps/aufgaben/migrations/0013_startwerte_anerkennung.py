"""Startwerte: Grenzen der Anerkennung (Eltern-Lob ohne Aufgabe)."""

from django.db import migrations

from apps.aufgaben.einstellungen import STARTWERTE_ANERKENNUNG
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_ANERKENNUNG)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("aufgaben", "0012_startwert_schnellknoepfe_merker"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
