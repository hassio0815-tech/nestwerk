"""Startwerte von familienziel (AP29): Einstellungen und Startliste der Familienbelohnungen."""

from django.db import migrations

from apps.familienziel.einstellungen import STARTWERTE
from apps.kern.einstellungen import startwerte_schreiben

BELOHNUNGEN = [
    ("Pizza", "geschenk"),
    ("Spieleabend", "controller"),
    ("Kino", "tv"),
    ("Eis essen", "stern"),
    ("Grillen", "garten"),
]


def startwerte(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)
    modell = apps.get_model("familienziel", "Familienbelohnung")
    if modell.objects.exists():
        return
    for nr, (titel, symbol) in enumerate(BELOHNUNGEN, 1):
        modell.objects.create(titel=titel, symbol=symbol, reihenfolge=nr)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("familienziel", "0001_initial"),
    ]

    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
