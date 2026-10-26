"""Startwerte der Oberflächen-Einstellungen."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.oberflaeche.einstellungen import STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [("kern", "0004_audit_objekt_id_laenge")]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
