"""Startdaten von lernen: Fächer Englisch und Mathe, Themen, Englisch-Vokabeln (generisch)."""

from django.db import migrations

from apps.lernen.startdaten import anlegen


def startfaecher(apps, schema_editor):
    anlegen(
        apps.get_model("lernen", "Fach"),
        apps.get_model("lernen", "Thema"),
        apps.get_model("lernen", "Frage"),
    )


class Migration(migrations.Migration):
    dependencies = [("lernen", "0002_startwerte")]

    # Rückwärts bleiben die Daten stehen (Eltern können Fragen inzwischen ergänzt haben)
    operations = [migrations.RunPython(startfaecher, migrations.RunPython.noop)]
