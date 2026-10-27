from django.utils import translation

from apps.punkte.models import Art


def test_buchungsarten_auf_englisch():
    assert str(Art.SERIENBONUS.label) == "Serienbonus"
    with translation.override("en"):
        assert str(Art.SERIENBONUS.label) == "Streak bonus"
