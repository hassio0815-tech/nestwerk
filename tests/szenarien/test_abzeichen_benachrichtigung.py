"""AP23: Neues Abzeichen erreicht Kind (Pop-up) und Eltern (Benachrichtigung), deutsche Texte."""

from datetime import timedelta

from apps.benachrichtigung import router, texte, versand
from apps.benachrichtigung.models import Benachrichtigung, Popup
from apps.ereignisse.models import Ereignis
from apps.spielregeln import services
from apps.spielregeln.models import Aktivitaet
from apps.spielregeln.tests.conftest import GO_LIVE, lok


def test_abzeichen_popup_und_eltern(anna, mama, uhr):
    Aktivitaet.objects.create(kind=anna, datum=GO_LIVE + timedelta(days=1), modul="t", referenz=1)
    uhr.stellen(lok(2026, 10, 28, 12))
    services.wochen_sicherstellen(anna)
    ereignis = Ereignis.objects.get(typ_id="abzeichen.verliehen")
    assert texte.rendern(ereignis, "Neues Abzeichen") == (
        "Neues Abzeichen: Wochenserie 1",
        "Anna: Eine aktive Woche geschafft.",
    )
    router.router(ereignis)
    assert set(
        Benachrichtigung.objects.filter(ereignis=ereignis).values_list(
            "empfaenger__anzeigename", flat=True
        )
    ) == {"Anna", "Mama"}
    versand.zustellungen_senden()
    popup = Popup.objects.get(empfaenger=anna, art="abzeichen.verliehen")
    assert popup.titel == "Neues Abzeichen: Wochenserie 1"

    from django.template.loader import render_to_string

    html = render_to_string("benachrichtigung/_popups.html", {"popups": [popup]})
    assert 'data-popup-art="abzeichen"' in html and "toast--abzeichen" in html
