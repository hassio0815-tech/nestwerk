from django.apps import AppConfig


class KernConfig(AppConfig):
    name = "apps.kern"
    label = "kern"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.db.backends.signals import connection_created

        from .db import sql_funktionen_registrieren
        from .einstellungen import kern_einstellungen_definieren

        connection_created.connect(sql_funktionen_registrieren, dispatch_uid="kern_sql_funktionen")
        kern_einstellungen_definieren()
