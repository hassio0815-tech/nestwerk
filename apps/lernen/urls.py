from django.urls import path

from . import views, views_ki, views_material, views_tutor

app_name = "lernen"

urlpatterns = [
    path("kind/lernen/", views.start, name="start"),
    path("kind/lernen/los/", views.los, name="los"),
    path("kind/lernen/ziel/<str:aktion>/", views.ziel_vorschlag, name="ziel_vorschlag"),
    path("kind/lernen/sitzung/<int:pk>/", views.sitzung, name="sitzung"),
    path("kind/lernen/sitzung/<int:pk>/antwort/", views.antwort, name="antwort"),
    path("kind/lernen/sitzung/<int:pk>/hilfe/", views.hilfe, name="hilfe"),
    path("kind/lernen/sitzung/<int:pk>/loesung/", views.loesung, name="loesung"),
    path("kind/lernen/sitzung/<int:pk>/beenden/", views.beenden, name="beenden"),
    path("kind/lernen/sitzung/<int:pk>/rueckschau/", views.rueckschau, name="rueckschau"),
    path("eltern/lernen/", views.eltern_seite, name="eltern"),
    path("eltern/lernen/pause/", views.pause_neu, name="pause_neu"),
    path("eltern/lernen/pause/<int:pk>/loeschen/", views.pause_loeschen, name="pause_loeschen"),
    path("eltern/lernen/ki/", views_ki.ki_seite, name="ki"),
    path("eltern/lernen/ki/anbieter/", views_ki.anbieter_speichern, name="ki_anbieter_neu"),
    path(
        "eltern/lernen/ki/anbieter/<int:pk>/",
        views_ki.anbieter_speichern,
        name="ki_anbieter_aendern",
    ),
    path(
        "eltern/lernen/ki/anbieter/<int:pk>/aktivieren/",
        views_ki.anbieter_aktivieren,
        name="ki_aktivieren",
    ),
    path(
        "eltern/lernen/ki/anbieter/<int:pk>/deaktivieren/",
        views_ki.anbieter_deaktivieren,
        name="ki_deaktivieren",
    ),
    path("eltern/lernen/ki/anbieter/<int:pk>/testen/", views_ki.anbieter_testen, name="ki_testen"),
    path("eltern/lernen/ki/zuordnung/", views_ki.zuordnung_setzen, name="ki_zuordnung"),
    # Lernmappe (Etappe 4)
    path("kind/lernen/material/", views_material.mappe, name="material"),
    path("kind/lernen/material/hochladen/", views_material.hochladen, name="material_hochladen"),
    path("kind/lernen/material/<int:pk>/", views_material.eigenes, name="material_kind"),
    path("lernen/material/<int:pk>/datei/", views_material.datei, name="material_datei"),
    path("eltern/lernen/material/", views_material.eltern_liste, name="eltern_material"),
    path(
        "eltern/lernen/material/sammel/",
        views_material.eltern_sammel,
        name="eltern_material_sammel",
    ),
    path(
        "eltern/lernen/material/regel/", views_material.eltern_regel, name="eltern_material_regel"
    ),
    path(
        "eltern/lernen/material/<int:pk>/",
        views_material.eltern_detail,
        name="eltern_material_detail",
    ),
    path(
        "eltern/lernen/material/<int:pk>/<str:aktion>/",
        views_material.eltern_aktion,
        name="eltern_material_aktion",
    ),
    path(
        "eltern/lernen/material/<int:pk>/frage/<int:frage_pk>/",
        views_material.eltern_frage,
        name="eltern_frage",
    ),
    # Tutor (Etappe 5)
    path("kind/lernen/tutor/", views_tutor.start, name="tutor"),
    path("kind/lernen/tutor/neu/", views_tutor.neu, name="tutor_neu"),
    path("kind/lernen/tutor/<int:pk>/", views_tutor.gespraech, name="tutor_gespraech"),
    path("kind/lernen/tutor/<int:pk>/senden/", views_tutor.senden, name="tutor_senden"),
    path("kind/lernen/tutor/<int:pk>/hilfe/", views_tutor.mehr_hilfe, name="tutor_hilfe"),
    path("kind/lernen/tutor/<int:pk>/versuch/", views_tutor.versuch, name="tutor_versuch"),
    path("kind/lernen/tutor/<int:pk>/beenden/", views_tutor.beenden, name="tutor_beenden"),
    path("eltern/lernen/tutor/", views_tutor.eltern_seite, name="eltern_tutor"),
    path(
        "eltern/lernen/tutor/schalter/", views_tutor.eltern_schalter, name="eltern_tutor_schalter"
    ),
    path(
        "eltern/lernen/tutor/<int:pk>/",
        views_tutor.eltern_gespraech,
        name="eltern_tutor_gespraech",
    ),
    path(
        "eltern/lernen/tutor/<int:pk>/loeschen/",
        views_tutor.eltern_loeschen,
        name="eltern_tutor_loeschen",
    ),
]
