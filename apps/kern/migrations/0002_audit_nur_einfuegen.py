from django.db import migrations

from apps.kern.db import nur_einfuegen_trigger


class Migration(migrations.Migration):
    dependencies = [("kern", "0001_initial")]

    operations = [nur_einfuegen_trigger("kern_auditeintrag")]
