from django.db import migrations, models

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE_EINRICHTUNG


def anlegen(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_EINRICHTUNG)


class Migration(migrations.Migration):
    dependencies = [
        ("lernen", "0014_startwerte_woche"),
        ("kern", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lernmappe",
            name="schulform",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.RunPython(anlegen, migrations.RunPython.noop),
    ]
