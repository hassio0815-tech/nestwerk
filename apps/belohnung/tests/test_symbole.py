"""Eigene Symbole für Fernsehzeit und Gaming (AP17): Sprite, Auswahl, Seed, Datenmigration."""

import importlib
from pathlib import Path

from django.apps import apps
from django.conf import settings

from apps.belohnung.models import Belohnungskategorie
from apps.belohnung.startwerte import KATEGORIEN
from apps.belohnung.symbole import SYMBOLE

SPRITE = Path(settings.BASE_DIR) / "templates" / "komponenten" / "_sprite.html"
MIGRATION = importlib.import_module("apps.belohnung.migrations.0003_symbole_tv_controller")


def test_alle_symbole_stehen_im_sprite():
    sprite = SPRITE.read_text()
    for schluessel, _ in SYMBOLE:
        assert f'id="i-{schluessel}"' in sprite, schluessel
    assert {"tv", "controller"} <= {s for s, _ in SYMBOLE}


def test_seed_nutzt_tv_und_controller():
    symbole = {name: symbol for name, symbol, _ in KATEGORIEN}
    assert symbole["Fernsehzeit"] == "tv"
    assert symbole["Gaming/Computer"] == "controller"


def test_migration_stellt_nur_platzhalter_um(db):
    Belohnungskategorie.objects.update_or_create(name="Fernsehzeit", defaults={"symbol": "uhr"})
    Belohnungskategorie.objects.update_or_create(  # Elternwahl
        name="Gaming/Computer", defaults={"symbol": "pokal"}
    )
    MIGRATION.umstellen(apps, None)
    assert Belohnungskategorie.objects.get(name="Fernsehzeit").symbol == "tv"
    assert Belohnungskategorie.objects.get(name="Gaming/Computer").symbol == "pokal"
