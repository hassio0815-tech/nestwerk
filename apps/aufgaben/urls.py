from django.urls import path, re_path
from django.views.generic import RedirectView

from . import (
    views,
    views_ablauf,
    views_anerkennung,
    views_nachweis,
    views_schnellknopf,
    views_wochenplan,
)

app_name = "aufgaben"

# Wochenplan (AP14)
wochenplan_urls = [
    path("eltern/wochenplan/", views_wochenplan.wochenplan_ansicht, name="wochenplan"),
    path(
        "eltern/wochenplan/<int:pk>/verschieben/",
        views_wochenplan.instanz_verschieben,
        name="wochenplan_verschieben",
    ),
]

urlpatterns = [
    path("eltern/aufgaben/", views.aufgaben_liste, name="liste"),
    path("eltern/aufgaben/neu/", views.aufgabe_neu, name="neu"),
    path("eltern/aufgaben/<int:pk>/bearbeiten/", views.aufgabe_bearbeiten, name="bearbeiten"),
    path("eltern/aufgaben/<int:pk>/status/<str:status>/", views.aufgabe_status, name="status"),
    # Die frühere Bibliothek ist in den Schnell-Knöpfen aufgegangen (Lesezeichen bleiben gültig)
    re_path(
        r"^eltern/bibliothek/(?:.*)$",
        RedirectView.as_view(pattern_name="aufgaben:schnellknoepfe", permanent=False),
        name="bibliothek_umleitung",
    ),
    path("eltern/kategorien/", views.kategorien_liste, name="kategorien"),
    path("eltern/kategorien/neu/", views.kategorie_neu, name="kategorie_neu"),
    path(
        "eltern/kategorien/<int:pk>/bearbeiten/",
        views.kategorie_bearbeiten,
        name="kategorie_bearbeiten",
    ),
]

# Nachweis-Fotos (AP13)
urlpatterns += [
    path(
        "nachweis/<int:meldung_id>/<str:name>/",
        views_nachweis.nachweis_bild,
        name="nachweis_bild",
    ),
]

# Kinderablauf (AP12)
urlpatterns += [
    path("kind/aufgaben/", views_ablauf.kind_aufgaben, name="kind"),
    path("kind/aufgaben/<int:pk>/waehlen/", views_ablauf.kind_waehlen, name="kind_waehlen"),
    path(
        "kind/aufgaben/<int:pk>/zurueckgeben/",
        views_ablauf.kind_zurueckgeben,
        name="kind_zurueckgeben",
    ),
    path("kind/aufgaben/<int:pk>/melden/", views_ablauf.kind_melden, name="kind_melden"),
    path("kind/aufgaben/<int:pk>/antworten/", views_ablauf.kind_antworten, name="kind_antworten"),
    path("eltern/meldungen/", views_ablauf.entscheidungen, name="entscheidungen"),
    path(
        "eltern/meldungen/<int:pk>/zuteilen/<uuid:kind_id>/",
        views_ablauf.eltern_zuteilen,
        name="zuteilen",
    ),
    path("eltern/meldungen/<int:pk>/loesen/", views_ablauf.eltern_loesen, name="loesen"),
    path(
        "eltern/meldungen/<int:pk>/bestaetigen/",
        views_ablauf.eltern_bestaetigen,
        name="bestaetigen",
    ),
    path("eltern/meldungen/<int:pk>/ablehnen/", views_ablauf.eltern_ablehnen, name="ablehnen"),
    path(
        "eltern/meldungen/<int:pk>/rueckfrage/", views_ablauf.eltern_rueckfrage, name="rueckfrage"
    ),
    path(
        "eltern/meldungen/<int:pk>/sonderpunkte/",
        views_ablauf.eltern_sonderpunkte,
        name="sonderpunkte",
    ),
    path("eltern/pruefen/<int:pk>/passt/", views_ablauf.pruefen_passt, name="pruefen_passt"),
    path("eltern/pruefen/alle/", views_ablauf.pruefen_alle, name="pruefen_alle"),
    path(
        "eltern/pruefen/<int:pk>/nachbessern/",
        views_ablauf.pruefen_nachbessern,
        name="pruefen_nachbessern",
    ),
    path(
        "eltern/pruefen/<int:pk>/ablehnen/", views_ablauf.pruefen_ablehnen, name="pruefen_ablehnen"
    ),
    path(
        "eltern/meldungen/<int:pk>/korrigieren/",
        views_ablauf.eltern_korrigieren,
        name="korrigieren",
    ),
]

# Schnell-Knöpfe (bei Bedarf)
urlpatterns += [
    path("eltern/schnellknoepfe/", views_schnellknopf.schnellknoepfe_seite, name="schnellknoepfe"),
    path(
        "eltern/schnellknopf/<int:pk>/",
        views_schnellknopf.eltern_druecken,
        name="schnellknopf_eltern",
    ),
    path("kind/schnellknopf/<int:pk>/", views_schnellknopf.kind_druecken, name="schnellknopf_kind"),
    path(
        "tablet/schnellknopf/<int:pk>/",
        views_schnellknopf.tablet_waehlen,
        name="schnellknopf_tablet_waehlen",
    ),
    path(
        "tablet/schnellknopf/<int:pk>/druecken/",
        views_schnellknopf.tablet_druecken,
        name="schnellknopf_tablet_druecken",
    ),
]

# Anerkennung (Eltern schenken Punkte ohne Aufgabe)
urlpatterns += [
    path("eltern/anerkennung/", views_anerkennung.anerkennung_vergeben, name="anerkennung"),
]

urlpatterns += wochenplan_urls
