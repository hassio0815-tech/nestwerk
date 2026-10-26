import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("benachrichtigung", "0002_kanaele_startwerte"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushabo",
            name="erstellt_am",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="pushabo",
            name="zuletzt_ok",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pushabo",
            name="fehlerzaehler",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
