from django.urls import path

from . import views

app_name = "spielregeln"

urlpatterns = [
    path("eltern/pausen/", views.pausen, name="pausen"),
    path("eltern/pausen/neu/", views.pause_neu, name="pause_neu"),
    path("eltern/pausen/schalter/", views.schalter, name="schalter"),
    path("eltern/pausen/<int:pk>/beenden/", views.pause_beenden, name="pause_beenden"),
    path("eltern/pausen/<int:pk>/loeschen/", views.pause_loeschen, name="pause_loeschen"),
]
