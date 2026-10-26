"""AP32: Faktor für Mindest-Aktivwochen (P-07) und Startwerte der Prognose-Einstellungen."""

from django.db import migrations, models

from apps.kern.einstellungen import startwerte_schreiben
from apps.spielregeln.einstellungen import PROGNOSE_STARTWERTE


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), PROGNOSE_STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("spielregeln", "0010_abzeichen_ruhmeshalle"),
    ]

    operations = [
        migrations.AddField(
            model_name="kalibrierung",
            name="faktor_wochen",
            field=models.DecimalField(decimal_places=2, default=1, max_digits=4),
        ),
        migrations.RunPython(startwerte, migrations.RunPython.noop),
    ]
