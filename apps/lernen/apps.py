from django.apps import AppConfig


class LernenConfig(AppConfig):
    name = "apps.lernen"
    label = "lernen"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Lernen"

    def ready(self):
        from . import events, registry
        from .einstellungen import einstellungen_definieren

        einstellungen_definieren()
        events.typen_deklarieren()
        events.texte_registrieren()
        registry.kacheln_registrieren()
        registry.metriken_registrieren()
