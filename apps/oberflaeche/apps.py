from django.apps import AppConfig


class OberflaecheConfig(AppConfig):
    name = "apps.oberflaeche"
    label = "oberflaeche"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .einstellungen import einstellungen_definieren
        from .registry import kacheln_registrieren

        einstellungen_definieren()
        kacheln_registrieren()
