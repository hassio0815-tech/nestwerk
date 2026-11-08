"""Ein Mood-Konzept für alle: Eltern-Wappen werden zu Eltern-Moods (Feld ``mood``).

Vorwärts: ``wappen`` wird bei Eltern nach ``mood`` kopiert (Schlüssel bleiben gleich, z. B.
``nachteule``), danach entfällt ``wappen``. Rückwärts: Eltern-Moods aus dem alten Wappen-Katalog
gehen zurück nach ``wappen`` (eigene Eltern-Moods und „geek“ gibt es dort nicht), ``mood`` der
Eltern wird geleert (vorher gab es dort keinen). Eigene Moods bekommen eine Zielgruppe
(Bestand: ``kind``)."""

import django.db.models.functions.text
from django.db import migrations, models

ALTE_WAPPEN = (
    "hausdrache",
    "rudelchef",
    "kuechenchef",
    "familientaxi",
    "bank",
    "grillmeister",
    "nachteule",
    "sockenfinder",
    "burgherr",
)


def wappen_zu_mood(apps, schema_editor):
    Benutzer = apps.get_model("konten", "Benutzer")
    for b in Benutzer.objects.filter(rolle="eltern").exclude(wappen=""):
        b.mood = b.wappen
        b.save(update_fields=["mood"])


def mood_zu_wappen(apps, schema_editor):
    Benutzer = apps.get_model("konten", "Benutzer")
    for b in Benutzer.objects.filter(rolle="eltern"):
        b.wappen = b.mood if b.mood in ALTE_WAPPEN else ""
        b.mood = ""
        b.save(update_fields=["wappen", "mood"])


def nichts(apps, schema_editor):
    pass


def eltern_moods_loeschen(apps, schema_editor):
    """Rückweg: Eigene Eltern-Moods gibt es im alten Schema nicht; sie müssten sonst am alten
    (zielgruppenlosen) Unique-Constraint scheitern, wenn der Text auch bei Kindern vorkommt."""
    apps.get_model("konten", "MoodEigen").objects.filter(zielgruppe="eltern").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("konten", "0008_kind_einstellungen_moods"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="moodeigen",
            name="konten_moodeigen_text_ci_uniq",
        ),
        migrations.AddField(
            model_name="moodeigen",
            name="zielgruppe",
            field=models.CharField(
                choices=[("kind", "Kinder"), ("eltern", "Eltern")],
                db_index=True,
                default="kind",
                max_length=6,
            ),
        ),
        migrations.RunPython(nichts, eltern_moods_loeschen),
        migrations.AddConstraint(
            model_name="moodeigen",
            constraint=models.UniqueConstraint(
                models.F("zielgruppe"),
                django.db.models.functions.text.Lower("text"),
                name="konten_moodeigen_zg_text_ci_uniq",
            ),
        ),
        migrations.AlterField(
            model_name="benutzer",
            name="mood",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Gewählter Mood (Katalog-Schlüssel der eigenen Zielgruppe oder eigen-<id>); "
                    "leer = kein Mood."
                ),
                max_length=20,
            ),
        ),
        migrations.RunPython(wappen_zu_mood, mood_zu_wappen),
        migrations.RemoveField(
            model_name="benutzer",
            name="wappen",
        ),
    ]
