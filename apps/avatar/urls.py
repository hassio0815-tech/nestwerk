from django.urls import path, re_path

from . import views, views_mods

app_name = "avatar"

urlpatterns = [
    re_path(r"^avatar/(?P<hash>[0-9a-f]{64})\.svg$", views.svg, name="svg"),
    path("avatar/galerie/", views.galerie, name="galerie"),
    path("kind/avatar/", views.kind_wahl, name="kind_wahl"),
    # AP26: Mod-Shop, Werkstatt, Slots, Themenwechsel
    path("kind/mods/", views_mods.shop, name="shop"),
    path("kind/mods/slot/<slug:slot>/ablegen/", views_mods.ablegen, name="ablegen"),
    path("kind/mods/<slug:schluessel>/", views_mods.mod_detail, name="mod"),
    path("kind/mods/<slug:schluessel>/kaufen/", views_mods.kaufen, name="kaufen"),
    path("kind/mods/<slug:schluessel>/anlegen/", views_mods.anlegen, name="anlegen"),
    path("kind/avatar/thema/", views_mods.thema, name="thema"),
    path("eltern/mods/", views_mods.eltern, name="eltern"),
    path("eltern/mods/standards/", views_mods.standards, name="standards"),
    path("eltern/mods/bau/<int:pk>/fertig/", views_mods.sofort, name="sofort"),
]
