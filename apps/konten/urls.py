from django.urls import path

from . import views

app_name = "konten"

urlpatterns = [
    path("", views.start, name="start"),
    path("anmelden/kind/<uuid:kind_id>/", views.kind_pin, name="kind_pin"),
    path("anmelden/eltern/", views.eltern_login, name="eltern_login"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("aktiv/", views.aktiv, name="aktiv"),
    path("kind/", views.kind_heim, name="kind_heim"),
    # Alles unter eltern/ ist nur für Eltern (Rollen-Decorator je View)
    path("eltern/", views.eltern_heim, name="eltern_heim"),
    path("eltern/geraete/", views.geraete, name="geraete"),
    path(
        "eltern/geraete/<uuid:geraet_id>/widerrufen/",
        views.geraet_widerrufen,
        name="geraet_widerrufen",
    ),
    path("eltern/kinder/<uuid:kind_id>/entsperren/", views.kind_entsperren, name="kind_entsperren"),
]
