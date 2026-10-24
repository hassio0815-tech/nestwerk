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
        from apps.kern.registry import KIND, Kachel, kachel_registrieren

        from . import kacheln

        post_migrate.connect(_bibliothek_laden, sender=self, dispatch_uid="avatar.bibliothek_laden")
        kachel_registrieren(
            Kachel(
                "avatar.kind_avatar",
                "avatar",
                "Mein Avatar",
                "avatar/kachel_kind.html",
                {KIND},
                kacheln.kind_kontext,
                sichtbar=kacheln.kind_sichtbar,
                reihenfolge=5,
            )
        )
