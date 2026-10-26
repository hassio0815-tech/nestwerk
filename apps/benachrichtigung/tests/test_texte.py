"""Texte und Deep-Links je Ereignistyp, Ruhezeit-Logik."""

from datetime import datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.benachrichtigung import ruhezeit, texte


def ereignis(typ="x.y", daten=None, kind=None, akteur=None):
    return SimpleNamespace(
        typ_id=typ,
        daten=daten or {},
        kind_id=1 if kind else None,
        kind=SimpleNamespace(anzeigename=kind) if kind else None,
        akteur_id=1 if akteur else None,
        akteur=SimpleNamespace(anzeigename=akteur) if akteur else None,
    )


def test_text_mit_platzhaltern():
    with texte.isoliert():
        texte.text_registrieren("x.y", titel="{kind} fertig", text="„{aufgabe}“ von {akteur}")
        titel, text = texte.rendern(
            ereignis(daten={"aufgabe": "Müll"}, kind="Anna", akteur="Mama"), "Bezeichnung"
        )
    assert (titel, text) == ("Anna fertig", "„Müll“ von Mama")


def test_rueckfall_bei_fehlendem_platzhalter():
    with texte.isoliert():
        texte.text_registrieren("x.y", titel="{kind} fertig", text="{aufgabe}")
        titel, text = texte.rendern(ereignis(kind="Anna", daten={"text": "Info"}), "Bezeichnung")
    assert (titel, text) == ("Bezeichnung", "Info")
    assert texte.rendern(ereignis("ohne.text"), "Bez") == ("Bez", "")


def test_standardtext_aus_dem_katalog_und_ueberschreiben():
    titel, _ = texte.rendern(
        ereignis("aufgabe.gemeldet", {"aufgabe": "Müll"}, kind="Ben"), "Bezeichnung"
    )
    assert titel == "Ben hat eine Aufgabe gemeldet"
    with texte.isoliert():
        texte.text_registrieren("aufgabe.gemeldet", titel="Neu: {kind}")
        assert texte.rendern(ereignis("aufgabe.gemeldet", kind="Ben"), "B")[0] == "Neu: Ben"
        with pytest.raises(ImproperlyConfigured):
            texte.text_registrieren("aufgabe.gemeldet", titel="doppelt")


def test_kuerzen_auf_spaltenlaenge():
    with texte.isoliert():
        texte.text_registrieren("x.y", titel="T" * 300, text="X" * 900)
        titel, text = texte.rendern(ereignis(), "B")
    assert len(titel) == texte.TITEL_MAX and len(text) == texte.TEXT_MAX and titel.endswith("…")


def test_deep_link():
    e = ereignis(daten={"instanz": 5}, kind="Anna")
    assert texte.link_fuer(e, "/eltern/meldung/{instanz}/") == "/eltern/meldung/5/"
    assert texte.link_fuer(e, "/kind/{kind_id}/") == "/kind/1/"
    assert texte.link_fuer(e, "/eltern/{fehlt}/") == ""  # Platzhalter fehlt: kein Link
    assert texte.link_fuer(e, "") == ""
    assert texte.link_fuer(e, "https://boese.example/{instanz}") == ""  # nur interne Pfade


BERLIN = ZoneInfo("Europe/Berlin")


def fenster(von, bis, tage=127, aktiv=True):
    return SimpleNamespace(von=von, bis=bis, wochentage=tage, aktiv=aktiv)


@pytest.mark.parametrize(
    ("von", "bis", "stunde", "erwartet"),
    [
        (time(9), time(17), 12, True),
        (time(9), time(17), 17, False),  # Ende ist exklusiv
        (time(9), time(17), 8, False),
        (time(21), time(7), 23, True),
        (time(21), time(7), 3, True),
        (time(21), time(7), 12, False),
        (time(8), time(8), 3, True),  # von == bis: ganzer Tag
    ],
)
def test_fenster_aktiv(von, bis, stunde, erwartet):
    moment = datetime(2026, 10, 21, stunde, 0, tzinfo=BERLIN)  # Mittwoch
    assert ruhezeit.fenster_aktiv(fenster(von, bis), moment) is erwartet


def test_wochentage_bitmaske():
    assert ruhezeit.tage_liste(0b1010101) == [0, 2, 4, 6]
    nur_mittwoch = fenster(time(9), time(17), tage=1 << 2)
    assert ruhezeit.fenster_aktiv(nur_mittwoch, datetime(2026, 10, 21, 12, tzinfo=BERLIN))
    assert not ruhezeit.fenster_aktiv(nur_mittwoch, datetime(2026, 10, 22, 12, tzinfo=BERLIN))


@pytest.mark.parametrize(
    "link,ok",
    [
        ("/eltern/meldungen/#instanz-3", True),
        ("/", True),
        ("//boese.example/x", False),
        ("/\\boese.example", False),
        ("/a\\b", False),
        ("https://boese.example/", False),
        ("/a\nb", False),
        ("", False),
    ],
)
def test_nur_interne_pfade(link, ok):
    """Regression B-12: '/\\host' leitet Browser wie '//host' auf fremde Hosts."""
    from apps.benachrichtigung import texte

    assert texte.ist_interner_pfad(link) is ok
