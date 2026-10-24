from django.urls import include, path

from famko.gesundheit import gesundheit

urlpatterns = [
    path("gesundheit/", gesundheit, name="gesundheit"),
    path("", include("apps.einrichtung.urls")),
    path("", include("apps.oberflaeche.urls")),
    path("", include("apps.konten.urls")),
    path("", include("apps.benachrichtigung.urls")),
    path("", include("apps.aufgaben.urls")),
    path("", include("apps.belohnung.urls")),
    path("", include("apps.avatar.urls")),
    path("", include("apps.spielregeln.urls")),
]
