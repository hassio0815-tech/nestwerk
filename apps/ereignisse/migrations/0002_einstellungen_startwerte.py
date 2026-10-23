from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben

STARTWERTE = {
    "ereignisse.max_versuche": 8,
    "ereignisse.backoff_basis_sekunden": 30,
    "ereignisse.backoff_max_sekunden": 3600,
}


def vorwaerts(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


def rueckwaerts(apps, schema_editor):
    apps.get_model("kern", "Einstellung").objects.filter(schluessel__in=STARTWERTE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ereignisse", "0001_initial"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]
