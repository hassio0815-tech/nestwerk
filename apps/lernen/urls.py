from django.urls import path

from . import (
    views,
    views_ki,
    views_kinder,
    views_material,
    views_plan,
    views_tipps,
    views_tutor,
    views_woche,
)

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
    path("kind/lernen/tipps/", views_tipps.kind_tipps, name="tipps"),
    path("eltern/lernen/tipps/", views_tipps.eltern_tipps, name="eltern_tipps"),
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
    # Prüfungsvorbereitung (Etappe 6)
    path("kind/lernen/pruefung/", views_plan.liste, name="pruefungen"),
    path("kind/lernen/pruefung/neu/", views_plan.neu, name="pruefung_neu"),
    path("kind/lernen/pruefung/anlegen/", views_plan.anlegen, name="pruefung_anlegen"),
    path("kind/lernen/pruefung/<int:pk>/", views_plan.detail, name="pruefung"),
    path(
        "kind/lernen/pruefung/<int:pk>/portion/<int:portion_pk>/start/",
        views_plan.portion_start,
        name="pruefung_portion_start",
    ),
    path("kind/lernen/pruefung/<int:pk>/ziel/", views_plan.ziel_erhoehen, name="pruefung_ziel"),
    path(
        "kind/lernen/pruefung/<int:pk>/stoff/<int:stoff_pk>/entfernen/",
        views_plan.stoff_entfernen,
        name="pruefung_stoff_entfernen",
    ),
    path(
        "kind/lernen/pruefung/<int:pk>/neu-planen/",
        views_plan.neu_planen,
        name="pruefung_neu_planen",
    ),
    path(
        "kind/lernen/pruefung/<int:pk>/abbrechen/", views_plan.abbrechen, name="pruefung_abbrechen"
    ),
    path("kind/lernen/pruefung/<int:pk>/probe/", views_plan.probe_start, name="pruefung_probe"),
    path("kind/lernen/probe/<int:pk>/", views_plan.probe, name="probe"),
    path("kind/lernen/probe/<int:pk>/antwort/", views_plan.probe_antwort, name="probe_antwort"),
    path(
        "kind/lernen/probe/<int:pk>/schwaechen/",
        views_plan.probe_schwaechen,
        name="probe_schwaechen",
    ),
    path("eltern/lernen/pruefung/", views_plan.eltern_liste, name="eltern_pruefungen"),
    path("eltern/lernen/pruefung/<int:pk>/", views_plan.eltern_detail, name="eltern_pruefung"),
    path(
        "eltern/lernen/pruefung/<int:pk>/termin/",
        views_plan.eltern_termin,
        name="eltern_pruefung_termin",
    ),
    path(
        "eltern/lernen/pruefung/<int:pk>/loeschen/",
        views_plan.eltern_loeschen,
        name="eltern_pruefung_loeschen",
    ),
    path("eltern/lernen/kinder/", views_kinder.eltern_kinder, name="eltern_kinder"),
    path(
        "eltern/lernen/kinder/<uuid:pk>/",
        views_kinder.eltern_kind_speichern,
        name="eltern_kind_speichern",
    ),
    path("eltern/lernen/kinder/schuljahr/", views_kinder.eltern_schuljahr, name="eltern_schuljahr"),
    path(
        "eltern/lernen/kinder/schuljahr/bestaetigen/",
        views_kinder.eltern_schuljahr_bestaetigen,
        name="eltern_schuljahr_bestaetigen",
    ),
    path("eltern/lernen/woche/", views_woche.eltern_woche, name="eltern_woche"),
    path(
        "eltern/lernen/woche/titel/",
        views_woche.eltern_titel_schalter,
        name="eltern_titel_schalter",
    ),
]
