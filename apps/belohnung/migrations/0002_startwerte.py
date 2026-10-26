"""Startwerte: Kategorien, Katalog und Taschengeld-Limit (Entscheidung 13)."""

from django.db import migrations

from apps.belohnung.einstellungen import STARTWERTE
from apps.belohnung.startwerte import BELOHNUNGEN, KATEGORIEN
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    kategorie_modell = apps.get_model("belohnung", "Belohnungskategorie")
    belohnung_modell = apps.get_model("belohnung", "Belohnung")
    kategorien = {}
    for nr, (name, symbol, schluessel) in enumerate(KATEGORIEN, start=1):
        kategorien[name], _ = kategorie_modell.objects.get_or_create(
            name=name,
            defaults={"symbol": symbol, "systemschluessel": schluessel, "reihenfolge": nr},
        )
    for nr, (titel, kategorie, preis, cent) in enumerate(BELOHNUNGEN, start=1):
        belohnung_modell.objects.get_or_create(
            titel=titel,
            kategorie=kategorien[kategorie],
            defaults={"preis_punkte": preis, "geldwert_cent": cent, "reihenfolge": nr},
        )
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("belohnung", "0001_initial"),
    ]

    # Rückwärts bleiben die Werte stehen (Katalog und Einstellungen gehen nie verloren)
    operations = [migrations.RunPython(startwerte, migrations.RunPython.noop)]
