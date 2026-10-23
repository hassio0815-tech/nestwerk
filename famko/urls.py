from django.urls import path

from famko.gesundheit import gesundheit

urlpatterns = [
    path("gesundheit/", gesundheit, name="gesundheit"),
]
