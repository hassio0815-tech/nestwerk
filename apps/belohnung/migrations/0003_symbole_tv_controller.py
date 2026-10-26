"""Eigene Symbole für Fernsehzeit (TV) und Gaming (Controller) statt Platzhalter-Icons.

Nur Kategorien, die noch das ursprüngliche Platzhalter-Symbol tragen, werden umgestellt;
von den Eltern geänderte Symbole bleiben unberührt."""

from django.db import migrations

UMSTELLUNG = {"Fernsehzeit": ("uhr", "tv"), "Gaming/Computer": ("funke", "controller")}


def umstellen(apps, schema_editor):
    modell = apps.get_model("belohnung", "Belohnungskategorie")
    for name, (alt, neu) in UMSTELLUNG.items():
        modell.objects.filter(name=name, symbol=alt).update(symbol=neu)


def zurueck(apps, schema_editor):
    modell = apps.get_model("belohnung", "Belohnungskategorie")
    for name, (alt, neu) in UMSTELLUNG.items():
        modell.objects.filter(name=name, symbol=neu).update(symbol=alt)


class Migration(migrations.Migration):
    dependencies = [("belohnung", "0002_startwerte")]
    operations = [migrations.RunPython(umstellen, zurueck)]
