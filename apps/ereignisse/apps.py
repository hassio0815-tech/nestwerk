from django.apps import AppConfig


class EreignisseConfig(AppConfig):
    name = "apps.ereignisse"
    label = "ereignisse"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.db.models.signals import post_migrate

        from .events import typen_deklarieren
        from .services import einstellungen_definieren, typen_synchronisieren

        einstellungen_definieren()
        typen_deklarieren()
        # Sync einmal nach dem gesamten migrate (sender = diese App), Typen anderer Apps
        # sind dann bereits in deren ready() deklariert.
        post_migrate.connect(
            typen_synchronisieren, sender=self, dispatch_uid="ereignisse_typen_sync"
        )
