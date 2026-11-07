"""Vorlage.je_kind: Aufgaben, die jedes Kind für sich erledigt (eigenes Zimmer, eigene Wäsche)."""

from django.db import migrations, models

JE_KIND_TITEL = (
    "Zimmer aufräumen",
    "Zimmer gründlich",
    "Wäsche zusammenlegen & einräumen",
)


def je_kind_setzen(apps, schema_editor):
    Vorlage = apps.get_model("aufgaben", "Vorlage")
    Vorlage.objects.filter(titel__in=JE_KIND_TITEL).update(je_kind=True)


class Migration(migrations.Migration):
    dependencies = [("aufgaben", "0013_startwerte_anerkennung")]

    operations = [
        migrations.AddField(
            model_name="vorlage",
            name="je_kind",
            field=models.BooleanField(
                default=False,
                help_text="Beim Anlegen bekommt jedes Kind eine eigene Aufgabe.",
            ),
        ),
        migrations.RunPython(je_kind_setzen, migrations.RunPython.noop),
    ]
