from django.urls import include, path

from famko.gesundheit import gesundheit

urlpatterns = [
    path("gesundheit/", gesundheit, name="gesundheit"),
    path("", include("apps.oberflaeche.urls")),
    path("", include("apps.konten.urls")),
]
