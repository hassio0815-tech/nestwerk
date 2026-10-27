"""Zweisprachigkeit: englische Eltern-Seite und Fehlermeldungen."""

import pytest
from django.utils import translation

from apps.familienziel import services
from apps.familienziel.models import AbstimmungStatus

pytestmark = pytest.mark.django_db


def test_eltern_seite_englisch(eltern_client, mama, uhr):
    mama.sprache = "en"
    mama.save()
    html = eltern_client.get("/eltern/familienziel/").content.decode()
    assert "Reward list" in html and "Current week" in html
    assert "Belohnungsliste" not in html


def test_fehlermeldung_englisch(anna, mama):
    with translation.override("en"):
        with pytest.raises(services.FamilienzielFehler, match="only kids vote|Only kids vote"):
            services.stimme_abgeben(mama, 1)
    assert AbstimmungStatus.GLEICHSTAND.label == "Eltern entscheiden"
    with translation.override("en"):
        assert str(AbstimmungStatus.GLEICHSTAND.label) == "Parents decide"


def test_grossziel_name_start_wert_englisch_umbenannt_unveraendert():
    from apps.kern.sprache import uebersetzt

    with translation.override("en"):
        assert uebersetzt("Ausflug") == "Day trip"
        assert uebersetzt("Zoo-Tag") == "Zoo-Tag"


def test_start_belohnung_englisch_umbenannt_unveraendert():
    from apps.familienziel.models import Familienbelohnung

    pizza = Familienbelohnung.objects.get(titel="Pizza")
    eis = Familienbelohnung.objects.get(titel="Eis essen")
    with translation.override("en"):
        assert str(eis) == "Ice cream" and str(pizza) == "Pizza"
    assert str(eis) == "Eis essen"
    eis.titel = "Eisdiele"
    with translation.override("en"):
        assert str(eis) == "Eisdiele"


def test_grossziel_ereignis_im_empfaenger_text_englisch(anna):
    from apps.benachrichtigung import texte
    from apps.ereignisse import services as ereignisse
    from apps.familienziel import events

    ereignis = ereignisse.veroeffentlichen(
        events.GROSSZIEL, daten={"grossziel": "Ausflug", "woche": "2026-W44"}
    )
    assert texte.rendern(ereignis, "x")[0] == "Großes Ziel freigeschaltet: Ausflug!"
    with translation.override("en"):
        assert texte.rendern(ereignis, "x")[0] == "Big goal unlocked: Day trip!"
