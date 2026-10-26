"""AP08: PWA-Manifest, Service Worker, VAPID, Abo-Endpunkte und Push-Kanal (webpush gemockt)."""

import json
import stat
from pathlib import Path
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from pywebpush import WebPushException

from apps.benachrichtigung import push, registry, router, versand, views_push
from apps.benachrichtigung import pushschluessel as vapid
from apps.benachrichtigung.models import PushAbo, ZustellStatus, Zustellung
from apps.konten.tests.conftest import angemeldet

from .conftest import TYP_ENTSCHEIDUNG, TYP_INFO, veroeffentlichen

pytestmark = pytest.mark.django_db

ENDPOINT = "https://web.push.apple.com/QWxhZGRpbjpvcGVuIHNlc2FtZQ"
ABO_DATEN = {"endpoint": ENDPOINT, "keys": {"p256dh": "BPkey-p256dh", "auth": "authkey"}}


@pytest.fixture
def webpush(monkeypatch):
    mock_ = mock.Mock(return_value=mock.Mock(status_code=201))
    monkeypatch.setattr(push, "webpush", mock_)
    return mock_


@pytest.fixture
def abo(mama):
    return push.abo_speichern(mama, ABO_DATEN, bezeichnung="iPhone Mama")


def antwort_fehler(status):
    return WebPushException("fehler", response=mock.Mock(status_code=status))


def zustellung(benutzer, kanal="push"):
    return Zustellung.objects.get(benachrichtigung__empfaenger=benutzer, kanal_id=kanal)


# --- Manifest, Service Worker, Offline -------------------------------------------------------


def test_manifest_ist_valide(client):
    antwort = client.get("/manifest.json")
    assert antwort.status_code == 200
    assert antwort["Content-Type"].startswith("application/manifest+json")
    assert antwort["Cache-Control"] == "no-cache"
    m = json.loads(antwort.content)
    assert m["name"] == "Nestwerk" and m["display"] == "standalone"
    assert m["start_url"] == "/" and m["scope"] == "/"
    assert m["theme_color"] == "#0E6A80" and m["background_color"] == "#F4F8F9"
    groessen = {i["sizes"] for i in m["icons"]}
    assert {"180x180", "192x192", "512x512"} <= groessen
    assert any(i["purpose"] == "maskable" for i in m["icons"])
    for icon in m["icons"]:
        assert icon["src"].startswith("/static/") and icon["type"] == "image/png"


def test_icons_sind_vorhanden():
    ordner = Path(push.__file__).parent / "static/benachrichtigung/icons"
    for name in ("icon-180.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        assert (ordner / name).read_bytes().startswith(b"\x89PNG")


def test_service_worker_ohne_cache_im_root_scope(client):
    antwort = client.get("/sw.js")
    assert antwort.status_code == 200
    assert antwort["Content-Type"] == "text/javascript; charset=utf-8"
    assert antwort["Cache-Control"] == "no-cache"
    assert antwort["Service-Worker-Allowed"] == "/"
    code = antwort.content.decode()
    assert "web_push" in code and "notificationclick" in code and "setAppBadge" in code
    assert 'OFFLINE_URL = "/offline/"' in code
    assert "http://" not in code.replace("https://nestwerk.test", "")  # keine externen Ressourcen


def test_sw_und_manifest_sind_oeffentlich_ohne_redirect(client):
    for pfad in ("/sw.js", "/manifest.json", "/offline/"):
        assert client.get(pfad).status_code == 200


def test_offline_seite_ist_eigenstaendig(client):
    html = client.get("/offline/").content.decode()
    assert "Keine Verbindung" in html
    assert "http://" not in html and "https://" not in html


def test_basis_verlinkt_manifest(mama, client):
    angemeldet(client, mama)
    html = client.get(reverse("benachrichtigung:liste")).content.decode()
    assert 'rel="manifest" href="/manifest.json"' in html and "pwa.js" in html


# --- VAPID -----------------------------------------------------------------------------------


def test_vapid_wird_nur_einmal_erzeugt(settings, tmp_path):
    settings.SECRETS_DIR = tmp_path / "secrets"
    erzeugt = []
    original = vapid.Vapid02.generate_keys

    def zaehlen(self):
        erzeugt.append(1)
        return original(self)

    with mock.patch.object(vapid.Vapid02, "generate_keys", zaehlen):
        erster = vapid.oeffentlicher_schluessel()
        datei = Path(settings.SECRETS_DIR) / "vapid_private.pem"
        inhalt = datei.read_bytes()
        zweiter = vapid.oeffentlicher_schluessel()
        vapid.schluessel()
    assert len(erzeugt) == 1
    assert erster == zweiter and datei.read_bytes() == inhalt
    assert stat.S_IMODE(datei.stat().st_mode) == 0o600
    assert len(erster) == 87 and "=" not in erster  # 65 Byte X9.62, URL-sicher ohne Padding
    assert not list(datei.parent.glob(".*.tmp"))


def test_vorhandene_vapid_datei_wird_nie_ueberschrieben(settings, tmp_path):
    settings.SECRETS_DIR = tmp_path / "s"
    erster = vapid.oeffentlicher_schluessel()
    (Path(settings.SECRETS_DIR) / "fernet.key").write_text("x")
    assert vapid.oeffentlicher_schluessel() == erster


# --- Abo-Endpunkte ---------------------------------------------------------------------------


def post_json(client, name, daten):
    return client.post(reverse(f"benachrichtigung:{name}"), json.dumps(daten), "application/json")


def test_abo_endpunkte_nur_angemeldet(client):
    for name in ("push_abo", "push_abmelden"):
        antwort = post_json(client, name, ABO_DATEN)
        assert antwort.status_code == 401
    assert PushAbo.objects.count() == 0


def test_abo_endpunkte_verlangen_csrf(client, mama):
    angemeldet(client, mama)
    strikt = Client(enforce_csrf_checks=True)
    strikt.cookies = client.cookies
    for name in ("push_abo", "push_abmelden"):
        assert post_json(strikt, name, ABO_DATEN).status_code == 403
    assert strikt.post(reverse("benachrichtigung:push_test")).status_code == 403
    assert PushAbo.objects.count() == 0


def test_abo_endpunkte_nur_post(client, mama):
    angemeldet(client, mama)
    assert client.get(reverse("benachrichtigung:push_abo")).status_code == 405


def test_abo_anmelden_speichert_pro_geraet_und_dedupliziert(client, mama):
    angemeldet(client, mama)
    daten = {**ABO_DATEN, "bezeichnung": "iPhone Mama"}
    assert post_json(client, "push_abo", daten).status_code == 200
    assert post_json(client, "push_abo", daten).status_code == 200
    abo = PushAbo.objects.get()
    assert abo.benutzer == mama and abo.endpoint == ENDPOINT and abo.aktiv
    assert abo.endpoint_hash == push.endpoint_hash(ENDPOINT)
    assert abo.bezeichnung == "iPhone Mama"
    zweites = {"endpoint": ENDPOINT + "2", "keys": {"p256dh": "k", "auth": "a"}}
    assert post_json(client, "push_abo", zweites).status_code == 200
    assert PushAbo.objects.count() == 2


@pytest.mark.parametrize(
    "daten",
    [
        {},
        {"endpoint": "http://unsicher.example/x", "keys": {"p256dh": "k", "auth": "a"}},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "k"}},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "k" * 201, "auth": "a"}},
    ],
)
def test_ungueltiges_abo_wird_abgelehnt(client, mama, daten):
    angemeldet(client, mama)
    assert post_json(client, "push_abo", daten).status_code == 400
    assert PushAbo.objects.count() == 0


def test_abmelden_entfernt_nur_eigenes_abo(client, mama, papa):
    push.abo_speichern(papa, ABO_DATEN)
    angemeldet(client, mama)
    assert post_json(client, "push_abmelden", {"endpoint": ENDPOINT}).json()["entfernt"] == 0
    assert PushAbo.objects.count() == 1
    push.abo_speichern(mama, {**ABO_DATEN, "endpoint": ENDPOINT + "m"})
    assert post_json(client, "push_abmelden", {"endpoint": ENDPOINT + "m"}).json()["entfernt"] == 1
    assert PushAbo.objects.get().benutzer == papa


def test_kiosk_sitzung_darf_nicht_abonnieren(client, mama, monkeypatch):
    angemeldet(client, mama)
    monkeypatch.setattr(views_push, "_ist_kiosk", lambda request: True)
    assert post_json(client, "push_abo", ABO_DATEN).status_code == 403
    seite = client.get(reverse("benachrichtigung:push_geraet")).content.decode()
    assert "keine Push-Nachrichten" in seite and "data-push-aktion" not in seite
    einst = client.get(reverse("benachrichtigung:einstellungen")).content.decode()
    assert "data-push-aktion" not in einst


def test_push_seite_und_einstellungen_zeigen_karte(client, mama, anna):
    assert client.get(reverse("benachrichtigung:push_geraet")).status_code == 302
    angemeldet(client, mama)
    seite = client.get(reverse("benachrichtigung:push_geraet")).content.decode()
    assert "Benachrichtigungen aktivieren" in seite and "Zum Home-Bildschirm" in seite
    assert "Als Web-App öffnen" in seite and 'data-push-schluessel="B' in seite
    einst = client.get(reverse("benachrichtigung:einstellungen")).content.decode()
    assert "Test-Push senden" in einst


def test_kind_sieht_push_seite_ohne_testknopf(client, anna):
    angemeldet(client, anna)
    seite = client.get(reverse("benachrichtigung:push_geraet")).content.decode()
    assert "Benachrichtigungen aktivieren" in seite and "Test-Push senden" not in seite


# --- Nutzlast und Versand --------------------------------------------------------------------


def gesendet(webpush):
    kwargs = webpush.call_args.kwargs
    return kwargs, json.loads(kwargs["data"])


def test_nutzlast_declarative_und_klassisch_lesbar(katalog, mama, abo, webpush):
    e = veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"aufgabe": "Müll", "instanz": 12})
    router.router(e)
    assert versand.zustellung_senden(zustellung(mama).pk) == ZustellStatus.GESENDET
    kwargs, nachricht = gesendet(webpush)
    assert nachricht["web_push"] == 8030
    n = nachricht["notification"]
    assert n["title"] and n["navigate"] == "https://nestwerk.test/eltern/meldung/12/"
    assert n["app_badge"] == 1
    assert kwargs["subscription_info"] == {
        "endpoint": ENDPOINT,
        "keys": {"p256dh": "BPkey-p256dh", "auth": "authkey"},
    }
    # klassisch: der Service Worker liest dasselbe JSON (title/body/navigate in notification)
    assert set(n) <= {"title", "body", "navigate", "app_badge"}


def test_header_ttl_urgency_topic_und_vapid(katalog, mama, abo, webpush, settings):
    from apps.ereignisse.models import EreignisTyp

    EreignisTyp.objects.filter(slug=TYP_ENTSCHEIDUNG).update(push_ttl_sekunden=7200)
    EreignisTyp.objects.filter(slug=TYP_INFO).update(push_ttl_sekunden=600)
    router.router(veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"aufgabe": "Müll", "instanz": 1}))
    versand.zustellungen_senden()
    kwargs, _ = gesendet(webpush)
    assert kwargs["ttl"] == 7200
    assert kwargs["headers"]["Urgency"] == "high"
    assert 1 <= len(kwargs["headers"]["Topic"]) <= 32
    assert kwargs["headers"]["Topic"].isalnum()
    assert kwargs["vapid_claims"] == {"sub": "https://nestwerk.test"}
    assert kwargs["vapid_private_key"] is not None

    router.router(veroeffentlichen(TYP_INFO))
    versand.zustellungen_senden()
    kwargs, _ = gesendet(webpush)
    assert kwargs["ttl"] == 600 and kwargs["headers"]["Urgency"] == "normal"


def test_410_und_404_deaktivieren_abo(katalog, mama, abo, webpush):
    webpush.side_effect = antwort_fehler(410)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    assert versand.zustellung_senden(zustellung(mama).pk) == ZustellStatus.AUFGEGEBEN
    abo.refresh_from_db()
    assert abo.aktiv is False
    assert registry.kanal("push").ziele(mama) == [None]  # kein aktives Gerät mehr

    abo2 = push.abo_speichern(mama, {**ABO_DATEN, "endpoint": ENDPOINT + "x"})
    webpush.side_effect = antwort_fehler(404)
    with pytest.raises(registry.DauerhafterFehler):
        push.abo_senden(abo2, {}, ttl=60)
    abo2.refresh_from_db()
    assert not abo2.aktiv


def test_andere_fehler_gehen_in_den_retry(katalog, mama, abo, webpush):
    webpush.side_effect = antwort_fehler(503)
    router.router(veroeffentlichen(TYP_INFO))
    z = zustellung(mama)
    assert versand.zustellung_senden(z.pk) == ZustellStatus.FEHLER
    z.refresh_from_db()
    abo.refresh_from_db()
    assert z.naechster_versuch is not None and "503" in z.fehler
    assert abo.aktiv and abo.fehlerzaehler == 1


def test_erfolg_setzt_zuletzt_ok_und_zaehler_zurueck(katalog, mama, abo, webpush):
    PushAbo.objects.filter(pk=abo.pk).update(fehlerzaehler=3)
    router.router(veroeffentlichen(TYP_INFO))
    versand.zustellungen_senden()
    abo.refresh_from_db()
    assert abo.zuletzt_ok is not None and abo.fehlerzaehler == 0


def test_ohne_abo_nicht_konfiguriert_und_ein_ziel_je_geraet(katalog, mama, webpush):
    router.router(veroeffentlichen(TYP_INFO))
    assert versand.zustellungen_senden() >= 1
    assert zustellung(mama).status == ZustellStatus.NICHT_KONFIGURIERT
    webpush.assert_not_called()


def test_mehrere_geraete_je_eine_zustellung(katalog, mama, abo, webpush):
    push.abo_speichern(mama, {**ABO_DATEN, "endpoint": ENDPOINT + "2"})
    router.router(veroeffentlichen(TYP_INFO))
    versand.zustellungen_senden()
    assert Zustellung.objects.filter(kanal_id="push").count() == 2
    assert webpush.call_count == 2


def test_ohne_basis_url_nicht_konfiguriert(katalog, mama, abo, webpush, settings):
    settings.BASIS_URL = ""
    router.router(veroeffentlichen(TYP_INFO))
    assert versand.zustellung_senden(zustellung(mama).pk) == ZustellStatus.NICHT_KONFIGURIERT
    webpush.assert_not_called()


def test_platzhalter_ist_ersetzt():
    assert isinstance(registry.kanal("push"), push.PushKanal)


# --- Test-Push -------------------------------------------------------------------------------


def test_test_push_an_eigene_geraete(client, mama, abo, webpush):
    angemeldet(client, mama)
    antwort = client.post(reverse("benachrichtigung:push_test"))
    assert antwort.status_code == 200 and "Test an 1 Gerät(e) gesendet" in antwort.content.decode()
    kwargs, nachricht = gesendet(webpush)
    assert nachricht["notification"]["title"] == "Nestwerk Test"
    assert nachricht["notification"]["navigate"] == "https://nestwerk.test/push/"
    assert kwargs["ttl"] == 300


def test_test_push_ohne_geraet_und_mit_fehler(client, mama, webpush):
    angemeldet(client, mama)
    assert "Noch kein Gerät" in client.post(reverse("benachrichtigung:push_test")).content.decode()
    push.abo_speichern(mama, ABO_DATEN)
    webpush.side_effect = antwort_fehler(410)
    assert "1 fehlgeschlagen" in client.post(reverse("benachrichtigung:push_test")).content.decode()
    assert PushAbo.objects.get().aktiv is False


def test_test_push_nur_eltern(client, anna):
    angemeldet(client, anna)
    assert client.post(reverse("benachrichtigung:push_test")).status_code == 403


# --- Endpoint-Allowlist (B-14) ---------------------------------------------------------------


def _abo_daten(endpoint):
    return {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://web.push.apple.com/abc",
        "https://push.apple.com/abc",
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://eu.notify.windows.com/?token=abc",
        "https://WEB.PUSH.APPLE.COM:443/abc",
    ],
)
def test_erlaubte_hosts_werden_akzeptiert(mama, endpoint):
    assert push.abo_speichern(mama, _abo_daten(endpoint)).aktiv


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://evilpush.apple.com.attacker.tld/x",  # Suffix-Trick
        "https://evilpush.apple.com/x",  # keine Label-Grenze
        "https://push.apple.com.evil.example/x",
        "https://attacker.tld/web.push.apple.com",
        "https://web.push.apple.com@attacker.tld/x",  # Benutzerinfo-Trick
        "http://web.push.apple.com/x",
        "https://web.push.apple.com:8443/x",
        "https://127.0.0.1/x",
        "https://10.0.0.5/x",
        "https://[::1]/x",
        "https://[2606:4700::1111]/x",
        "https://8.8.8.8/x",
    ],
)
def test_unzulaessige_endpoints_werden_abgelehnt(mama, endpoint):
    with pytest.raises(push.UngueltigesAbo):
        push.abo_speichern(mama, _abo_daten(endpoint))
    assert PushAbo.objects.count() == 0


@pytest.mark.parametrize(
    "adresse",
    [
        "10.1.2.3",
        "127.0.0.1",
        "169.254.169.254",
        "192.168.1.10",
        "::1",
        "fe80::1",
        "::ffff:192.168.1.1",
        "100.64.0.1",
    ],
)
def test_private_aufloesung_wird_abgelehnt(mama, monkeypatch, adresse):
    monkeypatch.setattr(push.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (adresse, 443))])
    with pytest.raises(push.UngueltigesAbo):
        push.abo_speichern(mama, _abo_daten(ENDPOINT))


def test_eine_private_adresse_unter_mehreren_genuegt(mama, monkeypatch):
    monkeypatch.setattr(
        push.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.0.0.1", 443))],
    )
    with pytest.raises(push.UngueltigesAbo):
        push.abo_speichern(mama, _abo_daten(ENDPOINT))


def test_abo_endpunkt_antwortet_400_auf_deutsch(client, mama):
    angemeldet(client, mama)
    antwort = post_json(client, "push_abo", _abo_daten("https://127.0.0.1/x"))
    assert antwort.status_code == 400
    assert "nicht erlaubt" in antwort.json()["fehler"]
    antwort = post_json(client, "push_abo", _abo_daten("https://evilpush.apple.com.attacker.tld/x"))
    assert antwort.status_code == 400
    assert antwort.json()["fehler"] == "Dieser Push-Dienst ist nicht erlaubt"


def test_aenderung_der_liste_wirkt_sofort(mama):
    from apps.kern import einstellungen

    endpoint = "https://push.beispiel-dienst.example/abc"
    with pytest.raises(push.UngueltigesAbo):
        push.abo_speichern(mama, _abo_daten(endpoint))
    einstellungen.setzen("benachrichtigung.push_erlaubte_hosts", ["beispiel-dienst.example"])
    assert push.abo_speichern(mama, _abo_daten(endpoint)).aktiv
    with pytest.raises(push.UngueltigesAbo):
        push.abo_speichern(mama, _abo_daten(ENDPOINT))  # Apple jetzt nicht mehr in der Liste


def test_ungueltige_host_endung_in_der_liste_wird_abgelehnt():
    from apps.kern import einstellungen

    for falsch in ("localhost", "10.0.0.1", "https://x.de", "-a.de", "a b.de"):
        with pytest.raises(einstellungen.UngueltigerWert):
            einstellungen.setzen("benachrichtigung.push_erlaubte_hosts", [falsch])


def test_versand_prueft_erneut_und_deaktiviert_abo(katalog, mama, abo, webpush):
    from apps.kern import einstellungen
    from apps.kern.models import AuditEintrag

    einstellungen.setzen("benachrichtigung.push_erlaubte_hosts", ["fcm.googleapis.com"])
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    assert versand.zustellung_senden(zustellung(mama).pk) == ZustellStatus.AUFGEGEBEN
    webpush.assert_not_called()
    abo.refresh_from_db()
    assert abo.aktiv is False
    eintrag = AuditEintrag.objects.get(aktion="benachrichtigung.push_endpoint_abgewiesen")
    assert "apple" not in json.dumps(eintrag.details) and "http" not in json.dumps(eintrag.details)


def test_versand_private_aufloesung_deaktiviert_abo(mama, abo, webpush, monkeypatch):
    monkeypatch.setattr(
        push.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.168.0.9", 443))]
    )
    with pytest.raises(registry.DauerhafterFehler):
        push.abo_senden(abo, {}, ttl=60)
    webpush.assert_not_called()
    abo.refresh_from_db()
    assert not abo.aktiv


def test_versand_dns_ausfall_ist_vorlaeufig(mama, abo, webpush, monkeypatch):
    def kaputt(*a, **k):
        raise OSError("dns")

    monkeypatch.setattr(push.socket, "getaddrinfo", kaputt)
    with pytest.raises(RuntimeError):
        push.abo_senden(abo, {}, ttl=60)
    abo.refresh_from_db()
    assert abo.aktiv and abo.fehlerzaehler == 1


def test_manifest_icons_sind_die_offiziellen_logo_dateien():
    """Die App-Icons stammen 1:1 aus branding/nestwerk (kein Platzhalter mehr)."""
    ordner = Path(push.__file__).parent / "static/benachrichtigung/icons"
    marke = Path(__file__).resolve().parents[3] / "branding/nestwerk"
    for ziel, quelle in {
        "icon-180.png": "apple-touch-icon-180.png",
        "icon-192.png": "icon-192.png",
        "icon-512.png": "icon-512.png",
        "icon-maskable-512.png": "icon-maskable-512.png",
    }.items():
        assert (ordner / ziel).read_bytes() == (marke / quelle).read_bytes()
