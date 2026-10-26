from django.urls import path
from django.views.generic import RedirectView

from apps.oberflaeche import views, views_einstellungen, views_familie

app_name = "oberflaeche"

urlpatterns = [
    path("styleguide/", views.styleguide, name="styleguide"),
    # "/" = Weiche je Rolle/Gerät; die Anmeldung selbst bleibt bei konten
    path("", views.startseite, name="startseite"),
    path("kind/", views.kind_heim, name="kind_heim"),
    path("kind/dungeon/", views.dungeon, name="dungeon"),
    path("eltern/dungeon/", views.eltern_dungeon, name="eltern_dungeon"),
    path("eltern/einstellungen/wappen/", views.wappen_setzen, name="wappen"),
    path("eltern/dungeon/anzeige/", views.dungeon_anzeige_setzen, name="dungeon_anzeige"),
    path("kind/spielwelt/", RedirectView.as_view(pattern_name="oberflaeche:dungeon", permanent=True)),
    path("kind/akzent/", views.akzent_setzen, name="akzent"),
    path("eltern/ranking/modus/", views.ranking_modus, name="ranking_modus"),
    path("module/", views.module_launcher, name="module"),
    path("eltern/", views.eltern_heim, name="eltern_heim"),
    path("tablet/", views.tablet, name="tablet"),
    path("tablet/teil/", views.tablet_teil, name="tablet_teil"),
    path("eltern/einstellungen/", views_einstellungen.uebersicht, name="einstellungen"),
    path(
        "eltern/einstellungen/<str:modul>/",
        views_einstellungen.speichern,
        name="einstellungen_speichern",
    ),
    path("eltern/familie/", views_familie.uebersicht, name="familie"),
    path("eltern/familie/kind/neu/", views_familie.kind_neu, name="familie_kind_neu"),
    path(
        "eltern/familie/kind/<uuid:kind_id>/umbenennen/",
        views_familie.kind_umbenennen,
        name="familie_kind_umbenennen",
    ),
    path(
        "eltern/familie/kind/<uuid:kind_id>/pin/", views_familie.kind_pin, name="familie_kind_pin"
    ),
    path(
        "eltern/familie/kind/<uuid:kind_id>/entsperren/",
        views_familie.kind_entsperren,
        name="familie_kind_entsperren",
    ),
    path(
        "eltern/familie/kind/<uuid:kind_id>/deaktivieren/",
        views_familie.kind_deaktivieren,
        name="familie_kind_deaktivieren",
    ),
    path(
        "eltern/familie/eltern/<uuid:eltern_id>/",
        views_familie.eltern_aendern,
        name="familie_eltern",
    ),
    path("eltern/familie/passwort/", views_familie.passwort, name="familie_passwort"),
]
