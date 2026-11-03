from django.urls import path

from . import views

app_name = "lernen"

urlpatterns = [
    path("kind/lernen/", views.start, name="start"),
    path("kind/lernen/los/", views.los, name="los"),
    path("kind/lernen/ziel/<str:aktion>/", views.ziel_vorschlag, name="ziel_vorschlag"),
    path("kind/lernen/sitzung/<int:pk>/", views.sitzung, name="sitzung"),
    path("kind/lernen/sitzung/<int:pk>/antwort/", views.antwort, name="antwort"),
    path("kind/lernen/sitzung/<int:pk>/hilfe/", views.hilfe, name="hilfe"),
    path("kind/lernen/sitzung/<int:pk>/loesung/", views.loesung, name="loesung"),
    path("kind/lernen/sitzung/<int:pk>/beenden/", views.beenden, name="beenden"),
    path("kind/lernen/sitzung/<int:pk>/rueckschau/", views.rueckschau, name="rueckschau"),
    path("eltern/lernen/", views.eltern_seite, name="eltern"),
    path("eltern/lernen/pause/", views.pause_neu, name="pause_neu"),
    path("eltern/lernen/pause/<int:pk>/loeschen/", views.pause_loeschen, name="pause_loeschen"),
]
