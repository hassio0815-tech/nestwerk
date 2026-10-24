from django.apps import AppConfig


class SpielregelnConfig(AppConfig):
    name = "apps.spielregeln"
    label = "spielregeln"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Spielregeln"

    def ready(self):
        from apps.ereignisse import registry as ereignis_registry

        from . import raenge, registry, services
        from .einstellungen import einstellungen_definieren
        from .events import typen_deklarieren

        einstellungen_definieren()
        typen_deklarieren()
        registry.metriken_registrieren()
        registry.kacheln_registrieren()
        # XP der gespeicherten Woche aktuell halten (punkte ist vor spielregeln geladen)
        ereignis_registry.handler_registrieren(
            "punkte.gebucht",
            services.xp_nachfuehren,
            name="spielregeln.xp_nachfuehren",
            synchron=True,
        )
        # AP22: Rang bei XP-Zuwachs prüfen (synchron, Savepoint)
        ereignis_registry.handler_registrieren(
            "punkte.gebucht",
            raenge.nach_buchung,
            name="spielregeln.rang_pruefen",
            synchron=True,
        )
