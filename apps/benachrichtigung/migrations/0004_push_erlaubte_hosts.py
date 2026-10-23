from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben

STARTWERTE = {
    "benachrichtigung.push_erlaubte_hosts": [
        "push.apple.com",
        "fcm.googleapis.com",
        "push.services.mozilla.com",
        "notify.windows.com",
    ],
}


def vorwaerts(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


def rueckwaerts(apps, schema_editor):
    apps.get_model("kern", "Einstellung").objects.filter(schluessel__in=STARTWERTE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("benachrichtigung", "0003_pushabo_felder"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]
