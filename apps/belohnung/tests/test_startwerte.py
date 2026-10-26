from importlib import import_module

import pytest
from django.apps import apps as django_apps

from apps.belohnung.models import Belohnung, Belohnungskategorie
from apps.kern import einstellungen
from apps.kern.models import Einstellung

pytestmark = pytest.mark.django_db

# Entscheidung 13 (docs / nestwerk-decisions)
KATEGORIEN = ["Süßes", "Fernsehzeit", "Gaming/Computer", "Taschengeld", "Sonstiges"]
KATALOG = {
    ("Süßes klein", "Süßes", 15, None),
    ("Süßes groß", "Süßes", 30, None),
    ("30 Min Fernsehen", "Fernsehzeit", 30, None),
    ("30 Min Konsole", "Gaming/Computer", 45, None),
    ("30 Min PC", "Gaming/Computer", 45, None),
    ("1 € Taschengeld", "Taschengeld", 30, 100),
}


def test_kategorien_exakt():
    kategorien = list(Belohnungskategorie.objects.order_by("reihenfolge"))
    assert [k.name for k in kategorien] == KATEGORIEN
    assert all(k.symbol for k in kategorien)
    assert Belohnungskategorie.objects.get(systemschluessel="taschengeld").name == "Taschengeld"


def test_katalog_exakt():
    vorhanden = {
        (b.titel, b.kategorie.name, b.preis_punkte, b.geldwert_cent)
        for b in Belohnung.objects.select_related("kategorie")
    }
    assert vorhanden == KATALOG
    assert Belohnung.objects.filter(aktiv=True).count() == len(KATALOG)


def test_limit_startwert_aus_der_migration():
    """Die Migration schreibt 10 €/Monat; wiederholt sie sich, bleibt alles unverändert."""
    migration = import_module("apps.belohnung.migrations.0002_startwerte")
    Einstellung.objects.filter(schluessel="belohnung.taschengeld_limit_cent").delete()
    migration.startwerte(django_apps, None)
    assert einstellungen.wert("belohnung.taschengeld_limit_cent") == 1000
    einstellungen.setzen("belohnung.taschengeld_limit_cent", 1500, akteur=None)
    migration.startwerte(django_apps, None)
    assert einstellungen.wert("belohnung.taschengeld_limit_cent") == 1500
    assert Belohnung.objects.count() == len(KATALOG)
