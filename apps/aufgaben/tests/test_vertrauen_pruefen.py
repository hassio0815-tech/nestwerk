"""Vertrauen prüfen: "Passt", "Alle passen", "Nachbessern" (Punkte zurück, neue Runde mit
einmaliger Bestätigung), "Ablehnen"; Dashboard-Karte."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.aufgaben import events, services
from apps.aufgaben.models import AufgabenInstanz, InstanzStatus as S
from apps.aufgaben.tests.test_ablauf import (  # noqa: F401  (Fixtures)
    T0,
    aufgabe,
    ereignisse,
    frisch,
    instanz,
    instanz_von,
    reserviert,
)
from apps.kern.models import AuditEintrag
from apps.punkte import selectors as punkte_selectors

Saldo = punkte_selectors.Saldo


def erledigt(aufgabe, kind):
    i = reserviert(instanz_von(aufgabe(freigabeart="vertrauen")), kind)
    services.erledigt_melden(i, kind, jetzt=T0)
    return frisch(i)


def test_nur_ungepruefte_vertrauen_erledigungen_in_der_liste(aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    mit_bestaetigung = reserviert(instanz_von(aufgabe(freigabeart="eltern")), anna)
    services.erledigt_melden(mit_bestaetigung, anna, jetzt=T0)
    assert list(services.zu_pruefen()) == [a]


def test_passt_markiert_und_behaelt_punkte(aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    services.passt(a, von=mama)
    a = frisch(a)
    assert (a.status, a.geprueft_von) == (S.BESTAETIGT, mama) and a.geprueft_am
    assert punkte_selectors.salden(anna) == Saldo(guthaben=10, xp=10)
    assert list(services.zu_pruefen()) == []
    assert AuditEintrag.objects.filter(aktion="aufgabe.geprueft").count() == 1
    with pytest.raises(services.UngueltigerUebergang):
        services.passt(a, von=mama)


def test_alle_passen(aufgabe, anna, mama):
    erledigt(aufgabe, anna)
    erledigt(aufgabe, anna)
    assert services.alle_passen(von=mama) == 2
    assert list(services.zu_pruefen()) == []


def test_ablehnen_ist_korrektur(aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    with pytest.raises(services.AblaufFehler):
        services.korrigieren(a, von=mama, begruendung="")
    services.korrigieren(a, von=mama, begruendung="Nicht gemacht")
    assert frisch(a).status == S.STORNIERT
    assert punkte_selectors.salden(anna) == Saldo(guthaben=0, xp=0)
    assert list(services.zu_pruefen()) == []


def test_nachbessern_gleiche_instanz_punkte_zurueck_einmal_bestaetigen(aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    with pytest.raises(services.AblaufFehler):
        services.korrigieren(a, von=mama, begruendung=" ", nachbessern=True)
    services.korrigieren(a, von=mama, begruendung="Ecke fehlt noch", nachbessern=True, jetzt=T0)
    a = frisch(a)
    assert (a.status, a.kind, a.nachbessern_anzahl, a.nachbessern_grund) == (
        S.NACHBESSERN,
        anna,
        1,
        "Ecke fehlt noch",
    )
    assert a.nachbessern_bis == T0 + timedelta(hours=48)
    assert AufgabenInstanz.objects.count() == 1  # keine neue Instanz
    assert punkte_selectors.salden(anna) == Saldo(guthaben=0, xp=0)
    assert ereignisse(events.NACHBESSERN).get().daten["begruendung"] == "Ecke fehlt noch"
    assert AuditEintrag.objects.filter(aktion="aufgabe.nachbessern").count() == 1
    assert list(services.zu_pruefen()) == []

    # Trotz Vertrauen: Meldung wartet auf Bestätigung, keine Punkte
    services.erledigt_melden(a, anna, jetzt=T0 + timedelta(hours=1))
    assert frisch(a).status == S.GEMELDET
    assert punkte_selectors.salden(anna) == Saldo(guthaben=0, xp=0)
    services.bestaetigen(a, von=mama)
    assert frisch(a).status == S.BESTAETIGT
    assert punkte_selectors.salden(anna) == Saldo(guthaben=10, xp=10)  # neuer Buchungsschlüssel
    assert list(services.zu_pruefen()) == []  # von den Eltern bestätigt

    # zweite Runde funktioniert ebenfalls (Schlüssel :n2)
    services.korrigieren(a, von=mama, begruendung="Noch mal", nachbessern=True, jetzt=T0)
    assert punkte_selectors.salden(anna) == Saldo(guthaben=0, xp=0)
    assert frisch(a).nachbessern_anzahl == 2


def test_nachbessern_klappt_auch_wenn_naechste_runde_offen_ist(aufgabe, anna, mama):
    auf = aufgabe(freigabeart="vertrauen")
    a = reserviert(instanz_von(auf), anna)
    services.erledigt_melden(a, anna, jetzt=T0)
    weitere = instanz_von(auf, tag=date(2026, 10, 15))  # nächste Runde schon offen
    services.korrigieren(a, von=mama, begruendung="Nochmal", nachbessern=True, jetzt=T0)
    services.erledigt_melden(a, anna, jetzt=T0 + timedelta(hours=2))
    assert frisch(a).status == S.GEMELDET and frisch(weitere).status == S.OFFEN


def test_nachbessern_frist_abgelaufen(aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    services.korrigieren(a, von=mama, begruendung="Nochmal", nachbessern=True, jetzt=T0)
    assert services.nachbessern_pruefen(jetzt=T0 + timedelta(hours=47)) == {"nachbessern_abgelaufen": 0}
    with pytest.raises(services.UngueltigerUebergang, match="Frist"):
        services.erledigt_melden(a, anna, jetzt=T0 + timedelta(hours=49))
    assert services.nachbessern_pruefen(jetzt=T0 + timedelta(hours=49)) == {"nachbessern_abgelaufen": 1}
    assert frisch(a).status == S.STORNIERT
    assert punkte_selectors.salden(anna) == Saldo(guthaben=0, xp=0)
    assert ereignisse(events.NACHBESSERN_ABGELAUFEN).count() == 1
    assert services.nachbessern_pruefen(jetzt=T0 + timedelta(hours=50)) == {"nachbessern_abgelaufen": 0}


def test_dashboard_karte_und_aktionen(eltern_client, aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    html = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert 'id="pruefen"' in html and a.titel_snapshot in html
    antwort = eltern_client.post(
        reverse("aufgaben:pruefen_nachbessern", args=[a.pk]), {"begruendung": "Bitte nochmal"}
    )
    assert antwort.status_code == 302
    assert AufgabenInstanz.objects.filter(status=S.NACHBESSERN).count() == 1
    b = erledigt(aufgabe, anna)
    eltern_client.post(reverse("aufgaben:pruefen_passt", args=[b.pk]))
    assert frisch(b).geprueft_am


def test_kind_sieht_grund_auf_der_karte(kind_client, aufgabe, anna, mama):
    a = erledigt(aufgabe, anna)
    services.korrigieren(a, von=mama, begruendung="Ecke fehlt", nachbessern=True)
    html = kind_client.get(reverse("aufgaben:kind")).content.decode()
    assert "Bitte nachbessern: Ecke fehlt" in html
