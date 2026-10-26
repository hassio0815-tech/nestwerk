from django.apps import AppConfig


class PunkteConfig(AppConfig):
    name = "apps.punkte"
    label = "punkte"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .events import typen_deklarieren

        typen_deklarieren()
