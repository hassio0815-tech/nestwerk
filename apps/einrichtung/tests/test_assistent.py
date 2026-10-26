import datetime

import pytest
from django.core import mail

from apps.kern import einstellungen
from apps.kern.models import AuditEintrag
from apps.konten import selectors

from .conftest import ELTERN, KINDER, NETZ, SMTP, ZEIT, url


def _bis_schritt7(c, smtp=True):
    assert c.post(url(1), {"app_name": "Nestwerk Zuhause"}).status_code == 302
    assert c.post(url(2), ELTERN).status_code == 302
    assert c.post(url(3), KINDER).status_code == 302
    if smtp:
        assert c.post(url(4), {**SMTP, "aktion": "weiter"}).status_code == 302
    else:
        assert c.post(url(4), {"aktion": "ueberspringen"}).status_code == 302
    assert c.post(url(5), NETZ).status_code == 302
    zeit = {**ZEIT, "go_live_datum": datetime.date.today().isoformat()}
    assert c.post(url(6), zeit).status_code == 302


def _startwerte_posten(c):
    from apps.einrichtung import uebersicht

    daten = {}
    for _t, _m, felder in uebersicht.felder():
        for f in felder:
            if f["art"] == "bool":
                if f["angehakt"]:
                    daten[f["name"]] = "on"
            else:
                daten[f["name"]] = f["wert"]
    return c.post(url(7), daten)


def test_leere_installation_leitet_um(c):
    r = c.get("/")
    assert r.status_code == 302 and r["Location"] == "/einrichtung/"
    assert c.get("/gesundheit/").status_code == 200
    assert c.get("/einrichtung/", follow=True).status_code == 200


def test_htmx_umleitung(c):
    r = c.get("/kind/", HTTP_HX_REQUEST="true")
    assert r["HX-Redirect"] == "/einrichtung/"


def test_nur_heimnetz(c):
    r = c.get("/einrichtung/", REMOTE_ADDR="8.8.8.8")
    assert r.status_code == 403
    assert c.get("/", REMOTE_ADDR="8.8.8.8").status_code == 403


def test_setup_token(c, monkeypatch):
    monkeypatch.setenv("NESTWERK_SETUP_TOKEN", "abc123")
    r = c.get(url(1))
    assert r.status_code == 302 and r["Location"].endswith("/einrichtung/token/")
    assert c.post("/einrichtung/token/", {"token": "falsch"}).status_code == 200
    assert c.get(url(1)).status_code == 302
    assert c.post("/einrichtung/token/", {"token": "abc123"}).status_code == 302
    assert c.get(url(1)).status_code == 200


def test_schritte_nicht_ueberspringbar(c):
    r = c.get(url(5))
    assert r.status_code == 302 and r["Location"] == url(1)


def test_validierung_schritt2(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    r = c.post(url(2), {**ELTERN, "passwort2": "anders"})
    assert r.status_code == 200 and "nicht gleich" in r.content.decode()
    r = c.post(url(2), {**ELTERN, "passwort": "12345678", "passwort2": "12345678"})
    assert "Zu schwach" in r.content.decode()
    r = c.post(url(2), {**ELTERN, "eltern2_rolle": "mama"})
    assert "nur je einmal" in r.content.decode()
    assert not selectors.aktive_eltern().exists()


def test_validierung_kinder_und_zurueck(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    c.post(url(2), ELTERN)
    r = c.post(url(3), {**KINDER, "kind-1-pin2": "0000"})
    html = r.content.decode()
    assert r.status_code == 200 and "nicht gleich" in html
    assert "1357" not in html and "2468" not in html
    assert not selectors.aktive_kinder().exists()  # alles oder nichts
    r = c.post(url(3), {"anzahl": "3"})
    assert "mindestens ein Kind" in r.content.decode()
    # Zurück zu Schritt 2 zeigt gespeicherte Namen, nie das Passwort
    html = c.get(url(2)).content.decode()
    assert "Anna" in html and "Sommer-Wiese-42" not in html


def test_mehr_zeilen(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    c.post(url(2), ELTERN)
    r = c.post(url(3), {**KINDER, "aktion": "mehr"})
    assert 'name="kind-3-name"' in r.content.decode()


def test_validierung_netz_zeit(c):
    _bis = {"app_name": "Nestwerk"}
    c.post(url(1), _bis)
    c.post(url(2), ELTERN)
    c.post(url(3), KINDER)
    c.post(url(4), {"aktion": "ueberspringen"})
    r = c.post(url(5), {**NETZ, "proxys": "0.0.0.0/0"})
    assert "/0" in r.content.decode()
    r = c.post(url(5), {**NETZ, "basis_url": "nestwerk"})
    assert "Adresse wie" in r.content.decode()
    c.post(url(5), NETZ)
    r = c.post(url(6), {"zeitzone": "Mars/Olymp", "go_live_datum": "2030-01-01"})
    assert "Unbekannte Zeitzone" in r.content.decode()
    assert "mehr als ein Jahr" in r.content.decode()


def test_proxy_vorbelegt_mit_remote(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    c.post(url(2), ELTERN)
    c.post(url(3), KINDER)
    c.post(url(4), {"aktion": "ueberspringen"})
    html = c.get(url(5), REMOTE_ADDR="192.168.7.7").content.decode()
    assert "192.168.7.7" in html


def test_testmail_locmem(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    c.post(url(2), ELTERN)
    c.post(url(3), KINDER)
    r = c.post(url(4), {**SMTP, "aktion": "testen"})
    html = r.content.decode()
    assert "Testmail gesendet" in html
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["anna@example.org"]
    assert "geheim-smtp-pw" not in html


def test_smtp_pflicht_oder_ueberspringen(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    c.post(url(2), ELTERN)
    c.post(url(3), KINDER)
    r = c.post(url(4), {**SMTP, "passwort": "", "aktion": "weiter"})
    assert "Passwort des Postfachs" in r.content.decode()


def test_ganzer_assistent_dann_gesperrt_und_anmeldbar(c):
    _bis_schritt7(c)
    r = _startwerte_posten(c)
    assert r.status_code == 302, r.content.decode()[:2000]
    html = c.get(url(8)).content.decode()
    assert "Anna" in html and "Max" in html
    r = c.post(url(8))
    assert r.status_code == 200 and "Fertig" in r.content.decode()
    assert einstellungen.wert("allgemein.einrichtung_abgeschlossen") is True
    assert einstellungen.wert("allgemein.go_live_datum") == datetime.date.today()
    assert einstellungen.wert("konten.vertraute_proxys") == ["192.168.1.5"]
    assert einstellungen.wert("allgemein.anzeigename") == "Nestwerk Zuhause"
    # gesperrt
    assert c.get("/einrichtung/").status_code == 404
    assert c.post(url(8)).status_code == 404
    assert c.get("/").status_code == 200  # keine Umleitung mehr
    # Anmeldung
    anna = selectors.aktive_eltern().get(anzeigename="Anna")
    r = c.post("/anmelden/eltern/", {"eltern": str(anna.pk), "passwort": "Sommer-Wiese-42"})
    assert r.status_code == 302
    c.post("/abmelden/")
    max_ = selectors.aktive_kinder().get(anzeigename="Max")
    r = c.post(f"/anmelden/kind/{max_.pk}/", {"pin": "1357"})
    assert r.status_code == 302
    # Audit
    assert AuditEintrag.objects.filter(aktion="einrichtung.abgeschlossen").count() == 1
    # keine Klartext-Secrets
    alles = " ".join(str(e.details) for e in AuditEintrag.objects.all())
    for geheim in ("Sommer-Wiese-42", "geheim-smtp-pw", "1357", "2468"):
        assert geheim not in alles


def test_session_ohne_secrets(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    c.post(url(2), ELTERN)
    c.post(url(3), KINDER)
    from django.contrib.sessions.models import Session

    for s in Session.objects.all():
        text = str(s.get_decoded())
        assert "Sommer" not in text and "1357" not in text


def test_abschluss_mit_offenen_punkten(c):
    c.post(url(1), {"app_name": "Nestwerk"})
    from apps.einrichtung import services

    assert services.offene_punkte()
    with pytest.raises(services.SchrittFehler):
        services.abschliessen()


def test_ueberspringen_warnung_in_zusammenfassung(c):
    _bis_schritt7(c, smtp=False)
    assert _startwerte_posten(c).status_code == 302
    assert "keine Mails" in c.get(url(8)).content.decode()
    assert c.post(url(8)).status_code == 200


def test_startwerte_validierung(c):
    _bis_schritt7(c)
    r = c.post(url(7), {"e_konten__kind_pin_fehlversuche": "999"})
    assert r.status_code == 200
    assert einstellungen.wert("konten.kind_pin_fehlversuche") != 999
