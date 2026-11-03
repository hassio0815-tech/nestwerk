from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE_PRUEFUNG


def anlegen(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_PRUEFUNG)


class Migration(migrations.Migration):
    dependencies = [
        ("lernen", "0012_pruefung"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
