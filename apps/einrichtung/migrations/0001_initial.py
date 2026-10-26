from django.db import migrations

from apps.einrichtung.einstellungen import STARTWERTE
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [("kern", "0001_initial")]
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
