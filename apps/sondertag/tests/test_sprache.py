"""Texte der Sondertage in beiden Sprachen."""

import pytest
from django.utils import translation

from apps.sondertag import selectors, services

pytestmark = pytest.mark.django_db


def test_noch_text_deutsch_und_englisch():
    assert selectors.noch_text(2, 1) == "Noch 2 Mods und 1 Woche bis zum Sondertag"
    with translation.override("en"):
        assert selectors.noch_text(2, 1) == "2 mods and 1 week to go until your special day"
        assert selectors.noch_text(1, 0) == "1 mod to go until your special day"
        assert "Almost there" in selectors.noch_text(0, 0)


def test_fehlermeldung_auf_englisch(anna):
    with translation.override("en"):
        with pytest.raises(services.SondertagFehler) as fehler:
            services.wunsch_senden(anna, None, wunsch="", begleitung="egal")
    assert "Write down what you wish for." in str(fehler.value)


def test_status_label_uebersetzt():
    from apps.sondertag.models import Status

    assert str(Status.WUNSCH_OFFEN.label) == "Wunsch offen"
    with translation.override("en"):
        assert str(Status.WUNSCH_OFFEN.label) == "Wish open"


# --- Start-Inhalte, Ereignis-Texte und Formate (docs/i18n.md) ---------------------------------

from datetime import date, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

from apps.benachrichtigung import texte  # noqa: E402
from apps.ereignisse.models import Ereignis  # noqa: E402
from apps.kern.sprache import uebersetzt  # noqa: E402
from apps.sondertag import events, prognose  # noqa: E402
from apps.sondertag.meilensteine_start import rang_schluessel  # noqa: E402
from apps.spielregeln.models import MeilensteinErreicht, MeilensteinRegel  # noqa: E402


def _text(typ):
    ereignis = Ereignis.objects.filter(typ_id=typ).order_by("-pk").first()
    return texte.rendern(ereignis, typ)


def _anspruch_mit_wartezeit(anna, mama):
    """Ein manueller Sondertag gestern: der neue Anspruch ist erst in ca. 150 Tagen einlösbar."""
    from apps.kern import zeit

    services.manuell_erfassen(anna, von=mama, datum=zeit.heute() - timedelta(days=1))
    regel = MeilensteinRegel.objects.get(schluessel=rang_schluessel(2))
    fakt = MeilensteinErreicht.objects.create(kind=anna, regel=regel)
    return services.anspruch_anlegen(anna, fakt.pk, titel=regel.name)


def test_meilenstein_name_englisch_umbenannt_unveraendert():
    regel = MeilensteinRegel.objects.get(schluessel=rang_schluessel(3))
    with translation.override("en"):
        assert uebersetzt(regel.name) == "Special day: all 6 slots in Rare"
        assert "Reached rank Rare" in uebersetzt(regel.beschreibung)
    assert uebersetzt(regel.name) == "Sondertag: Ausbaustufe 6 in Rare"
    regel.name = "Unser Ausflugstag"
    with translation.override("en"):
        assert uebersetzt(regel.name) == "Unser Ausflugstag"


def test_hinweis_im_ereignis_in_sprache_des_empfaengers(anna, mama):
    a = _anspruch_mit_wartezeit(anna, mama)
    assert a.einloesbar_ab > date.today()
    de, en = a.einloesbar_ab.strftime("%d.%m.%Y"), a.einloesbar_ab.strftime("%m/%d/%Y")
    titel, text = _text(events.FREIGESCHALTET)
    assert titel == "Sondertag verdient!"
    assert text == f"Einlösbar ab {de}. Deinen Wunsch kannst du schon jetzt schicken."
    with translation.override("en"):
        titel, text = _text(events.FREIGESCHALTET)
        assert text == f"Ready from {en}. You can send your wish right now."
        # Eltern-Ereignis: Titel aus dem Start-Meilenstein wird mit übersetzt
        assert "Special day: all 6 slots in Uncommon" in _text(events.VERDIENT_ELTERN)[1]
    assert "Sondertag: Ausbaustufe 6 in Uncommon" in _text(events.VERDIENT_ELTERN)[1]


def test_alter_hinweis_ohne_msgid_bleibt_lesbar(anna, mama):
    _anspruch_mit_wartezeit(anna, mama)
    Ereignis.objects.filter(typ_id=events.FREIGESCHALTET).update(
        daten={"titel": "x", "hinweis": "Alter deutscher Hinweis."}
    )
    with translation.override("en"):
        assert _text(events.FREIGESCHALTET)[1] == "Alter deutscher Hinweis."


def test_wunsch_ereignis_begleitung_und_hinweis_englisch(anna, mama):
    a = _anspruch_mit_wartezeit(anna, mama)
    services.wunsch_senden(anna, a, wunsch="Zoo", begleitung="papa")
    assert "Begleitung: Papa." in _text(events.WUNSCH)[1]
    with translation.override("en"):
        text = _text(events.WUNSCH)[1]
    assert "Dad" in text and "Papa" not in text and "Mum" not in text
    assert "You can accept it from" in text or "accept" in text


def test_manuell_titel_wird_uebersetzt(anna, mama):
    a = services.manuell_erfassen(anna, von=mama, datum=date(2026, 1, 5))
    assert a.titel == "manuell erfasst"
    with translation.override("en"):
        assert uebersetzt(a.titel) == "added manually"


def test_datum_und_faktor_folgen_der_sprache():
    tag = date(2026, 10, 30)
    assert services.datum_text(tag) == "30.10.2026"
    assert prognose.faktor_text(Decimal("0.85")) == "0,85"
    with translation.override("en"):
        assert services.datum_text(tag) == "10/30/2026"
        assert prognose.faktor_text(Decimal("0.85")) == "0.85"
