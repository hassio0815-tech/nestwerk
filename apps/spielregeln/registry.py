"""Registrierungen von spielregeln in ``kern.registry``: Metriken (für die Abzeichen-Engine,
AP23) und Dashboard-Kacheln (Kind: Serie, Rang; Eltern: Pausen, Ränge).

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


def _rang_stufe(kind):
    from . import selectors

    rang = selectors.aktueller_rang(kind)
    return rang.stufe if rang else 0


def metriken_registrieren():
    for schluessel, bezeichnung, beschreibung, einheit in METRIKEN:
        registry.metrik_registrieren(
            Metrik(schluessel, MODUL, bezeichnung, beschreibung=beschreibung, einheit=einheit)
        )
        registry.provider_registrieren(
            Provider(f"metrik.{schluessel}", MODUL, bezeichnung, _stand_feld(_FELD[schluessel]))
        )
    # AP22: Stufe des höchsten erreichten Rangs (Fakt, sinkt nie) – Abzeichen je Rang (AP23)
    registry.metrik_registrieren(
        Metrik(
            "rang",
            MODUL,
            "Rang",
            beschreibung="Stufe des höchsten erreichten Rangs (1 = Startrang)",
            einheit="Stufe",
        )
    )
    registry.provider_registrieren(Provider("metrik.rang", MODUL, "Rang", _rang_stufe))


def _kind_serie(request):
    from . import selectors

    kind = request.user
    return {"stand": selectors.stand(kind), "pause": selectors.aktuelle_pause(kind)}


def _kind_rang(request):
    from . import selectors

    return {"f": selectors.rang_fortschritt(request.user)}


def _eltern_raenge(request):
    from . import views

    return views.raenge_kachel_kontext()


def _eltern_pausen(request):
    from . import views

    return views.pausen_kachel_kontext()


def kacheln_registrieren():
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.kind_rang",
            MODUL,
            "Mein Rang",
            "spielregeln/kacheln/kind_rang.html",
            {KIND},
            _kind_rang,
            reihenfolge=14,
        )
    )
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.eltern_raenge",
            MODUL,
            "Ränge",
            "spielregeln/kacheln/eltern_raenge.html",
            {ELTERN},
            _eltern_raenge,
            reihenfolge=26,
        )
    )
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
