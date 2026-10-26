from django.urls import path

from . import views

app_name = "belohnung"

urlpatterns = [
    # Kind
    path("kind/belohnungen/", views.kind_katalog, name="kind"),
    path("kind/belohnungen/<int:pk>/beantragen/", views.beantragen, name="beantragen"),
    path(
        "kind/belohnungen/antrag/<int:pk>/zurueckziehen/", views.zurueckziehen, name="zurueckziehen"
    ),
    # Eltern
    path("eltern/belohnungen/", views.antraege, name="antraege"),
    path("eltern/belohnungen/antrag/<int:pk>/bestaetigen/", views.bestaetigen, name="bestaetigen"),
    path("eltern/belohnungen/antrag/<int:pk>/ablehnen/", views.ablehnen, name="ablehnen"),
    path("eltern/belohnungen/katalog/", views.katalog, name="katalog"),
    path("eltern/belohnungen/katalog/neu/", views.belohnung_neu, name="neu"),
    path(
        "eltern/belohnungen/katalog/<int:pk>/bearbeiten/",
        views.belohnung_bearbeiten,
        name="bearbeiten",
    ),
    path("eltern/belohnungen/katalog/<int:pk>/aktiv/", views.belohnung_aktiv, name="aktiv"),
    path("eltern/belohnungen/limit/", views.standard_limit, name="limit"),
    path("eltern/belohnungen/limit/<uuid:kind_id>/", views.kind_limit, name="kind_limit"),
]
