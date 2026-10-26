from django.urls import path

from . import views, views_push

app_name = "benachrichtigung"

urlpatterns = [
    path("eltern/benachrichtigungen/", views.liste, name="liste"),
    path("eltern/benachrichtigungen/teil/", views.liste_teil, name="liste_teil"),
    path("eltern/benachrichtigungen/zaehler/", views.zaehler, name="zaehler"),
    path("eltern/benachrichtigungen/alle-gelesen/", views.alle_gelesen, name="alle_gelesen"),
    path("eltern/benachrichtigungen/<int:pk>/gelesen/", views.gelesen, name="gelesen"),
    path("eltern/benachrichtigungen/<int:pk>/oeffnen/", views.oeffnen, name="oeffnen"),
    path("eltern/benachrichtigungen/einstellungen/", views.einstellungen, name="einstellungen"),
    path(
        "eltern/benachrichtigungen/einstellungen/praeferenz/", views.praeferenz, name="praeferenz"
    ),
    path(
        "eltern/benachrichtigungen/einstellungen/ruhezeit/",
        views.ruhezeit_speichern,
        name="ruhezeit",
    ),
    path("eltern/benachrichtigungen/einstellungen/profil/", views.profil, name="profil"),
    path("kind/popups/", views.popups, name="popups"),
    # PWA und Web-Push (AP08): sw.js im Root-Scope, öffentlich und ohne Cache
    path("sw.js", views_push.service_worker, name="sw"),
    path("manifest.json", views_push.manifest, name="manifest"),
    path("offline/", views_push.offline, name="offline"),
    path("push/", views_push.push_geraet, name="push_geraet"),
    path("push/abo/", views_push.abo_anmelden, name="push_abo"),
    path("push/abo/abmelden/", views_push.abo_abmelden, name="push_abmelden"),
    path("eltern/push/test/", views_push.test_push, name="push_test"),
]
