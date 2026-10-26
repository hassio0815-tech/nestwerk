from django.apps import AppConfig


class FamilienzielConfig(AppConfig):
    name = "apps.familienziel"
    label = "familienziel"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Familienziel"

    def ready(self):
        from apps.ereignisse import registry as ereignis_registry

        from . import registry, services
        from .einstellungen import einstellungen_definieren
        from .events import typen_deklarieren

        einstellungen_definieren()
        typen_deklarieren()
        registry.kacheln_registrieren()
        # Erfolg live prüfen: XP-Zuwachs/Korrektur und neue Aktivität (Bedingung). Synchron in der
        # Transaktion der Buchung, im Savepoint: ein Fehler kippt die Buchung nicht (Job holt nach).
        for typ, name in (
            ("punkte.gebucht", "familienziel.erfolg_nach_buchung"),
            ("aktivitaet.erfasst", "familienziel.erfolg_nach_aktivitaet"),
        ):
            ereignis_registry.handler_registrieren(
                typ, services.erfolg_nach_ereignis, name=name, synchron=True
            )
