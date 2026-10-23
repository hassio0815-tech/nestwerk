"""Startwerte von spielregeln (AP20): Wochenpuffer (K1), Neutralität ab Pausentagen (K5)."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.spielregeln.einstellungen import STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("spielregeln", "0001_initial"),
    ]

    # Rückwärts bleiben die Werte stehen (Einstellungen gehen nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
