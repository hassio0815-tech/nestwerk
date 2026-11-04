"""Verbindet die Mathe-Themen mit den Generatoren (SPEC 21.13); additiv und idempotent."""

from django.db import migrations

from apps.lernen.startdaten import mathe_themen_anlegen


def anlegen(apps, schema_editor):
    mathe_themen_anlegen(apps.get_model("lernen", "Fach"), apps.get_model("lernen", "Thema"))


class Migration(migrations.Migration):
    dependencies = [("lernen", "0017_startwerte_mathe")]

    # Rückwärts bleiben die Themen stehen (Eltern können Fragen ergänzt haben)
    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
