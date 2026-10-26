"""Anmeldeseiten und Sitzungsdauer."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.kern.models import AuditEintrag
from apps.konten import selectors

from .conftest import FALSCHE_PIN, PASSWORT, eltern_anmelden, kind_anmelden

pytestmark = pytest.mark.django_db

TAG = 86400


def test_startseite_zeigt_avatar_kacheln_der_kinder(anna, ben, client):
    antwort = client.get(reverse("konten:start"))
    html = antwort.content.decode()
    assert antwort.status_code == 200
    assert "Anna" in html and "Ben" in html
    assert reverse("konten:kind_pin", args=[anna.pk]) in html
    assert 'data-akzent="pink"' in html  # Annas Akzentfarbe an der Kachel


def test_inaktive_kinder_stehen_nicht_auf_der_startseite(anna, ben, client):
    ben.aktiv = False
    ben.save()
    html = client.get(reverse("konten:start")).content.decode()
    assert "Ben" not in html
    assert client.get(reverse("konten:kind_pin", args=[ben.pk])).status_code == 404


def test_pin_seite_hat_pin_pad_und_kindfarbe(anna, client):
    html = client.get(reverse("konten:kind_pin", args=[anna.pk])).content.decode()
    assert "data-pin" in html and 'name="pin"' in html
    assert 'data-akzent="pink"' in html  # am <body>


def test_kind_login_erfolg(anna, client):
    antwort = kind_anmelden(client, anna)
    assert antwort.status_code == 302 and antwort.url == reverse("konten:kind_heim")
    assert client.session["_auth_user_id"] == str(anna.pk)
    html = client.get(antwort.url).content.decode()
    assert 'data-akzent="pink"' in html and "Hallo Anna" in html


def test_kind_login_falsche_pin(anna, client):
    antwort = kind_anmelden(client, anna, FALSCHE_PIN)
    assert antwort.status_code == 401
    assert "_auth_user_id" not in client.session


def test_kind_login_sperre_zeigt_meldung(anna, client, uhr):
    for _ in range(5):
        antwort = kind_anmelden(client, anna, FALSCHE_PIN)
    assert antwort.status_code == 429
    assert "5 Minuten" in antwort.content.decode()
    assert kind_anmelden(client, anna).status_code == 429  # auch die richtige PIN
    uhr.weiter(minutes=5, seconds=1)
    assert kind_anmelden(client, anna).status_code == 302


def test_sperre_wird_im_audit_protokolliert(anna, client, uhr):
    for _ in range(5):
        kind_anmelden(client, anna, FALSCHE_PIN)
    eintrag = AuditEintrag.objects.get(aktion="konten.pin_gesperrt")
    assert eintrag.kind == anna and eintrag.akteur_name == "Anna"


def test_gesperrtes_kind_ist_auf_der_startseite_markiert(anna, client, uhr):
    for _ in range(5):
        kind_anmelden(client, anna, FALSCHE_PIN)
    assert "gesperrt" in client.get(reverse("konten:start")).content.decode()
    assert selectors.gesperrte_kinder() == [anna]


def test_eltern_login_erfolg_mit_namen(mama, papa, client):
    seite = client.get(reverse("konten:eltern_login")).content.decode()
    assert "Mama" in seite and "Papa" in seite
    antwort = eltern_anmelden(client, papa)
    assert antwort.status_code == 302 and antwort.url == reverse("oberflaeche:module")
    assert client.session["_auth_user_id"] == str(papa.pk)


def test_eltern_login_falsches_passwort(mama, client):
    assert eltern_anmelden(client, mama, "falsch-falsch").status_code == 401
    assert "_auth_user_id" not in client.session


def test_eltern_login_ohne_gesetztes_passwort_nicht_moeglich(db, client):
    from apps.konten import services

    ohne = services.eltern_anlegen("Opa")
    assert eltern_anmelden(client, ohne, "irgendwas123").status_code == 401


def test_kind_kann_sich_nicht_als_eltern_anmelden(anna, mama, client):
    antwort = client.post(
        reverse("konten:eltern_login"), {"eltern": str(anna.pk), "passwort": PASSWORT}
    )
    assert antwort.status_code == 401


def test_eltern_login_mit_unsinn_als_id(mama, client):
    antwort = client.post(reverse("konten:eltern_login"), {"eltern": "kaputt", "passwort": "x"})
    assert antwort.status_code == 401


def test_eltern_sperre_ueber_http(mama, client, uhr):
    for _ in range(10):
        eltern_anmelden(client, mama, "falsch-falsch")
    antwort = eltern_anmelden(client, mama)
    assert antwort.status_code == 429 and "15 Minuten" in antwort.content.decode()
    uhr.weiter(minutes=16)
    assert eltern_anmelden(client, mama).status_code == 302


def test_sitzungsdauer_eltern_vertrautes_geraet_90_tage(mama, client):
    eltern_anmelden(client, mama, vertraut=True)
    assert abs(client.session.get_expiry_age() - 90 * TAG) < 5


def test_sitzungsdauer_eltern_ohne_vertrauen_12_stunden(mama, client):
    eltern_anmelden(client, mama)
    assert abs(client.session.get_expiry_age() - 12 * 3600) < 5


def test_kind_auf_persoenlichem_geraet_bleibt_365_tage(anna, iphone, client):
    from .conftest import client_fuer

    c = client_fuer(iphone)
    kind_anmelden(c, anna)
    assert abs(c.session.get_expiry_age() - 365 * TAG) < 5
    assert c.session["nestwerk_kiosk"] is False


def test_abmelden(anna, client):
    kind_anmelden(client, anna)
    antwort = client.post(reverse("konten:abmelden"))
    assert antwort.status_code == 302
    assert "_auth_user_id" not in client.session
    assert AuditEintrag.objects.filter(aktion="konten.abgemeldet", akteur=anna).exists()


def test_abmelden_nur_per_post(anna, client):
    kind_anmelden(client, anna)
    assert client.get(reverse("konten:abmelden")).status_code == 405
    assert "_auth_user_id" in client.session


def test_next_nur_auf_eigene_seiten(mama, client):
    antwort = client.post(
        reverse("konten:eltern_login"),
        {"eltern": str(mama.pk), "passwort": PASSWORT, "next": "https://boese.example/x"},
    )
    assert antwort.url == reverse("oberflaeche:module")
    c = Client()
    antwort = c.post(
        reverse("konten:eltern_login"),
        {"eltern": str(mama.pk), "passwort": PASSWORT, "next": "/eltern/geraete/"},
    )
    assert antwort.url == "/eltern/geraete/"


def test_login_cookie_wird_bei_neuer_anmeldung_getauscht(anna, client):
    client.get(reverse("konten:start"))
    kind_anmelden(client, anna)
    vorher = client.cookies["sessionid"].value
    client.post(reverse("konten:abmelden"))
    kind_anmelden(client, anna)
    assert client.cookies["sessionid"].value != vorher


def test_csrf_wird_erzwungen(anna):
    c = Client(enforce_csrf_checks=True)
    antwort = c.post(reverse("konten:kind_pin", args=[anna.pk]), {"pin": "4817"})
    assert antwort.status_code == 403


def test_seiten_ohne_externe_ressourcen(anna, mama, client):
    seiten = [
        client.get(reverse("konten:start")),
        client.get(reverse("konten:kind_pin", args=[anna.pk])),
        client.get(reverse("konten:eltern_login")),
    ]
    for s in seiten:
        html = s.content.decode()
        assert s.status_code == 200
        assert "http://" not in html and "https://" not in html


def test_passwortwechsel_beendet_andere_eltern_sitzungen(mama):
    """Regression B-05: Eltern haben kein eigenes Passwort; ohne Anpassung blieben alle
    Sitzungen (vertraute Geräte: 90 Tage) nach einem Wechsel des Familien-Passworts gültig."""
    from django.test import Client

    alt, neu = Client(), Client()
    eltern_anmelden(alt, mama)
    eltern_anmelden(neu, mama)
    assert alt.get(reverse("konten:geraete")).status_code == 200
    antwort = neu.post(
        reverse("oberflaeche:familie_passwort"),
        {"passwort": "ganz-neues-pw", "passwort2": "ganz-neues-pw"},
    )
    assert antwort.status_code == 302
    # die eigene Sitzung bleibt, die andere ist beendet
    assert neu.get(reverse("konten:geraete")).status_code == 200
    assert alt.get(reverse("konten:geraete")).status_code == 302
    assert "_auth_user_id" not in alt.session
    assert PASSWORT != "ganz-neues-pw"
