from django.db import migrations

from apps.avatar.einstellungen import RUHMESHALLE_STARTWERTE
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    """P3-A: avatar.ruhmeshalle_ausbaustufe (überschreibt nie bestehende Werte)."""
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), RUHMESHALLE_STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("avatar", "0005_ruhmeshalle"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
