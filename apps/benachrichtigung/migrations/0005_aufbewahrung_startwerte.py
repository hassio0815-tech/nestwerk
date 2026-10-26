"""Startwerte Aufbewahrung (B-15, Review AP31)."""

from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben

STARTWERTE = {
    "benachrichtigung.aufbewahrung_ungelesen_tage": 180,
    "benachrichtigung.zustellung_aufbewahrung_tage": 90,
}


def vorwaerts(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("benachrichtigung", "0004_push_erlaubte_hosts"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
