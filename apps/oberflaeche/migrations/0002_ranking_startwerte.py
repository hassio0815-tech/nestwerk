"""Startwert Ranking-Modus (AP30)."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.oberflaeche.einstellungen import RANKING_STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), RANKING_STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0004_audit_objekt_id_laenge"),
        ("oberflaeche", "0001_startwerte"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
