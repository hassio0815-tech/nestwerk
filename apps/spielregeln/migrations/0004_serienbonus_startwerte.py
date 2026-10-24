"""Startwerte Serienbonus (AP21, Entscheidung 4, SPEC 18.2). Überschreibt nie bestehende Werte."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.spielregeln.einstellungen import STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("spielregeln", "0003_aktivitaeten_nachtragen"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
