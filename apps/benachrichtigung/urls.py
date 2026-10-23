from django.urls import path

from . import views

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
]
