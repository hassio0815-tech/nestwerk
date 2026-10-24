from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _bibliothek_laden(sender, **kwargs):
    """Nach ``migrate``: Themen, Slots und Beispiel-Baupläne aus der Bibliothek anlegen
    (idempotent, überschreibt keine in der Datenbank geänderten Zeilen)."""
    from django.db import connections

    verbindung = connections[kwargs.get("using", "default")]
    if "avatar_thema" not in verbindung.introspection.table_names():
        return  # z. B. "migrate avatar zero"
    from .bibliothek_db import bibliothek_laden

    bibliothek_laden()


class AvatarConfig(AppConfig):
    name = "apps.avatar"
    label = "avatar"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import registry
        from .einstellungen import einstellungen_definieren
        from .events import texte_registrieren, typen_deklarieren

        post_migrate.connect(_bibliothek_laden, sender=self, dispatch_uid="avatar.bibliothek_laden")
        einstellungen_definieren()
        typen_deklarieren()
        texte_registrieren()
        registry.metriken_registrieren()
        registry.kacheln_registrieren()
