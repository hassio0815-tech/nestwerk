from django.urls import path

from . import views

app_name = "sondertag"

urlpatterns = [
    path("kind/sondertag/wunsch/", views.wunsch, name="wunsch"),
    path("eltern/sondertage/", views.eltern_seite, name="eltern"),
    path("eltern/sondertage/<int:pk>/annehmen/", views.annehmen, name="annehmen"),
    path("eltern/sondertage/<int:pk>/uebergeben/", views.uebergeben, name="uebergeben"),
    path("eltern/sondertage/<int:pk>/stattgefunden/", views.stattgefunden, name="stattgefunden"),
    path("eltern/sondertage/<int:pk>/aendern/", views.aendern, name="aendern"),
    path("eltern/sondertage/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("eltern/prognose/", views.prognose_seite, name="prognose"),
    path("eltern/prognose/uebernehmen/", views.prognose_uebernehmen, name="prognose_uebernehmen"),
    path("eltern/sondertage/manuell/", views.manuell, name="manuell"),
]
