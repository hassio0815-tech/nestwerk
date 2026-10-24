"""AP27: God-Mode-Mod-Sets (DATA_MODEL 9.3) und Startwert des God-Mode-Zyklus."""

import django.db.models.deletion
from django.db import migrations, models

from apps.avatar.einstellungen import STARTWERTE
from apps.kern.einstellungen import startwerte_schreiben


def startwerte(apps, schema_editor):
    """AP27: avatar.godmode_zyklus_aktivwochen (überschreibt nie bestehende Werte)."""
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0001_initial"),
        ("avatar", "0003_startwerte"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModSet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nummer", models.PositiveSmallIntegerField()),
                ("name", models.CharField(max_length=60)),
            ],
            options={
                "verbose_name": "Mod-Set",
                "verbose_name_plural": "Mod-Sets",
                "ordering": ["thema__reihenfolge", "nummer"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="moddefinition",
            name="avatar_mod_thema_slot_seltenheit",
        ),
        migrations.AddField(
            model_name="modset",
            name="thema",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="modsets",
                to="avatar.thema",
            ),
        ),
        migrations.AddField(
            model_name="moddefinition",
            name="modset",
            field=models.ForeignKey(
                blank=True,
                help_text="Nur God-Mode-Zyklus-Sets (AP27)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mods",
                to="avatar.modset",
            ),
        ),
        migrations.AddConstraint(
            model_name="moddefinition",
            constraint=models.UniqueConstraint(
                condition=models.Q(("modset__isnull", True)),
                fields=("thema", "slot", "seltenheit"),
                name="avatar_mod_thema_slot_seltenheit",
            ),
        ),
        migrations.AddConstraint(
            model_name="moddefinition",
            constraint=models.UniqueConstraint(
                condition=models.Q(("modset__isnull", False)),
                fields=("thema", "slot", "modset"),
                name="avatar_mod_thema_slot_modset",
            ),
        ),
        migrations.AddConstraint(
            model_name="modset",
            constraint=models.UniqueConstraint(
                fields=("thema", "nummer"), name="avatar_modset_thema_nummer"
            ),
        ),
        migrations.AddConstraint(
            model_name="modset",
            constraint=models.CheckConstraint(
                condition=models.Q(("nummer__gte", 1)), name="avatar_modset_nummer_ab_1"
            ),
        ),
        migrations.RunPython(startwerte, migrations.RunPython.noop),
    ]
