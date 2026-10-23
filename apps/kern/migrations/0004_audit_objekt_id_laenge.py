"""AuditEintrag.objekt_id: 40 -> 100 Zeichen (Einstellungs-Schlüssel bis 100 Zeichen).

SQLite baut die Tabelle für ``AlterField`` neu auf (neue Tabelle, Kopie, alte löschen); dabei
gehen Trigger der alten Tabelle verloren. Deshalb: Insert-only-Trigger vorher entfernen und
danach neu anlegen (auch rückwärts), damit UPDATE/DELETE weiterhin abbrechen.
"""

from django.db import migrations, models

from apps.kern.db import nur_einfuegen_trigger

TABELLE = "kern_auditeintrag"
_trigger = nur_einfuegen_trigger(TABELLE)


class Migration(migrations.Migration):
    dependencies = [("kern", "0003_konten_fremdschluessel")]

    operations = [
        # vorwärts: Trigger weg (vor dem Neuaufbau); rückwärts: Trigger wieder anlegen
        migrations.RunSQL(sql=_trigger.reverse_sql, reverse_sql=_trigger.sql),
        migrations.AlterField(
            model_name="auditeintrag",
            name="objekt_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        # vorwärts: Trigger neu; rückwärts: Trigger weg (vor dem Rückbau)
        nur_einfuegen_trigger(TABELLE),
    ]
