"""Registrierungen von spielregeln in ``kern.registry``: Metriken (für die Abzeichen-Engine,
AP23) und Dashboard-Kacheln (Kind: Serie; Eltern: Pausen).

Metrik-Werte: Zu jeder Metrik ``<schluessel>`` gibt es einen Provider ``metrik.<schluessel>``
mit ``funktion(kind) -> int``; Abfrage über ``metrik_wert(schluessel, kind)``.
"""

from apps.kern import registry
from apps.kern.registry import ELTERN, KIND, Kachel, Metrik, Provider

MODUL = "spielregeln"


def metrik_wert(schluessel, kind):
    """Wert einer Metrik für ein Kind (über den Provider ``metrik.<schluessel>``)."""
    return registry.fortschritt(f"metrik.{schluessel}", kind)


def _stand_feld(feld):
    def wert(kind):
        from . import selectors

        return getattr(selectors.stand(kind), feld)

    return wert


METRIKEN = (
    ("wochenserie", "Wochenserie", "Aktive Wochen in Folge (Pausen neutral)", "Wochen"),
    ("aktive_wochen", "Aktive Wochen", "Aktive Wochen insgesamt, nie zurückgesetzt", "Wochen"),
    ("tagesserie", "Tagesserie", "Tage in Folge mit bestätigter Aufgabe (Pausen neutral)", "Tage"),
    ("rekord_wochenserie", "Rekord Wochenserie", "Längste Wochenserie bisher", "Wochen"),
    ("rekord_tagesserie", "Rekord Tagesserie", "Längste Tagesserie bisher", "Tage"),
)
_FELD = {
    "wochenserie": "wochenserie",
    "aktive_wochen": "aktive_wochen_gesamt",
    "tagesserie": "tagesserie",
    "rekord_wochenserie": "rekord_wochenserie",
    "rekord_tagesserie": "rekord_tagesserie",
}


def metriken_registrieren():
    for schluessel, bezeichnung, beschreibung, einheit in METRIKEN:
        registry.metrik_registrieren(
            Metrik(schluessel, MODUL, bezeichnung, beschreibung=beschreibung, einheit=einheit)
        )
        registry.provider_registrieren(
            Provider(f"metrik.{schluessel}", MODUL, bezeichnung, _stand_feld(_FELD[schluessel]))
        )


def _kind_serie(request):
    from . import selectors

    kind = request.user
    return {"stand": selectors.stand(kind), "pause": selectors.aktuelle_pause(kind)}


def _eltern_pausen(request):
    from . import views

    return views.pausen_kachel_kontext()


def kacheln_registrieren():
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.kind_serie",
            MODUL,
            "Meine Serie",
            "spielregeln/kacheln/kind_serie.html",
            {KIND},
            _kind_serie,
            reihenfolge=15,
        )
    )
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.eltern_pausen",
            MODUL,
            "Pausen",
            "spielregeln/kacheln/eltern_pausen.html",
            {ELTERN},
            _eltern_pausen,
            reihenfolge=25,
        )
    )
