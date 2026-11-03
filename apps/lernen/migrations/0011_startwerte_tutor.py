from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE_TUTOR


def anlegen(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_TUTOR)


class Migration(migrations.Migration):
    dependencies = [
        ("lernen", "0010_tutor"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
