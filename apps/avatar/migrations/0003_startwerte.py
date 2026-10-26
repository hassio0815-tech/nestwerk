"""Startwerte avatar (AP26, SPEC 11.4 Zeitbremse). Überschreibt nie bestehende Werte."""

from django.db import migrations

from apps.avatar.einstellungen import STARTWERTE
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("avatar", "0002_modbesitz"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
