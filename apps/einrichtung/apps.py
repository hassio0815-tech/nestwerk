from django.apps import AppConfig


class EinrichtungConfig(AppConfig):
    name = "apps.einrichtung"
    label = "einrichtung"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import einstellungen

        einstellungen.einstellungen_definieren()
