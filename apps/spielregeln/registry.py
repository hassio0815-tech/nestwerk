"""Registrierungen von spielregeln in ``kern.registry``: Metriken (für die Abzeichen-Engine,
AP23) und Dashboard-Kacheln (Kind: Serie, Rang; Eltern: Pausen, Ränge).

Metrik-Werte: Zu jeder Metrik ``<schluessel>`` gibt es einen Provider ``metrik.<schluessel>``
mit ``funktion(kind) -> int``; Abfrage über ``metrik_wert(schluessel, kind)``.

Bereiche (AP23, optional): Ein Provider ``metrik.<schluessel>.bereiche`` mit
``funktion(kind) -> dict[str, int | tuple[int, str]]`` liefert den Wert je Bereich (z. B.
``{"2027-Q1": (1, "Q1 2027")}`` oder ``{"rang-3": (3, "Rare")}``; Bereich max. 30 Zeichen,
Bezeichnung optional). Regeln mit ``wiederholbar = bereich`` werden je Bereich verliehen/erreicht.

Neue Metrik (z. B. AP26 ``ausbaustufe``, später ``lernen.*``) in ``AppConfig.ready()``::

    registry.metrik_registrieren(Metrik("ausbaustufe", "avatar", "Ausbaustufe", einheit="Slots"))
    registry.provider_registrieren(Provider("metrik.ausbaustufe", "avatar", "Ausbaustufe", fn))
    # optional je Bereich:
    registry.provider_registrieren(Provider("metrik.ausbaustufe.bereiche", "avatar", "…", fn2))

Danach kennt die Abzeichen-/Meilenstein-Engine die Metrik ohne Code-Änderung.
"""

from django.utils.translation import gettext_lazy as _

from apps.kern import registry
from apps.kern.registry import ELTERN, KIND, Kachel, Metrik, Provider

MODUL = "spielregeln"


def metrik_wert(schluessel, kind):
    """Wert einer Metrik für ein Kind (über den Provider ``metrik.<schluessel>``)."""
    return registry.fortschritt(f"metrik.{schluessel}", kind)


def hat_bereiche(schluessel):
    return registry.provider_vorhanden(f"metrik.{schluessel}.bereiche")


def metrik_bereiche(schluessel, kind) -> dict[str, tuple[int, str]] | None:
    """Werte je Bereich ``{bereich: (wert, bezeichnung)}``; ``None`` = Metrik ohne Bereiche."""
    if not hat_bereiche(schluessel):
        return None
    roh = registry.fortschritt(f"metrik.{schluessel}.bereiche", kind) or {}
    ergebnis = {}
    for bereich, eintrag in roh.items():
        wert, bezeichnung = eintrag if isinstance(eintrag, tuple) else (eintrag, "")
        ergebnis[str(bereich)[:30]] = (int(wert), str(bezeichnung or bereich)[:60])
    return ergebnis


def _stand_feld(feld):
    def wert(kind):
        from . import selectors

        return getattr(selectors.stand(kind), feld)

    return wert


METRIKEN = (
    ("wochenserie", _("Wochenserie"), _("Aktive Wochen in Folge (Pausen neutral)"), _("Wochen")),
    (
        "aktive_wochen",
        _("Aktive Wochen"),
        _("Aktive Wochen insgesamt, nie zurückgesetzt"),
        _("Wochen"),
    ),
    (
        "tagesserie",
        _("Tagesserie"),
        _("Tage in Folge mit bestätigter Aufgabe (Pausen neutral)"),
        _("Tage"),
    ),
    ("rekord_wochenserie", _("Rekord Wochenserie"), _("Längste Wochenserie bisher"), _("Wochen")),
    ("rekord_tagesserie", _("Rekord Tagesserie"), _("Längste Tagesserie bisher"), _("Tage")),
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
            _("Rang"),
            beschreibung=_("Stufe des höchsten erreichten Rangs (1 = Startrang)"),
            einheit=_("Stufe"),
        )
    )
    registry.provider_registrieren(Provider("metrik.rang", MODUL, "Rang", _rang_stufe))
    # AP23: je erreichtem Rang ein Bereich ``rang-<stufe>`` (Abzeichen je Rangaufstieg)
    registry.provider_registrieren(
        Provider("metrik.rang.bereiche", MODUL, "Erreichte Ränge", _rang_bereiche)
    )
    registry.metrik_registrieren(
        Metrik(
            "quartal_voll_aktiv",
            MODUL,
            _("Volle Quartale"),
            beschreibung=_("Abgeschlossene Quartale, in denen jede Woche aktiv oder pausiert war"),
            einheit=_("Quartale"),
        )
    )
    registry.provider_registrieren(
        Provider("metrik.quartal_voll_aktiv", MODUL, "Volle Quartale", _volle_quartale)
    )
    registry.provider_registrieren(
        Provider("metrik.quartal_voll_aktiv.bereiche", MODUL, "Quartale", _quartal_bereiche)
    )


def _rang_bereiche(kind):
    from . import selectors

    return {
        f"rang-{f.rang.stufe}": (f.rang.stufe, f.rang.name) for f in selectors.rang_aufstiege(kind)
    }


def _volle_quartale(kind):
    from . import selectors

    return sum(1 for _, _, voll in selectors.abgeschlossene_quartale(kind) if voll)


def _quartal_bereiche(kind):
    from . import selectors

    return {
        f"{jahr}-Q{nummer}": (int(voll), f"Q{nummer} {jahr}")
        for jahr, nummer, voll in selectors.abgeschlossene_quartale(kind)
    }


def _kind_serie(request):
    from . import selectors

    kind = request.user
    return {"stand": selectors.stand(kind), "pause": selectors.aktuelle_pause(kind)}


def _kind_rang(request):
    from apps.kern import einstellungen

    from . import prognose, selectors

    f = selectors.rang_fortschritt(request.user)
    wochen = None
    if f.naechster and einstellungen.wert("spielregeln.prognose_kind_zeigen"):
        ziel = prognose.naechster_rang(request.user)
        wochen = ziel.wochen if ziel and ziel.wochen else None  # nur die Zahl, keine Eltern-Infos
    return {"f": f, "prognose_wochen": wochen}


def _eltern_raenge(request):
    from . import views

    return views.raenge_kachel_kontext()


def _eltern_pausen(request):
    from . import views

    return views.pausen_kachel_kontext()


def _kind_abzeichen(request):
    from . import selectors

    return {"v": selectors.vitrine(request.user)}


def _eltern_abzeichen(request):
    from . import abzeichen

    return {"zeilen": abzeichen.eltern_uebersicht()}


def kacheln_registrieren():
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.kind_abzeichen",
            MODUL,
            _("Meine Abzeichen"),
            "spielregeln/kacheln/kind_abzeichen.html",
            {KIND},
            _kind_abzeichen,
            reihenfolge=16,
        )
    )
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.eltern_abzeichen",
            MODUL,
            _("Abzeichen"),
            "spielregeln/kacheln/eltern_abzeichen.html",
            {ELTERN},
            _eltern_abzeichen,
            reihenfolge=27,
        )
    )
    registry.kachel_registrieren(
        Kachel(
            "spielregeln.kind_rang",
            MODUL,
            _("Mein Rang"),
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
            _("Ränge"),
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
            _("Meine Serie"),
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
            _("Pausen"),
            "spielregeln/kacheln/eltern_pausen.html",
            {ELTERN},
            _eltern_pausen,
            reihenfolge=25,
        )
    )
