"""Heimnetz-Prüfung und Client-IP hinter dem Proxy (X-Forwarded-For nur von vertrauten Proxys)."""

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.kern import einstellungen
from apps.konten import netz
from apps.konten.models import AnmeldeVersuch

from .conftest import PIN, kind_anmelden

pytestmark = pytest.mark.django_db


def anfrage(remote, xff=None):
    extra = {"REMOTE_ADDR": remote}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    return RequestFactory().get("/", **extra)


@pytest.fixture
def npm(db):
    """Nur der NPM (192.168.1.5) ist vertrauter Proxy; Heimnetz = 192.168.1.0/24."""
    einstellungen.setzen("konten.vertraute_proxys", ["192.168.1.5/32"], akteur=None)
    einstellungen.setzen("konten.kind_netze_cidr", ["192.168.1.0/24"], akteur=None)


def test_ohne_proxy_gilt_die_direkte_adresse(npm):
    assert str(netz.client_ip(anfrage("192.168.1.77"))) == "192.168.1.77"


def test_xff_von_vertrautem_proxy_wird_ausgewertet(npm):
    assert str(netz.client_ip(anfrage("192.168.1.5", "192.168.1.40"))) == "192.168.1.40"


def test_xff_von_fremder_adresse_wird_ignoriert(npm):
    r = anfrage("203.0.113.9", "192.168.1.40")
    assert str(netz.client_ip(r)) == "203.0.113.9"
    assert not netz.kind_login_erlaubt(r)


def test_xff_von_anderem_lan_geraet_wird_ignoriert(npm):
    # Ein LAN-Gerät, das nicht der Proxy ist, kann sich keine Heimnetz-Adresse erfinden
    r = anfrage("192.168.1.99", "10.9.9.9")
    assert str(netz.client_ip(r)) == "192.168.1.99"


def test_gefaelschter_linker_xff_eintrag_hilft_nicht(npm):
    # Angreifer von außen schickt "192.168.1.40" mit; der NPM hängt die echte Adresse rechts an
    r = anfrage("192.168.1.5", "192.168.1.40, 203.0.113.9")
    assert str(netz.client_ip(r)) == "203.0.113.9"
    assert not netz.kind_login_erlaubt(r)


def test_nur_der_rechteste_eintrag_zaehlt_auch_bei_privaten_adressen(db):
    """Regression B-02: Startwert (alle privaten Netze vertraut) + privater Heimnetz-Client.
    Der Client kann links Adressen erfinden; zählen darf nur, was der Proxy angehängt hat."""
    r = anfrage("192.168.1.5", "203.0.113.77, 192.168.1.40")
    assert str(netz.client_ip(r)) == "192.168.1.40"
    r = anfrage("192.168.1.5", "10.0.0.1, 10.0.0.2, 192.168.1.41")
    assert str(netz.client_ip(r)) == "192.168.1.41"


def test_eltern_rate_limit_laesst_sich_nicht_per_xff_umgehen(db, client):
    """Regression B-02: Ein Kind im WLAN probiert das Eltern-Passwort mit wechselnden
    gefälschten X-Forwarded-For-Adressen; die Sperre greift trotzdem für seine echte IP."""
    from apps.konten import services

    services.eltern_passwort_setzen("richtig-geheim", von=None)
    mama = services.eltern_anlegen("Mama")
    limit = einstellungen.wert("konten.eltern_fehlversuche")
    for i in range(limit):
        client.post(
            reverse("konten:eltern_login"),
            {"eltern": str(mama.pk), "passwort": f"falsch{i}"},
            REMOTE_ADDR="192.168.1.5",
            HTTP_X_FORWARDED_FOR=f"10.66.0.{i}, 192.168.1.40",
        )
    antwort = client.post(
        reverse("konten:eltern_login"),
        {"eltern": str(mama.pk), "passwort": "richtig-geheim"},
        REMOTE_ADDR="192.168.1.5",
        HTTP_X_FORWARDED_FOR="10.66.1.1, 192.168.1.40",
    )
    assert antwort.status_code == 429
    assert set(AnmeldeVersuch.objects.values_list("ip", flat=True)) == {"192.168.1.40"}


def test_nur_vertraute_in_der_kette_nimmt_den_linkesten(npm):
    r = anfrage("192.168.1.5", "192.168.1.5")
    assert str(netz.client_ip(r)) == "192.168.1.5"


def test_leerer_oder_fehlender_xff_vom_proxy_faellt_auf_proxy_adresse_zurueck(npm):
    assert str(netz.client_ip(anfrage("192.168.1.5"))) == "192.168.1.5"
    assert str(netz.client_ip(anfrage("192.168.1.5", "  "))) == "192.168.1.5"


@pytest.mark.parametrize("xff", ["kein-ip", "192.168.1.40, murks", "999.1.1.1", "192.168.1.40,"])
def test_unlesbarer_xff_ergibt_unbekannt_und_kein_kinder_login(npm, xff):
    r = anfrage("192.168.1.5", xff)
    assert netz.client_ip(r) is None
    assert not netz.kind_login_erlaubt(r)


def test_unlesbare_remote_addr(npm):
    assert netz.client_ip(anfrage("")) is None
    assert not netz.kind_login_erlaubt(anfrage(""))


def test_heimnetz_innen_und_aussen(npm):
    assert netz.kind_login_erlaubt(anfrage("192.168.1.77"))
    assert not netz.kind_login_erlaubt(anfrage("192.168.2.77"))
    assert netz.kind_login_erlaubt(anfrage("192.168.1.5", "192.168.1.200"))


def test_leere_liste_schaltet_die_pruefung_aus(npm):
    einstellungen.setzen("konten.kind_netze_cidr", [], akteur=None)
    assert netz.kind_login_erlaubt(anfrage("203.0.113.9"))
    assert netz.kind_login_erlaubt(anfrage(""))


def test_ipv6_und_ipv4_gemappt(npm):
    einstellungen.setzen("konten.kind_netze_cidr", ["192.168.1.0/24", "fd00::/8"], akteur=None)
    assert netz.kind_login_erlaubt(anfrage("fd00::1234"))
    assert netz.kind_login_erlaubt(anfrage("::ffff:192.168.1.50"))
    assert not netz.kind_login_erlaubt(anfrage("2001:db8::1"))
    # IPv6-Adresse trifft nie ein IPv4-Netz
    einstellungen.setzen("konten.kind_netze_cidr", ["0.0.0.0/0"], akteur=None)
    assert not netz.kind_login_erlaubt(anfrage("2001:db8::1"))


def test_startwerte_sind_private_netze(db):
    assert netz.kind_login_erlaubt(anfrage("192.168.178.20"))
    assert netz.kind_login_erlaubt(anfrage("10.1.2.3"))
    assert not netz.kind_login_erlaubt(anfrage("8.8.8.8"))


def test_ungueltiges_netz_wird_abgelehnt(db):
    from apps.kern.einstellungen import UngueltigerWert

    with pytest.raises(UngueltigerWert):
        einstellungen.setzen("konten.kind_netze_cidr", ["kein netz"], akteur=None)
    with pytest.raises(UngueltigerWert):
        einstellungen.setzen("konten.vertraute_proxys", ["300.1.1.1/8"], akteur=None)


# --- über HTTP ------------------------------------------------------------------------------


def test_kind_login_von_aussen_wird_abgewiesen_und_nicht_gezaehlt(npm, anna, client):
    antwort = kind_anmelden(client, anna, PIN, REMOTE_ADDR="203.0.113.9")
    assert antwort.status_code == 403
    assert "_auth_user_id" not in client.session
    assert not AnmeldeVersuch.objects.exists()
    anna.kindprofil.refresh_from_db()
    assert anna.kindprofil.pin_fehlversuche == 0


def test_kind_login_ueber_proxy_aus_dem_heimnetz(npm, anna, client):
    antwort = kind_anmelden(
        client, anna, PIN, REMOTE_ADDR="192.168.1.5", HTTP_X_FORWARDED_FOR="192.168.1.40"
    )
    assert antwort.status_code == 302
    assert AnmeldeVersuch.objects.get().ip == "192.168.1.40"


def test_kind_login_ueber_proxy_von_aussen(npm, anna, client):
    antwort = kind_anmelden(
        client, anna, PIN, REMOTE_ADDR="192.168.1.5", HTTP_X_FORWARDED_FOR="203.0.113.9"
    )
    assert antwort.status_code == 403


def test_pin_seite_von_aussen_nicht_erreichbar(npm, anna, client):
    antwort = client.get(reverse("konten:kind_pin", args=[anna.pk]), REMOTE_ADDR="203.0.113.9")
    assert antwort.status_code == 403
