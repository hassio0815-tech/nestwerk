from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben
from apps.lernen.einstellungen import STARTWERTE_PUNKTE, STARTWERTE_RUNDE


def anlegen(apps, schema_editor):
    einstellung = apps.get_model("kern", "Einstellung")
    startwerte_schreiben(einstellung, STARTWERTE_PUNKTE)
    startwerte_schreiben(einstellung, STARTWERTE_RUNDE)
    # Das Tageslimit sinkt von 10 auf 8, aber nur, wenn es noch der alte Startwert ist
    einstellung.objects.filter(schluessel="lernen.lernpunkte_tageslimit", wert=10).update(wert=8)


class Migration(migrations.Migration):
    dependencies = [
        ("lernen", "0025_etappe14_metakognition"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
