"""AP22: Rangaufstieg erreicht Kind (festliches Pop-up) und Eltern (Benachrichtigung)."""

from django.db import transaction

from apps.benachrichtigung import router, texte, versand
from apps.benachrichtigung.models import Benachrichtigung, Popup
from apps.ereignisse.models import Ereignis
from apps.punkte import services as punkte
from apps.punkte.models import Art
from apps.spielregeln import services


def test_rangaufstieg_popup_und_eltern(anna, mama, uhr):
    with transaction.atomic():
        punkte.buchen(anna, Art.AUFGABE, 9500, schluessel="t:1", quelle_modul="test", von=None)
    services.raenge_pruefen(anna, aktive_wochen=70)
    ereignis = Ereignis.objects.get(typ_id="rang.aufgestiegen")
    assert texte.rendern(ereignis, "Rangaufstieg") == (
        "Neuer Rang: Epic!",
        "Anna ist aufgestiegen.",
    )
    router.router(ereignis)
    assert set(
        Benachrichtigung.objects.filter(ereignis=ereignis).values_list(
            "empfaenger__anzeigename", flat=True
        )
    ) == {"Anna", "Mama"}
    versand.zustellungen_senden()
    popup = Popup.objects.get(empfaenger=anna)
    assert popup.art == "rang.aufgestiegen" and popup.titel == "Neuer Rang: Epic!"

    html = kind_html(anna)
    assert 'data-popup-art="rang"' in html and "toast--rang" in html


def kind_html(kind):
    from django.template.loader import render_to_string

    return render_to_string(
        "benachrichtigung/_popups.html", {"popups": list(Popup.objects.filter(empfaenger=kind))}
    )
