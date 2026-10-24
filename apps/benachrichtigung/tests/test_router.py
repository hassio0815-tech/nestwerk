"""Router: Matrix Präferenz x Ruhezeit x Kanal, Liste, Idempotenz, Profil, Kinder."""

from datetime import date, time

import pytest

from apps.benachrichtigung import router, services
from apps.benachrichtigung.models import Benachrichtigung, Popup, ZustellStatus, Zustellung
from apps.ereignisse import worker
from apps.ereignisse.models import Ereignis

from .conftest import (
    TYP_ENTSCHEIDUNG,
    TYP_INFO,
    TYP_INTERN,
    TYP_KIND,
    TYP_LISTE,
    veroeffentlichen,
)

pytestmark = pytest.mark.django_db

FREITAG = date(2026, 10, 23)
OFFEN = ZustellStatus.OFFEN
RUHE = ZustellStatus.UNTERDRUECKT_RUHEZEIT
AUS = ZustellStatus.UNTERDRUECKT_PRAEFERENZ


def status_von(benutzer, ereignis, kanal):
    return Zustellung.objects.get(
        benachrichtigung__empfaenger=benutzer, benachrichtigung__ereignis=ereignis, kanal_id=kanal
    ).status


# Präferenz: None = Standard (an), True/False = ausdrücklich; Ruhezeit: ohne / aktiv zur Zeit /
# aktiv, aber andere Uhrzeit; E-Mail-Pause an/aus.
@pytest.mark.parametrize("kanal", ["push", "email"])
@pytest.mark.parametrize("praeferenz", [None, True, False])
@pytest.mark.parametrize("ruhe", ["keine", "jetzt", "spaeter"])
@pytest.mark.parametrize("email_pause", [False, True])
def test_matrix_praeferenz_ruhezeit_kanal(
    katalog, mama, papa, uhr, kanal, praeferenz, ruhe, email_pause
):
    uhr.lokal(FREITAG, 22, 30)
    if ruhe == "jetzt":
        services.ruhezeit_setzen(mama, von=time(21), bis=time(7), gilt_fuer_email=email_pause)
    elif ruhe == "spaeter":
        services.ruhezeit_setzen(mama, von=time(23), bis=time(7), gilt_fuer_email=email_pause)
    if praeferenz is not None:
        services.praeferenz_setzen(mama, TYP_INFO, kanal, praeferenz)

    e = veroeffentlichen(TYP_INFO)
    router.router(e)

    if praeferenz is False:
        erwartet = AUS
    elif ruhe == "jetzt" and (kanal == "push" or email_pause):
        erwartet = RUHE
    else:
        erwartet = OFFEN
    assert status_von(mama, e, kanal) == erwartet
    # Papa hat nichts eingestellt: Standard, keine Ruhezeit
    assert status_von(papa, e, kanal) == OFFEN
    # Die Liste hat immer genau einen Eintrag je Elternteil
    assert Benachrichtigung.objects.filter(ereignis=e).count() == 2


def test_standard_ohne_praeferenz_zeile_gilt_standard_kanaele(katalog, mama, papa):
    e = veroeffentlichen(TYP_LISTE)  # standard_kanaele leer
    router.router(e)
    assert status_von(mama, e, "push") == AUS
    assert status_von(mama, e, "email") == AUS
    # Eintrag in der Liste trotzdem da
    assert Benachrichtigung.objects.filter(empfaenger=mama, ereignis=e).exists()


def test_praeferenz_kann_kanal_bei_leerem_standard_einschalten(katalog, mama):
    services.praeferenz_setzen(mama, TYP_LISTE, "email", True)
    e = veroeffentlichen(TYP_LISTE)
    router.router(e)
    assert status_von(mama, e, "email") == OFFEN
    assert status_von(mama, e, "push") == AUS


def test_ruhezeit_nach_mitternacht_und_wochentag(katalog, mama, uhr):
    # Fenster Fr 22:00 bis 07:00 nur freitags; Samstag 03:00 liegt noch im Freitags-Fenster
    services.ruhezeit_setzen(mama, von=time(22), bis=time(7), wochentage=1 << 4)
    samstag = date(2026, 10, 24)
    for tag, stunde, erwartet in [
        (FREITAG, 21, OFFEN),
        (FREITAG, 23, RUHE),
        (samstag, 3, RUHE),
        (samstag, 8, OFFEN),
        (samstag, 23, OFFEN),  # Samstag selbst hat kein Fenster
    ]:
        uhr.lokal(tag, stunde)
        e = veroeffentlichen(TYP_INFO)
        router.router(e)
        assert status_von(mama, e, "push") == erwartet, (tag, stunde)


def test_inaktive_ruhezeit_wirkt_nicht(katalog, mama, uhr):
    uhr.lokal(FREITAG, 23)
    services.ruhezeit_setzen(mama, von=time(21), bis=time(7), aktiv=False)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    assert status_von(mama, e, "push") == OFFEN


def test_ruhezeit_betrifft_nur_die_eigene_person(katalog, mama, papa, uhr):
    uhr.lokal(FREITAG, 23)
    services.ruhezeit_setzen(mama, von=time(21), bis=time(7))
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    assert status_von(mama, e, "push") == RUHE
    assert status_von(papa, e, "push") == OFFEN


def test_profil_mail_nur_bei_entscheidungen(katalog, mama, papa):
    services.mail_profil_setzen(mama, True)
    info = veroeffentlichen(TYP_INFO)
    entscheidung = veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"instanz": 7})
    router.router(info)
    router.router(entscheidung)
    assert status_von(mama, info, "email") == AUS
    assert status_von(mama, entscheidung, "email") == OFFEN
    assert status_von(mama, info, "push") == OFFEN  # Push bleibt unberührt
    assert status_von(papa, info, "email") == OFFEN  # Profil gilt je Elternteil


def test_katalogtyp_ohne_flag_zaehlt_als_entscheidung(katalog, mama):
    from apps.ereignisse import registry as ereignisse

    # Seit AP27 deklariert sondertag den Typ selbst (mit Flag); hier ohne Flag neu (``katalog``
    # stellt die Registry danach wieder her)
    ereignisse.typ_verzeichnis._eintraege.pop("sondertag.wunsch", None)
    ereignisse.typ_deklarieren(
        "sondertag.wunsch",
        modul="sondertag",
        bezeichnung="Antrag",
        zielgruppe="eltern",
        standard_kanaele=["email"],
    )
    from apps.ereignisse import services as ereignis_services

    ereignis_services.typen_synchronisieren()
    services.mail_profil_setzen(mama, True)
    e = veroeffentlichen("sondertag.wunsch")
    router.router(e)
    assert status_von(mama, e, "email") == OFFEN


def test_router_ist_idempotent(katalog, mama, papa):
    e = veroeffentlichen(TYP_INFO)
    assert router.router(e) > 0
    vorher = (Benachrichtigung.objects.count(), Zustellung.objects.count())
    assert router.router(e) == 0
    assert router.router(e) == 0
    assert (Benachrichtigung.objects.count(), Zustellung.objects.count()) == vorher
    # je Empfänger und Kanal genau eine Zustellung (Eltern: push + email)
    assert vorher == (2, 4)


def test_ueber_den_worker_genau_einmal(katalog, mama, papa):
    e = veroeffentlichen(TYP_INFO)
    worker.runde()
    worker.runde()
    # zweiter Worker-Lauf desselben Ereignisses (z. B. manuelles Neu-Einplanen)
    from apps.ereignisse.models import EreignisVerarbeitung

    EreignisVerarbeitung.objects.filter(ereignis=e).update(status="offen", versuche=0)
    worker.runde()
    assert Benachrichtigung.objects.filter(ereignis=e).count() == 2
    assert Zustellung.objects.filter(benachrichtigung__ereignis=e).count() == 4


def test_interner_typ_und_inaktiver_typ_erzeugen_nichts(katalog, mama):
    router.router(veroeffentlichen(TYP_INTERN))
    from apps.ereignisse.models import EreignisTyp

    EreignisTyp.objects.filter(pk=TYP_INFO).update(aktiv=False)
    router.router(veroeffentlichen(TYP_INFO))
    assert not Benachrichtigung.objects.exists()


def test_kind_bekommt_nur_push_und_popup(katalog, mama, anna):
    from apps.benachrichtigung import texte

    with texte.isoliert():
        texte.text_registrieren(
            TYP_KIND, titel="Aufgabe bestätigt!", text="„{aufgabe}“ ist geschafft."
        )
        _kind_pruefen(mama, anna)


def _kind_pruefen(mama, anna):
    e = veroeffentlichen(TYP_KIND, kind=anna, daten={"aufgabe": "Müll"})
    router.router(e)
    kanaele = set(
        Zustellung.objects.filter(benachrichtigung__empfaenger=anna).values_list(
            "kanal_id", flat=True
        )
    )
    assert kanaele == {"push", "popup"}
    assert status_von(anna, e, "popup") == OFFEN
    # Eltern bekommen die Kind-Meldung nicht
    assert not Benachrichtigung.objects.filter(empfaenger=mama).exists()
    eintrag = Benachrichtigung.objects.get(empfaenger=anna)
    assert eintrag.titel == "Aufgabe bestätigt!" and "Müll" in eintrag.text
    assert eintrag.link == "/kind/"


def test_kind_praeferenz_setzen_die_eltern(katalog, mama, anna):
    services.praeferenz_setzen(anna, TYP_KIND, "popup", False)
    e = veroeffentlichen(TYP_KIND, kind=anna)
    router.router(e)
    assert status_von(anna, e, "popup") == AUS
    assert status_von(anna, e, "push") == OFFEN
    assert not Popup.objects.exists()


def test_kind_ereignis_ohne_kind_erzeugt_keine_benachrichtigung(katalog, mama):
    router.router(veroeffentlichen(TYP_KIND))
    assert not Benachrichtigung.objects.exists()


def test_ruhezeit_nur_fuer_eltern(katalog, anna):
    with pytest.raises(ValueError):
        services.ruhezeit_setzen(anna, von=time(21), bis=time(7))


def test_globaler_kanal_aus_erzeugt_keine_zustellung(katalog, mama):
    from apps.benachrichtigung.models import Kanal

    router.kanaele_synchronisieren()
    Kanal.objects.filter(slug="email").update(aktiv=False)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    assert not Zustellung.objects.filter(kanal_id="email").exists()
    assert Zustellung.objects.filter(kanal_id="push").exists()


def test_ereignis_kind_und_akteur_werden_gespeichert(katalog, mama, anna):
    e = veroeffentlichen(TYP_KIND, kind=anna, akteur=mama)
    e.refresh_from_db()
    assert e.kind_id == anna.pk and e.akteur_id == mama.pk
    assert Ereignis.objects.filter(kind=anna).count() == 1
