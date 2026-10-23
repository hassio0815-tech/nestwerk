from django.apps import AppConfig


class KontenConfig(AppConfig):
    name = "apps.konten"
    label = "konten"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .einstellungen import einstellungen_definieren

        einstellungen_definieren()
