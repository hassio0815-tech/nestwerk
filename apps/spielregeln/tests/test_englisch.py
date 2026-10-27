"""Englische Oberfläche (Entscheidung 45): Deutsch ist Quellsprache, Englisch kommt aus .po."""

import pytest
from django.utils import translation

from apps.spielregeln import raenge
from apps.spielregeln.forms import PauseForm
from apps.spielregeln.models import Vergleich


def test_englische_eltern_seite_per_cookie(eltern_client):
    eltern_client.cookies["nestwerk_sprache"] = "en"
    html = eltern_client.get("/eltern/raenge/").content.decode()
    assert "Calibration" in html and "Levels" in html
    assert "Kalibrierung" not in html


def test_deutsch_bleibt_standard(eltern_client):
    html = eltern_client.get("/eltern/raenge/").content.decode()
    assert "Kalibrierung" in html and "Calibration" not in html


def test_fehlertext_und_auswahl_englisch(db):
    with translation.override("en"):
        assert str(Vergleich.MIN.label) == "at least (≥)"
        assert str(PauseForm.base_fields["grund"].label) == "Reason (optional)"
        with pytest.raises(raenge.RangFehler, match="Only parents"):
            raenge._eltern_pruefen(None)
    with translation.override("de"):
        assert str(Vergleich.MIN.label) == "mindestens (≥)"


# --- Start-Inhalte, Ereignis-Texte und Datumsformate (docs/i18n.md) ---------------------------

from datetime import date  # noqa: E402

from django.utils.translation import gettext  # noqa: E402

from apps.benachrichtigung import texte  # noqa: E402
from apps.ereignisse.models import Ereignis  # noqa: E402
from apps.kern.sprache import uebersetzt  # noqa: E402
from apps.spielregeln import abzeichen, events, services  # noqa: E402
from apps.spielregeln.models import AbzeichenDefinition, AbzeichenVerleihung, Rang  # noqa: E402

from .conftest import lok  # noqa: E402


def _text(typ, **filter):
    ereignis = Ereignis.objects.filter(typ_id=typ, **filter).order_by("-pk").first()
    return texte.rendern(ereignis, typ)


def test_start_abzeichen_und_rang_englisch_umbenannt_unveraendert(db):
    badge = AbzeichenDefinition.objects.get(schluessel="wochenserie-4")
    rang = Rang.objects.get(schluessel="godmode")
    with translation.override("en"):
        assert uebersetzt(badge.name) == "Weekly streak 4"
        assert uebersetzt(badge.beschreibung) == "4 active weeks in a row."
        assert uebersetzt(rang.name) == "God Mode"
    assert uebersetzt(badge.name) == "Wochenserie 4"
    badge.name = "Mein Orden"
    with translation.override("en"):
        assert uebersetzt(badge.name) == "Mein Orden"


def test_vitrine_titel_englisch(anna, db):
    badge = AbzeichenDefinition.objects.get(schluessel="wochenserie-4")
    v = AbzeichenVerleihung.objects.create(kind=anna, abzeichen=badge, wert=4, schwelle=4)
    with translation.override("en"):
        assert abzeichen._titel(v) == "Weekly streak 4"
    assert abzeichen._titel(v) == "Wochenserie 4"


def test_abzeichen_ereignis_im_empfaenger_text(anna, db):
    namen = ("wochenserie-1", "wochenserie-2", "tagesserie-7")
    verleihungen = [
        AbzeichenVerleihung.objects.create(
            kind=anna, abzeichen=AbzeichenDefinition.objects.get(schluessel=s), wert=1, schwelle=1
        )
        for s in namen
    ]
    abzeichen._abzeichen_melden(anna, verleihungen[:1], True)
    titel, text = _text(events.ABZEICHEN_VERLIEHEN)
    assert titel == "Neues Abzeichen: Wochenserie 1"
    with translation.override("en"):
        titel, text = _text(events.ABZEICHEN_VERLIEHEN)
    assert titel == "New badge: Weekly streak 1" and "One active week done." in text

    abzeichen._abzeichen_melden(anna, [*verleihungen[1:], verleihungen[0]], True)
    titel, text = _text(events.ABZEICHEN_VERLIEHEN)
    assert titel == "Neues Abzeichen: Wochenserie 2 (+2 weitere)"
    assert "Neue Abzeichen: Wochenserie 2, Tagesserie 7, Wochenserie 1" in text
    with translation.override("en"):
        titel, text = _text(events.ABZEICHEN_VERLIEHEN)
    assert titel == "New badge: Weekly streak 2 (+2 more)"
    assert "New badges: Weekly streak 2, Daily streak 7, Weekly streak 1" in text


def test_abzeichen_ohne_beschreibung_hinweis_englisch(anna, db):
    badge = AbzeichenDefinition.objects.get(schluessel="wochenserie-1")
    badge.beschreibung = ""
    badge.save()
    v = AbzeichenVerleihung.objects.create(kind=anna, abzeichen=badge, wert=1, schwelle=1)
    abzeichen._abzeichen_melden(anna, [v], True)
    with translation.override("en"):
        assert "New in your display case." in _text(events.ABZEICHEN_VERLIEHEN)[1]


def test_pause_ereignisse_im_empfaenger_text_und_datum(anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    pause = services.pause_setzen(
        anna, von=mama, ab=date(2026, 10, 28), bis=date(2026, 10, 30), jetzt=lok(2026, 10, 21, 9)
    )
    assert (
        _text(events.PAUSE_GESTARTET)[1]
        == "Pause vom 28.10.2026 bis 30.10.2026. Aufgaben zählen trotzdem."
    )
    with translation.override("en"):
        text = _text(events.PAUSE_GESTARTET)[1]
    assert text.startswith("Break from 10/28/2026 to 10/30/2026.")
    # ältere Ereignisse ohne msgid lesen den gespeicherten deutschen Text weiter
    Ereignis.objects.filter(typ_id=events.PAUSE_GESTARTET).update(
        daten={"zeitraum": "ab 01.01.2026"}
    )
    with translation.override("en"):
        assert "ab 01.01.2026" in _text(events.PAUSE_GESTARTET)[1]

    # geplante Pause löschen
    services.pause_loeschen(pause, von=mama, jetzt=lok(2026, 10, 21, 10))
    assert _text(events.PAUSE_BEENDET)[1] == "Die geplante Pause entfällt."
    with translation.override("en"):
        assert _text(events.PAUSE_BEENDET)[1] == "The planned break is cancelled."


def test_pause_ende_hinweis_englisch(anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    pause = services.pause_setzen(anna, von=mama, ab=date(2026, 10, 20), jetzt=lok(2026, 10, 21, 9))
    services.pause_beenden(pause, von=mama, bis=date(2026, 10, 25), jetzt=lok(2026, 10, 21, 10))
    assert _text(events.PAUSE_BEENDET)[1] == "Deine Pause endet am 25.10.2026."
    with translation.override("en"):
        assert _text(events.PAUSE_BEENDET)[1] == "Your break ends on 10/25/2026."


def test_datum_im_ereignis_folgt_der_sprache_nicht_dem_speicherzeitpunkt(anna, mama, uhr):
    """Die Ereignis-Daten enthalten beide Schreibweisen; der Text wählt die des Empfängers."""
    uhr.stellen(lok(2026, 10, 21, 9))
    with translation.override("en"):
        services.pause_setzen(anna, von=mama, ab=date(2026, 10, 28), jetzt=lok(2026, 10, 21, 9))
    assert _text(events.PAUSE_GESTARTET)[1].startswith("Pause ab 28.10.2026.")
    assert gettext("ab %(von)s") == "ab %(von)s"


def test_abzeichen_seite_zeigt_naechstes_englisch(eltern_client, anna):
    eltern_client.cookies["nestwerk_sprache"] = "en"
    html = eltern_client.get("/eltern/abzeichen/").content.decode()
    assert "Weekly streak 1" in html or "Daily streak 7" in html
    assert "Wochenserie 1 (" not in html
