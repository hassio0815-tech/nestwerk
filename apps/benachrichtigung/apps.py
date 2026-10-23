from django.apps import AppConfig


class BenachrichtigungConfig(AppConfig):
    name = "apps.benachrichtigung"
    label = "benachrichtigung"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.db.models.signals import post_migrate

        from apps.ereignisse import registry as ereignis_registry
        from apps.kern import registry as kern_registry

        from . import kachel, kanaele, router, services, versand

        services.einstellungen_definieren()
        kanaele.eingebaute_registrieren()
        # Router für alle Ereignistypen (auch von Modulen, die später deklarieren)
        ereignis_registry.alle_typen_handler_registrieren(router.router, name=router.ROUTER_NAME)
        ereignis_registry.nachlauf_registrieren(
            "benachrichtigung.versand", versand.zustellungen_senden
        )
        kern_registry.kachel_registrieren(kachel.eltern_kachel())
        post_migrate.connect(
            router.kanaele_synchronisieren, sender=self, dispatch_uid="benachrichtigung_kanaele"
        )
