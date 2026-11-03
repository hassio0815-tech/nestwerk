from django.apps import AppConfig


class LernenConfig(AppConfig):
    name = "apps.lernen"
    label = "lernen"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Lernen"

    def ready(self):
        from .einstellungen import einstellungen_definieren

        # Etappe 1 (Fundament): nur Einstellungen. Ereignisse, Kacheln und Metriken folgen mit
        # den Diensten der späteren Etappen (SPEC 21).
        einstellungen_definieren()
