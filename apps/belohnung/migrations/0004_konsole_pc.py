"""Startkatalog: "30 Min Gaming/PC" wird zu "30 Min Konsole"; "30 Min PC" kommt dazu."""

from django.db import migrations


def aufteilen(apps, schema_editor):
    modell = apps.get_model("belohnung", "Belohnung")
    kat = apps.get_model("belohnung", "Belohnungskategorie")
    alt = modell.objects.filter(titel="30 Min Gaming/PC").first()
    if alt:
        alt.titel = "30 Min Konsole"
        alt.save(update_fields=["titel"])
    gaming = kat.objects.filter(name="Gaming/Computer").first()
    if gaming and not modell.objects.filter(titel="30 Min PC").exists():
        konsole = modell.objects.filter(titel="30 Min Konsole").first()
        modell.objects.create(
            titel="30 Min PC",
            kategorie=gaming,
            preis_punkte=konsole.preis_punkte if konsole else 45,
            reihenfolge=(konsole.reihenfolge + 1) if konsole else 5,
        )


class Migration(migrations.Migration):
    dependencies = [("belohnung", "0003_symbole_tv_controller")]
    operations = [migrations.RunPython(aufteilen, migrations.RunPython.noop)]
