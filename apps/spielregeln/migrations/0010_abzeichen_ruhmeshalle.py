"""Abzeichen der Ruhmeshalle (P3-A): Erster Held, Heldentrio, Sammler, Legende."""

from django.db import migrations

from apps.spielregeln.abzeichen_start import anlegen


def startwerte(apps, schema_editor):
    anlegen(apps.get_model("spielregeln", "AbzeichenDefinition"))


class Migration(migrations.Migration):
    dependencies = [("spielregeln", "0009_held_startwerte")]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
