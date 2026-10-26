from django.db import migrations

from apps.kern.db import nur_einfuegen_trigger


class Migration(migrations.Migration):
    dependencies = [("punkte", "0001_initial")]

    operations = [nur_einfuegen_trigger("punkte_buchung")]
