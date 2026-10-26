import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.kern import einstellungen
from apps.kern.models import AuditEintrag

pytestmark = pytest.mark.django_db


def test_app_name_setzen_speichert_und_auditiert():
    call_command("app_name_setzen", "Familienhub")
    assert einstellungen.wert("allgemein.anzeigename") == "Familienhub"
    assert AuditEintrag.objects.filter(
        aktion="einstellung.geaendert", objekt_id="allgemein.anzeigename"
    ).exists()


def test_app_name_setzen_lehnt_leer_und_zu_lang_ab():
    with pytest.raises(CommandError):
        call_command("app_name_setzen", "  ")
    with pytest.raises(CommandError):
        call_command("app_name_setzen", "x" * 41)
