from django.db import migrations

from apps.kern.einstellungen import startwerte_schreiben

STARTWERTE = {
    "benachrichtigung.push_ttl_standard_sekunden": 86400,
    "benachrichtigung.zustellung_max_versuche": 5,
    "benachrichtigung.aufbewahrung_tage": 90,
}

KANAELE = {"email": "E-Mail", "push": "Push", "popup": "Pop-up in der App"}


def vorwaerts(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)
    kanal = apps.get_model("benachrichtigung", "Kanal")
    for slug, bezeichnung in KANAELE.items():
        kanal.objects.get_or_create(slug=slug, defaults={"bezeichnung": bezeichnung})


def rueckwaerts(apps, schema_editor):
    apps.get_model("kern", "Einstellung").objects.filter(schluessel__in=STARTWERTE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("benachrichtigung", "0001_initial"),
        ("kern", "0001_initial"),
    ]

    operations = [migrations.RunPython(vorwaerts, rueckwaerts)]
