from django.apps import AppConfig


class AufgabenConfig(AppConfig):
    name = "apps.aufgaben"
    label = "aufgaben"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import ablauf, aktivitaet, instanzen, nachweise
        from .einstellungen import einstellungen_definieren
        from .events import texte_registrieren, typen_deklarieren

        einstellungen_definieren()
        nachweise.registrieren()
        typen_deklarieren()
        texte_registrieren()
        instanzen.reservierungsablauf_hook_registrieren(ablauf.interesse_abgelaufen)
        aktivitaet.registrieren()  # spielregeln: Aktivität/Storno (AP20)
