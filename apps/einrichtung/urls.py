from django.urls import path

from . import views

app_name = "einrichtung"

urlpatterns = [
    path("einrichtung/", views.start, name="start"),
    path("einrichtung/token/", views.token, name="token"),
    path("einrichtung/schritt/<int:nr>/", views.schritt, name="schritt"),
]
