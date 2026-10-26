"""Querschnitt aufgaben -> spielregeln (AP20): Bestätigung erfasst die Aktivität mit Meldedatum
(K1), Korrektur storniert sie; ein Fehler im Nachführen kippt die Bestätigung nicht."""

from datetime import date

from apps.aufgaben import services as aufgaben
from apps.aufgaben import wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz
from apps.spielregeln import services
from apps.spielregeln.models import Aktivitaet, KindStand, Wochenauswertung
from apps.spielregeln.tests.conftest import lok


def _instanz(mama, freigabeart="eltern"):
    aufgabe = Aufgabe.objects.create(
        titel="Müll",
        punkte=10,
        erstellt_von=mama,
        wiederholungsart=wiederholung.EINMALIG,
        freigabeart=freigabeart,
    )
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        titel_snapshot=aufgabe.titel,
        punkte_snapshot=aufgabe.punkte,
        freigabeart_snapshot=aufgabe.freigabeart,
    )


def test_bestaetigung_erfasst_aktivitaet_mit_meldedatum_korrektur_storniert(anna, mama, uhr):
    instanz = _instanz(mama)
    gemeldet = uhr.stellen(lok(2026, 10, 25, 19))  # Sonntag
    aufgaben.interesse_zeigen(instanz, anna, jetzt=gemeldet)
    aufgaben.erledigt_melden(instanz, anna, jetzt=gemeldet)
    bestaetigt = uhr.stellen(lok(2026, 10, 26, 18))  # Montag, im Puffer
    aufgaben.bestaetigen(instanz, von=mama, jetzt=bestaetigt)
    a = Aktivitaet.objects.get()
    assert (a.kind, a.datum, a.modul, a.referenz) == (
        anna,
        date(2026, 10, 25),
        "aufgaben",
        str(instanz.pk),
    )
    assert Wochenauswertung.objects.get(kind=anna).aktiv  # Woche 43 gerettet (K1)

    uhr.stellen(lok(2026, 10, 28, 9))
    aufgaben.korrigieren(instanz, von=mama, begruendung="doch nicht")
    a.refresh_from_db()
    assert a.storniert
    assert not Wochenauswertung.objects.get(kind=anna).aktiv
    assert services.neu_berechnen() == []


def test_vertrauen_erfasst_sofort(anna, mama, uhr):
    instanz = _instanz(mama, freigabeart="vertrauen")
    jetzt = uhr.stellen(lok(2026, 10, 21, 17))
    aufgaben.interesse_zeigen(instanz, anna, jetzt=jetzt)
    aufgaben.erledigt_melden(instanz, anna, jetzt=jetzt)
    assert Aktivitaet.objects.get().datum == date(2026, 10, 21)
    assert KindStand.objects.get(kind=anna).tagesserie == 1


def test_fehler_im_nachfuehren_kippt_bestaetigung_nicht(anna, mama, uhr, monkeypatch):
    def kaputt(*args, **kwargs):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(services, "kind_auswerten", kaputt)
    instanz = _instanz(mama, freigabeart="vertrauen")
    jetzt = uhr.stellen(lok(2026, 10, 21, 17))
    aufgaben.interesse_zeigen(instanz, anna, jetzt=jetzt)
    aufgaben.erledigt_melden(instanz, anna, jetzt=jetzt)
    assert Aktivitaet.objects.count() == 1


def test_spaete_bestaetigung_punkte_und_aktivitaet_in_derselben_woche(anna, mama, uhr):
    """Review AP31 (AP21 Bezugswoche nach Puffer): Meldung So, Bestätigung erst Mi (Woche schon
    abgeschlossen) -> Aktivität UND Punkte (Basis, Serienbonus, Sonderpunkte) zählen für den
    Tag der Bestätigung, nicht für die abgeschlossene Woche."""
    from apps.punkte import selectors as punkte

    instanz = _instanz(mama)
    gemeldet = uhr.stellen(lok(2026, 10, 25, 19))  # Sonntag KW 43
    aufgaben.interesse_zeigen(instanz, anna, jetzt=gemeldet)
    aufgaben.erledigt_melden(instanz, anna, jetzt=gemeldet)
    bestaetigt = uhr.stellen(lok(2026, 10, 28, 18))  # Mittwoch KW 44, Puffer vorbei
    aufgaben.bestaetigen(instanz, von=mama, sonderpunkte=2, begruendung="super", jetzt=bestaetigt)
    assert Aktivitaet.objects.get().datum == date(2026, 10, 28)
    daten = {b.art: b.bezugsdatum for b in punkte.buchungen(anna)}
    assert set(daten.values()) == {date(2026, 10, 28)}
    assert punkte.xp_zeitraum(date(2026, 10, 19), date(2026, 10, 25), kind=anna) == 0
