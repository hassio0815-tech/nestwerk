import random

from django.db import migrations

SCHLUESSEL = [
    "hausdrache", "rudelchef", "kuechenchef", "familientaxi", "bank",
    "grillmeister", "nachteule", "sockenfinder", "burgherr",
]


def vergeben(apps, schema_editor):
    Benutzer = apps.get_model("konten", "Benutzer")
    eltern = list(Benutzer.objects.filter(rolle="eltern").order_by("reihenfolge", "anzeigename"))
    belegt = {b.wappen for b in eltern if b.wappen}
    for b in eltern:
        if b.wappen:
            continue
        frei = [s for s in SCHLUESSEL if s not in belegt] or SCHLUESSEL
        b.wappen = random.choice(frei)
        belegt.add(b.wappen)
        b.save(update_fields=["wappen"])


class Migration(migrations.Migration):
    dependencies = [("konten", "0004_wappen")]
    operations = [migrations.RunPython(vergeben, migrations.RunPython.noop)]
