"""Startwerte: Kategorien (Entscheidung 16) und Bibliotheksvorlagen (Entscheidung 15)."""

from django.db import migrations
from django.utils.translation import gettext_noop

KATEGORIEN = [
    # (name, symbol, systemschluessel)
    (gettext_noop("Haushalt"), "home", ""),
    (gettext_noop("Küche"), "kueche", ""),
    (gettext_noop("Wäsche"), "waesche", ""),
    (gettext_noop("Garten"), "garten", ""),
    (gettext_noop("Schule"), "schule", "schule"),
    (gettext_noop("Sonstiges"), "liste", ""),
]

VORLAGEN = [
    # (titel, punkte, freigabeart, kategorie)
    (gettext_noop("Müll rausbringen"), 5, "vertrauen", gettext_noop("Haushalt")),
    (gettext_noop("Mülltonnen rausstellen"), 10, "vertrauen", gettext_noop("Haushalt")),
    (gettext_noop("Leergut"), 15, "vertrauen", gettext_noop("Haushalt")),
    (gettext_noop("Altglas"), 15, "vertrauen", gettext_noop("Haushalt")),
    (gettext_noop("Spülmaschine ausräumen"), 10, "vertrauen", gettext_noop("Küche")),
    (gettext_noop("Spülmaschine einräumen"), 10, "vertrauen", gettext_noop("Küche")),
    (gettext_noop("Tisch decken/abräumen"), 10, "vertrauen", gettext_noop("Küche")),
    (gettext_noop("Einkaufsliste"), 10, "eltern", gettext_noop("Küche")),
    (gettext_noop("Wäsche waschen"), 15, "eltern", gettext_noop("Wäsche")),
    (gettext_noop("Wäsche aufhängen"), 15, "eltern", gettext_noop("Wäsche")),
    (gettext_noop("Wäsche zusammenlegen & einräumen"), 20, "eltern", gettext_noop("Wäsche")),
    (gettext_noop("Flur saugen"), 15, "eltern", gettext_noop("Haushalt")),
    (gettext_noop("Zimmer gründlich"), 30, "nachweis", gettext_noop("Haushalt")),
    (gettext_noop("Bad putzen"), 40, "nachweis", gettext_noop("Haushalt")),
    (gettext_noop("Rasen mähen"), 45, "nachweis", gettext_noop("Garten")),
    (gettext_noop("Auto aussaugen"), 30, "nachweis", gettext_noop("Sonstiges")),
    (gettext_noop("Vokabeln lernen 15 Min"), 15, "eltern", gettext_noop("Schule")),
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
