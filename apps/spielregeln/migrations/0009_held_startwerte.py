"""Startwerte Held der Woche (AP30). Überschreibt nie bestehende Werte."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.spielregeln.einstellungen import HELD_STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), HELD_STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("spielregeln", "0008_abzeichen_startwerte"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
