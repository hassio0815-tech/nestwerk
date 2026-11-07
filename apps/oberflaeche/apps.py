from django.apps import AppConfig


class OberflaecheConfig(AppConfig):
    name = "apps.oberflaeche"
    label = "oberflaeche"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .einstellungen import einstellungen_definieren
        from .events import texte_registrieren, typen_deklarieren
        from .registry import kacheln_registrieren
        from .uebernehmen import nach_anmeldung

        user_logged_in.connect(nach_anmeldung, dispatch_uid="oberflaeche.uebernehmen")
        einstellungen_definieren()
        kacheln_registrieren()
        typen_deklarieren()
        texte_registrieren()
