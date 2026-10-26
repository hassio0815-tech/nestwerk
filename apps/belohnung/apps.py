from django.apps import AppConfig


class BelohnungConfig(AppConfig):
    name = "apps.belohnung"
    label = "belohnung"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.punkte.registry import reservierung_registrieren

        from .einstellungen import einstellungen_definieren
        from .events import texte_registrieren, typen_deklarieren
        from .selectors import offene_reservierung

        einstellungen_definieren()
        typen_deklarieren()
        texte_registrieren()
        reservierung_registrieren(
            "belohnung.offene_antraege", offene_reservierung, modul="belohnung"
        )
