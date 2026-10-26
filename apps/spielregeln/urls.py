from django.urls import path

from . import views, views_meilensteine

app_name = "spielregeln"

urlpatterns = [
    path("eltern/pausen/", views.pausen, name="pausen"),
    path("eltern/pausen/neu/", views.pause_neu, name="pause_neu"),
    path("eltern/pausen/schalter/", views.schalter, name="schalter"),
    path("eltern/pausen/<int:pk>/beenden/", views.pause_beenden, name="pause_beenden"),
    path("eltern/pausen/<int:pk>/loeschen/", views.pause_loeschen, name="pause_loeschen"),
    path("eltern/raenge/", views.raenge, name="raenge"),
    path("eltern/raenge/<int:pk>/", views.rang_aendern, name="rang_aendern"),
    path("eltern/raenge/kalibrierung/", views.kalibrierung, name="kalibrierung"),
    path("eltern/abzeichen/", views.abzeichen, name="abzeichen"),
    path("eltern/abzeichen/neu/", views.abzeichen_neu, name="abzeichen_neu"),
    path("eltern/abzeichen/<int:pk>/", views.abzeichen_aendern, name="abzeichen_aendern"),
    path("eltern/abzeichen/<int:pk>/aktiv/", views.abzeichen_aktiv, name="abzeichen_aktiv"),
    path("abzeichen/galerie/", views.abzeichen_galerie, name="abzeichen_galerie"),
    path("eltern/meilensteine/", views_meilensteine.meilensteine, name="meilensteine"),
    path(
        "eltern/meilensteine/<int:pk>/",
        views_meilensteine.meilenstein_aendern,
        name="meilenstein_aendern",
    ),
    path(
        "eltern/meilensteine/<int:pk>/aktiv/",
        views_meilensteine.meilenstein_aktiv,
        name="meilenstein_aktiv",
    ),
]
