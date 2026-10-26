from django.apps import AppConfig


class SondertagConfig(AppConfig):
    name = "apps.sondertag"
    label = "sondertag"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Sondertag"

    def ready(self):
        from apps.ereignisse import registry as ereignis_registry

        from . import events, registry, services
        from .einstellungen import einstellungen_definieren

        einstellungen_definieren()
        events.typen_deklarieren()
        events.texte_registrieren()
        registry.kacheln_registrieren()
        # Anspruch synchron mit dem Meilenstein-Fakt (gleiche Transaktion, idempotent); fällt er
        # aus, holt ``sondertag_sicherstellen`` bzw. die nächste Prüfung ihn nach.
        ereignis_registry.handler_registrieren(
            events.MEILENSTEIN_ERREICHT,
            services.nach_meilenstein,
            name="sondertag.anspruch_aus_meilenstein",
            synchron=True,
        )
