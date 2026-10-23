from django.apps import AppConfig


class AufgabenConfig(AppConfig):
    name = "apps.aufgaben"
    label = "aufgaben"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .einstellungen import einstellungen_definieren
        from .events import typen_deklarieren

        einstellungen_definieren()
        typen_deklarieren()
