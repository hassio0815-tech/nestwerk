from django.urls import path

from . import views

app_name = "familienziel"

urlpatterns = [
    path("eltern/familienziel/", views.eltern_seite, name="eltern"),
    path("eltern/familienziel/belohnung/neu/", views.belohnung_neu, name="belohnung_neu"),
    path(
        "eltern/familienziel/belohnung/<int:pk>/<str:aktion>/",
        views.belohnung_aktion,
        name="belohnung_aktion",
    ),
    path("eltern/familienziel/woche/<int:pk>/", views.woche_setzen, name="woche_setzen"),
    path(
        "eltern/familienziel/woche/<int:pk>/eingeloest/",
        views.woche_eingeloest,
        name="woche_eingeloest",
    ),
    path(
        "eltern/familienziel/grossziel/<int:pk>/eingeloest/",
        views.grossziel_eingeloest,
        name="grossziel_eingeloest",
    ),
    path("kind/familienziel/abstimmen/", views.abstimmen, name="abstimmen"),
]
