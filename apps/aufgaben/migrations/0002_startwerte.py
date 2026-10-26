"""Startwerte: Kategorien (Entscheidung 16) und Bibliotheksvorlagen (Entscheidung 15)."""

from django.db import migrations

KATEGORIEN = [
    # (name, symbol, systemschluessel)
    ("Haushalt", "home", ""),
    ("Küche", "kueche", ""),
    ("Wäsche", "waesche", ""),
    ("Garten", "garten", ""),
    ("Schule", "schule", "schule"),
    ("Sonstiges", "liste", ""),
]

VORLAGEN = [
    # (titel, punkte, freigabeart, kategorie)
    ("Müll rausbringen", 5, "vertrauen", "Haushalt"),
    ("Mülltonnen rausstellen", 10, "vertrauen", "Haushalt"),
    ("Leergut", 15, "vertrauen", "Haushalt"),
    ("Altglas", 15, "vertrauen", "Haushalt"),
    ("Spülmaschine ausräumen", 10, "vertrauen", "Küche"),
    ("Spülmaschine einräumen", 10, "vertrauen", "Küche"),
    ("Tisch decken/abräumen", 10, "vertrauen", "Küche"),
    ("Einkaufsliste", 10, "eltern", "Küche"),
    ("Wäsche waschen", 15, "eltern", "Wäsche"),
    ("Wäsche aufhängen", 15, "eltern", "Wäsche"),
    ("Wäsche zusammenlegen & einräumen", 20, "eltern", "Wäsche"),
    ("Flur saugen", 15, "eltern", "Haushalt"),
    ("Zimmer gründlich", 30, "nachweis", "Haushalt"),
    ("Bad putzen", 40, "nachweis", "Haushalt"),
    ("Rasen mähen", 45, "nachweis", "Garten"),
    ("Auto aussaugen", 30, "nachweis", "Sonstiges"),
    ("Vokabeln lernen 15 Min", 15, "eltern", "Schule"),
]


def anlegen(apps, schema_editor):
    Kategorie = apps.get_model("aufgaben", "Kategorie")
    Vorlage = apps.get_model("aufgaben", "Vorlage")
    kategorien = {}
    for reihenfolge, (name, symbol, schluessel) in enumerate(KATEGORIEN, start=1):
        kategorien[name], _ = Kategorie.objects.get_or_create(
            name=name,
            defaults={"symbol": symbol, "systemschluessel": schluessel, "reihenfolge": reihenfolge},
        )
    for titel, punkte, freigabe, kategorie in VORLAGEN:
        Vorlage.objects.get_or_create(
            titel=titel,
            defaults={
                "punkte": punkte,
                "freigabeart": freigabe,
                "kategorie": kategorien[kategorie],
                "aktiv": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("aufgaben", "0001_initial")]
    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
