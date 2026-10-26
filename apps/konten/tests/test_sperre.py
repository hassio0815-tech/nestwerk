"""Rate-Limit und Sperre (O11): Kind je Konto mit Verdopplung, Eltern je IP."""

from datetime import timedelta

import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.kern import einstellungen
from apps.konten import selectors, services, sperre
from apps.konten.models import AnmeldeVersuch, KindProfil

from .conftest import FALSCHE_PIN, PASSWORT, PIN

pytestmark = pytest.mark.django_db


def versuche(kind, pin, anzahl):
    for _ in range(anzahl):
        authenticate(None, kind=kind, pin=pin)


def profil(kind):
    return KindProfil.objects.get(benutzer=kind)


def test_startwerte_stehen_in_der_db():
    assert einstellungen.wert("konten.kind_pin_fehlversuche") == 5
    assert einstellungen.wert("konten.kind_pin_sperre_minuten") == 5
    assert einstellungen.wert("konten.kind_pin_sperre_max_minuten") == 60
    assert einstellungen.wert("konten.eltern_fehlversuche") == 10
    assert einstellungen.wert("konten.eltern_sperre_minuten") == 15
    assert not [s for s in einstellungen.fehlende() if s.startswith("konten.")]


def test_vier_fehlversuche_sperren_noch_nicht(anna, uhr):
    versuche(anna, FALSCHE_PIN, 4)
    assert selectors.kind_gesperrt_bis(anna) is None
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_fuenf_fehlversuche_sperren_fuenf_minuten(anna, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    assert selectors.kind_gesperrt_bis(anna) == uhr.jetzt + timedelta(minutes=5)


def test_richtige_pin_waehrend_der_sperre_wird_abgelehnt(anna, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    assert authenticate(None, kind=anna, pin=PIN) is None
    uhr.weiter(minutes=4, seconds=59)
    assert authenticate(None, kind=anna, pin=PIN) is None
    uhr.weiter(seconds=2)
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_backend_wirft_bei_sperre_permission_denied(anna, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    from apps.konten.backends import KindBackend

    with pytest.raises(PermissionDenied):
        KindBackend().authenticate(None, kind=anna, pin=PIN)


def test_sperre_verdoppelt_sich_bis_zum_hoechstwert(anna, uhr):
    erwartet = [5, 10, 20, 40, 60, 60]
    for minuten in erwartet:
        versuche(anna, FALSCHE_PIN, 5)
        gesperrt = selectors.kind_gesperrt_bis(anna)
        assert gesperrt is not None
        assert (gesperrt - uhr.jetzt).total_seconds() == minuten * 60
        uhr.weiter(minutes=minuten, seconds=1)
    assert profil(anna).pin_sperrstufe == len(erwartet)


def test_versuche_waehrend_der_sperre_zaehlen_nicht_und_verlaengern_nicht(anna, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    bis = profil(anna).pin_gesperrt_bis
    versuche(anna, FALSCHE_PIN, 20)
    p = profil(anna)
    assert p.pin_gesperrt_bis == bis
    assert p.pin_sperrstufe == 1
    assert p.pin_fehlversuche == 0


def test_erfolg_setzt_alles_zurueck(anna, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    uhr.weiter(minutes=6)
    versuche(anna, FALSCHE_PIN, 3)
    assert authenticate(None, kind=anna, pin=PIN) == anna
    p = profil(anna)
    assert (p.pin_fehlversuche, p.pin_sperrstufe, p.pin_gesperrt_bis) == (0, 0, None)
    # nach dem Reset beginnt die Zählung wieder bei der ersten Stufe
    versuche(anna, FALSCHE_PIN, 5)
    assert (selectors.kind_gesperrt_bis(anna) - uhr.jetzt).total_seconds() == 300


def test_sperre_gilt_je_kind(anna, ben, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    assert selectors.kind_gesperrt_bis(anna) is not None
    assert selectors.kind_gesperrt_bis(ben) is None
    assert authenticate(None, kind=ben, pin=PIN) == ben


def test_sperre_steht_in_der_db_und_ueberlebt_neustart(anna, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    frisch = KindProfil.objects.get(benutzer_id=anna.pk)  # neue Instanz = neuer Prozess
    assert frisch.pin_gesperrt_bis == uhr.jetzt + timedelta(minutes=5)
    assert frisch.pin_sperrstufe == 1


def test_eltern_koennen_entsperren(anna, mama, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    assert selectors.gesperrte_kinder() == [anna]
    services.kind_entsperren(anna, von=mama)
    assert selectors.gesperrte_kinder() == []
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_pin_zuruecksetzen_hebt_sperre_auf(anna, mama, uhr):
    versuche(anna, FALSCHE_PIN, 5)
    services.pin_setzen(anna, "2468", von=mama)
    assert authenticate(None, kind=anna, pin="2468") == anna
    assert authenticate(None, kind=anna, pin=PIN) is None


@pytest.mark.parametrize("pin", ["123", "12345", "abcd", "12 4", ""])
def test_ungueltiges_pin_format_zaehlt_als_fehlversuch(anna, pin):
    assert authenticate(None, kind=anna, pin=pin) is None
    assert profil(anna).pin_fehlversuche == 1


def test_einstellungen_aendern_limit_und_dauer(anna, uhr):
    einstellungen.setzen("konten.kind_pin_fehlversuche", 2, akteur=None)
    einstellungen.setzen("konten.kind_pin_sperre_minuten", 1, akteur=None)
    versuche(anna, FALSCHE_PIN, 2)
    assert (selectors.kind_gesperrt_bis(anna) - uhr.jetzt).total_seconds() == 60


# --- Eltern: je IP --------------------------------------------------------------------------


def anfrage(ip):
    return RequestFactory().post("/anmelden/eltern/", REMOTE_ADDR=ip)


def eltern_versuche(mama, passwort, ip, anzahl):
    for _ in range(anzahl):
        authenticate(anfrage(ip), eltern=mama, passwort=passwort)


def test_zehn_fehlversuche_je_ip_sperren_fuenfzehn_minuten(mama, uhr):
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 9)
    assert sperre.eltern_gesperrt_bis("192.168.1.20", uhr.jetzt) is None
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 1)
    bis = sperre.eltern_gesperrt_bis("192.168.1.20", uhr.jetzt)
    assert (bis - uhr.jetzt).total_seconds() == 15 * 60
    # richtiges Passwort hilft während der Sperre nicht
    assert authenticate(anfrage("192.168.1.20"), eltern=mama, passwort=PASSWORT) is None
    # andere IP bleibt frei
    assert authenticate(anfrage("192.168.1.21"), eltern=mama, passwort=PASSWORT) == mama


def test_eltern_sperre_endet_und_verlaengert_sich_nicht_durch_versuche(mama, uhr):
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 10)
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 30)
    assert AnmeldeVersuch.objects.count() == 10  # gesperrte Versuche werden nicht gezählt
    uhr.weiter(minutes=15, seconds=1)
    assert authenticate(anfrage("192.168.1.20"), eltern=mama, passwort=PASSWORT) == mama


def test_eltern_erfolg_setzt_zaehler_zurueck(mama, uhr):
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 9)
    uhr.weiter(seconds=1)
    assert authenticate(anfrage("192.168.1.20"), eltern=mama, passwort=PASSWORT) == mama
    uhr.weiter(seconds=1)
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 9)
    assert sperre.eltern_gesperrt_bis("192.168.1.20", uhr.jetzt) is None


def test_eltern_fehlversuche_ausserhalb_des_fensters_zaehlen_nicht(mama, uhr):
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 9)
    uhr.weiter(minutes=16)
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 1)
    assert sperre.eltern_gesperrt_bis("192.168.1.20", uhr.jetzt) is None


def test_alte_anmeldeversuche_werden_nach_30_tagen_geloescht(mama, uhr):
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 3)
    uhr.weiter(days=31)
    eltern_versuche(mama, "falsch-falsch", "192.168.1.20", 1)
    assert services.alte_versuche_loeschen(uhr.jetzt) == 3
    assert AnmeldeVersuch.objects.count() == 1
