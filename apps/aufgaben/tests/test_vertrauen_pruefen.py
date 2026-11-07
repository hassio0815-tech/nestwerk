"""Vertrauen prüfen: "Passt", "Alle passen", "Nachbessern" (Punkte zurück, neue Runde mit
einmaliger Bestätigung), "Ablehnen"; Dashboard-Karte."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.aufgaben import events, services
from apps.aufgaben.models import AufgabenInstanz
from apps.aufgaben.models import InstanzStatus as S
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
    assert services.nachbessern_pruefen(jetzt=T0 + timedelta(hours=47)) == {
        "nachbessern_abgelaufen": 0
    }
    with pytest.raises(services.UngueltigerUebergang, match="Frist"):
        services.erledigt_melden(a, anna, jetzt=T0 + timedelta(hours=49))
    assert services.nachbessern_pruefen(jetzt=T0 + timedelta(hours=49)) == {
        "nachbessern_abgelaufen": 1
    }
    assert frisch(a).status == S.STORNIERT
    assert punkte_selectors.salden(anna) == Saldo(guthaben=0, xp=0)
    assert ereignisse(events.NACHBESSERN_ABGELAUFEN).count() == 1
    assert services.nachbessern_pruefen(jetzt=T0 + timedelta(hours=50)) == {
        "nachbessern_abgelaufen": 0
    }


def test_dashboard_karte_und_aktionen(eltern_client, aufgabe, anna, mama):
    from apps.kern import zeit

    def erledigt(aufgabe, kind):  # heute, damit die Kachel "Heute erledigt" sie zeigt
        i = reserviert(instanz_von(aufgabe(freigabeart="vertrauen")), kind)
        services.erledigt_melden(i, kind, jetzt=zeit.jetzt())
        return frisch(i)

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


# --- Kachel "Heute erledigt" ------------------------------------------------------------------


def _melden(aufgabe, kind, art, jetzt, mama=None):
    i = reserviert(instanz_von(aufgabe(freigabeart=art)), kind)
    services.erledigt_melden(i, kind, jetzt=jetzt)
    if art != "vertrauen":
        services.bestaetigen(i, von=mama, jetzt=jetzt)
    return frisch(i)


def test_heute_erledigt_alle_freigabearten_neueste_zuerst(aufgabe, anna, mama):
    a = _melden(aufgabe, anna, "vertrauen", T0)
    b = _melden(aufgabe, anna, "eltern", T0 + timedelta(hours=1), mama)
    assert list(services.heute_erledigt(jetzt=T0 + timedelta(hours=2))) == [b, a]


def test_heute_erledigt_schliesst_unbestaetigt_und_andere_tage_aus(aufgabe, anna, mama):
    _melden(aufgabe, anna, "vertrauen", T0 - timedelta(days=1))
    offen = reserviert(instanz_von(aufgabe(freigabeart="eltern")), anna)
    services.erledigt_melden(offen, anna, jetzt=T0)  # GEMELDET, nicht bestätigt
    abgelehnt = _melden(aufgabe, anna, "vertrauen", T0)
    services.korrigieren(abgelehnt, von=mama, begruendung="nein")
    assert list(services.heute_erledigt(jetzt=T0)) == []


def test_heute_erledigt_tagesgrenze_in_familienzeitzone(aufgabe, anna, mama):
    from apps.kern import zeit

    beginn, ende = zeit.tag_intervall(zeit.heute(T0))
    knapp_davor = _melden(aufgabe, anna, "vertrauen", beginn - timedelta(minutes=1))
    erste = _melden(aufgabe, anna, "vertrauen", beginn)
    letzte = _melden(aufgabe, anna, "vertrauen", ende - timedelta(minutes=1))
    _melden(aufgabe, anna, "vertrauen", ende)
    assert knapp_davor not in services.heute_erledigt(jetzt=T0)
    assert list(services.heute_erledigt(jetzt=T0)) == [letzte, erste]


def test_heute_erledigt_kachel_kontext_begrenzt(aufgabe, anna, mama):
    for n in range(10):
        _melden(aufgabe, anna, "eltern", T0 + timedelta(minutes=n), mama)
    k = services.heute_erledigt_kachel(jetzt=T0 + timedelta(hours=1))
    assert (len(k["liste"]), k["gesamt"], k["weitere"], k["offen"]) == (8, 10, 2, 0)
    assert not any(i.zu_pruefen for i in k["liste"])


def test_ungepruefte_vertrauen_zeile_bleibt_ueber_dem_limit_sichtbar(aufgabe, anna, mama):
    aelteste = _melden(aufgabe, anna, "vertrauen", T0)
    for n in range(1, 10):
        _melden(aufgabe, anna, "eltern", T0 + timedelta(minutes=n), mama)
    k = services.heute_erledigt_kachel(jetzt=T0 + timedelta(hours=1))
    assert aelteste in k["liste"]
    assert [i.zu_pruefen for i in k["liste"] if i.pk == aelteste.pk] == [True]
    assert (len(k["liste"]), k["gesamt"], k["weitere"], k["offen"]) == (9, 10, 1, 1)


def test_heute_erledigt_abfragen_unabhaengig_von_anzahl(
    aufgabe, anna, mama, django_assert_max_num_queries
):
    for n in range(5):
        _melden(aufgabe, anna, "vertrauen", T0 + timedelta(minutes=n))
    with django_assert_max_num_queries(3):
        k = services.heute_erledigt_kachel(jetzt=T0 + timedelta(hours=1))
        [(i.kind.anzeigename, i.zu_pruefen) for i in k["liste"]]


def test_kachel_zeigt_knoepfe_nur_fuer_ungeprueftes_vertrauen(eltern_client, aufgabe, anna, mama):
    from apps.kern import zeit

    jetzt = zeit.jetzt()
    v = _melden(aufgabe, anna, "vertrauen", jetzt)
    e = _melden(aufgabe, anna, "eltern", jetzt, mama)
    html = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert "Heute erledigt" in html or "Done today" in html
    assert reverse("aufgaben:pruefen_passt", args=[v.pk]) in html
    assert reverse("aufgaben:pruefen_passt", args=[e.pk]) not in html
    assert f'id="erledigt-{e.pk}"' in html
    eltern_client.post(reverse("aufgaben:pruefen_passt", args=[v.pk]))
    html = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert reverse("aufgaben:pruefen_passt", args=[v.pk]) not in html
    assert f'id="erledigt-{v.pk}"' in html  # bleibt als Info sichtbar


def test_kachel_leer_zeigt_hinweis(eltern_client, mama):
    html = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert 'id="pruefen"' in html
    assert "Heute noch nichts erledigt." in html or "Nothing done yet today." in html
