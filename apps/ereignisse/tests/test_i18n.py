from django.utils import translation

from apps.ereignisse.models import Zielgruppe


def test_zielgruppen_auf_englisch():
    assert str(Zielgruppe.BEIDE.label) == "Eltern und Kind"
    with translation.override("en"):
        assert str(Zielgruppe.BEIDE.label) == "Parents and child"
