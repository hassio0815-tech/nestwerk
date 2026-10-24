from django.urls import path, re_path

from . import views

app_name = "avatar"

urlpatterns = [
    re_path(r"^avatar/(?P<hash>[0-9a-f]{64})\.svg$", views.svg, name="svg"),
    path("avatar/galerie/", views.galerie, name="galerie"),
    path("kind/avatar/", views.kind_wahl, name="kind_wahl"),
]
