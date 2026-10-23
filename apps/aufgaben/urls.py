from django.urls import path

from . import views

app_name = "aufgaben"

urlpatterns = [
    path("eltern/aufgaben/", views.aufgaben_liste, name="liste"),
    path("eltern/aufgaben/neu/", views.aufgabe_neu, name="neu"),
    path("eltern/aufgaben/<int:pk>/bearbeiten/", views.aufgabe_bearbeiten, name="bearbeiten"),
    path("eltern/aufgaben/<int:pk>/status/<str:status>/", views.aufgabe_status, name="status"),
    path("eltern/bibliothek/", views.vorlagen_liste, name="vorlagen"),
    path("eltern/bibliothek/neu/", views.vorlage_neu, name="vorlage_neu"),
    path(
        "eltern/bibliothek/<int:pk>/bearbeiten/",
        views.vorlage_bearbeiten,
        name="vorlage_bearbeiten",
    ),
    path("eltern/bibliothek/<int:pk>/loeschen/", views.vorlage_loeschen, name="vorlage_loeschen"),
    path(
        "eltern/bibliothek/<int:pk>/als-aufgabe/",
        views.vorlage_als_aufgabe,
        name="vorlage_als_aufgabe",
    ),
    path("eltern/kategorien/", views.kategorien_liste, name="kategorien"),
    path("eltern/kategorien/neu/", views.kategorie_neu, name="kategorie_neu"),
    path(
        "eltern/kategorien/<int:pk>/bearbeiten/",
        views.kategorie_bearbeiten,
        name="kategorie_bearbeiten",
    ),
]
