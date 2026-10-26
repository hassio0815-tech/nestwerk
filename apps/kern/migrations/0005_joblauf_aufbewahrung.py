"""Startwert Aufbewahrung der Job-Läufe (B-15, Review AP31)."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben

STARTWERTE = {"allgemein.joblauf_aufbewahrung_tage": 90}


def vorwaerts(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [("kern", "0004_audit_objekt_id_laenge")]

    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
