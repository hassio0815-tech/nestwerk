"""Eltern-Oberfläche der KI-Anbindung: nur Eltern, Risiko-Hinweis, Einwilligung, Key unsichtbar."""

from django.urls import reverse

from apps.kern.models import AuditEintrag
from apps.lernen.models import KiAnbieter, KiZuordnung

KEY = "test-schluessel-nicht-echt"


def _neu(client, **kw):
    daten = {
        "name": "Mein Server",
        "typ": "openai_kompatibel",
        "basis_url": "http://dein-ki-server:11434/v1",
        "modell": "dein-modellname",
        "api_key": "",
    }
    daten.update(kw)
    return client.post(reverse("lernen:ki_anbieter_neu"), daten)


ALLE_GET = ["lernen:ki"]


def test_nur_eltern(kind_client, client, kind_a, lokal):
    for name, args in [
        ("lernen:ki", []),
        ("lernen:ki_anbieter_neu", []),
        ("lernen:ki_anbieter_aendern", [lokal.pk]),
        ("lernen:ki_aktivieren", [lokal.pk]),
        ("lernen:ki_deaktivieren", [lokal.pk]),
        ("lernen:ki_testen", [lokal.pk]),
        ("lernen:ki_zuordnung", []),
    ]:
        url = reverse(name, args=args)
        assert kind_client.get(url).status_code == 403, name
        assert kind_client.post(url, {}).status_code == 403, name
        antwort = client.post(url, {})
        assert antwort.status_code in (302, 403), name
    lokal.refresh_from_db()
    assert not lokal.aktiv and not KiZuordnung.objects.exists()


def test_seite_leer_zeigt_ki_aus(eltern_client):
    antwort = eltern_client.get(reverse("lernen:ki"))
    assert antwort.status_code == 200
    html = antwort.content.decode()
    assert "Noch kein Anbieter" in html and "KI aus" in html


def test_get_auf_schreibende_urls_nicht_erlaubt(eltern_client, lokal):
    assert eltern_client.get(reverse("lernen:ki_aktivieren", args=[lokal.pk])).status_code == 405
    assert eltern_client.get(reverse("lernen:ki_testen", args=[lokal.pk])).status_code == 405


def test_eltern_seite_verlinkt_ki(eltern_client):
    html = eltern_client.get(reverse("lernen:eltern")).content.decode()
    assert reverse("lernen:ki") in html


def test_anlegen_lokal_mit_hinweis_und_ohne_checkbox(eltern_client):
    assert _neu(eltern_client).status_code == 302
    a = KiAnbieter.objects.get()
    assert not a.aktiv and not a.ist_cloud
    html = eltern_client.get(reverse("lernen:ki")).content.decode()
    assert "Auch eine eigene KI kann Fehler machen" in html
    assert 'name="einwilligung"' not in html
    assert "Bevor ihr diesen Cloud-Anbieter einschaltet" not in html


def test_cloud_risiko_hinweis_vor_aktivierung_und_einwilligung(eltern_client, mama):
    _neu(eltern_client, typ="anthropic", basis_url="", api_key=KEY)
    a = KiAnbieter.objects.get()
    assert a.ist_cloud and not a.aktiv
    html = eltern_client.get(reverse("lernen:ki")).content.decode()
    assert "Bevor ihr diesen Cloud-Anbieter einschaltet" in html
    assert "Daten verlassen euren Server" in html
    assert "Kosten" in html and "Fehler machen" in html
    assert 'name="einwilligung"' in html and "required" in html
    # ohne Häkchen: kein Einschalten
    antwort = eltern_client.post(reverse("lernen:ki_aktivieren", args=[a.pk]), {})
    assert antwort.status_code == 400 and "Einwilligung" in antwort.content.decode()
    a.refresh_from_db()
    assert not a.aktiv and a.einwilligung_am is None
    # mit Häkchen: Einwilligung wird mit Zeitpunkt und Person gespeichert
    eltern_client.post(reverse("lernen:ki_aktivieren", args=[a.pk]), {"einwilligung": "1"})
    a.refresh_from_db()
    assert a.aktiv and a.einwilligung_am is not None and a.einwilligung_von == mama
    html = eltern_client.get(reverse("lernen:ki")).content.decode()
    assert "Einwilligung am" in html and "Mama" in html


def test_key_nie_in_ausgaben(eltern_client):
    r = _neu(eltern_client, typ="anthropic", basis_url="", api_key=KEY)
    a = KiAnbieter.objects.get()
    seiten = [
        r.content.decode(),
        eltern_client.get(reverse("lernen:ki")).content.decode(),
        eltern_client.post(reverse("lernen:ki_aktivieren", args=[a.pk]), {}).content.decode(),
    ]
    assert all(KEY not in s for s in seiten)
    assert "Schlüssel gesetzt" in seiten[1]
    assert KEY not in str(list(AuditEintrag.objects.values_list("details", flat=True)))
    # beim Bearbeiten bleibt das Feld leer und der Schlüssel erhalten
    alt = a.schluessel_verschluesselt
    eltern_client.post(
        reverse("lernen:ki_anbieter_aendern", args=[a.pk]),
        {
            "name": "Mein Server",
            "typ": "anthropic",
            "basis_url": "",
            "modell": "neu",
            "api_key": "",
        },
    )
    a.refresh_from_db()
    assert a.schluessel_verschluesselt == alt and a.modell == "neu"


def test_validierungsfehler_zeigen_meldung(eltern_client):
    antwort = _neu(eltern_client, basis_url="")
    assert antwort.status_code == 400 and "Adresse" in antwort.content.decode()
    antwort = _neu(eltern_client, typ="openai", basis_url="", api_key="")
    assert antwort.status_code == 400 and "API-Schlüssel" in antwort.content.decode()
    assert not KiAnbieter.objects.exists()


def test_aendern_unbekannter_anbieter_404(eltern_client):
    url = reverse("lernen:ki_anbieter_aendern", args=[999])
    assert eltern_client.post(url, {}).status_code == 404


def test_aktivieren_und_deaktivieren_lokal(eltern_client, lokal):
    eltern_client.post(reverse("lernen:ki_aktivieren", args=[lokal.pk]), {})
    lokal.refresh_from_db()
    assert lokal.aktiv
    eltern_client.post(reverse("lernen:ki_deaktivieren", args=[lokal.pk]))
    lokal.refresh_from_db()
    assert not lokal.aktiv


def test_verbindung_testen_zeigt_ergebnis_ohne_secrets(eltern_client, cloud, transport):
    url = reverse("lernen:ki_testen", args=[cloud.pk])
    transport.antworten.append((200, {"content": [{"type": "text", "text": "OK"}]}))
    html = eltern_client.post(url, HTTP_HX_REQUEST="true").content.decode()
    assert f'id="ki-test-{cloud.pk}"' in html and "Verbindung klappt" in html
    transport.antworten.append((401, {"error": KEY}))
    html = eltern_client.post(url, HTTP_HX_REQUEST="true").content.decode()
    assert "Test fehlgeschlagen" in html and "Schlüssel prüfen" in html
    assert KEY not in html
    # der Seitenaufruf zeigt danach nur den Status
    assert (
        "Letzter Test: fehlgeschlagen" in eltern_client.get(reverse("lernen:ki")).content.decode()
    )


def test_zuordnung_ueber_die_oberflaeche(eltern_client, lokal):
    url = reverse("lernen:ki_zuordnung")
    eltern_client.post(url, {"aufgabe": "tutor", "anbieter": lokal.pk})
    assert KiZuordnung.objects.get().anbieter == lokal
    html = eltern_client.get(reverse("lernen:ki")).content.decode()
    assert "Anbieter ist ausgeschaltet: KI bleibt aus." in html
    eltern_client.post(url, {"aufgabe": "tutor", "anbieter": ""})
    assert not KiZuordnung.objects.exists()
    assert eltern_client.post(url, {"aufgabe": "quatsch", "anbieter": ""}).status_code == 400
    assert eltern_client.post(url, {"aufgabe": "tutor", "anbieter": "999"}).status_code == 404


def test_zuordnungs_status_hinweise(eltern_client, cloud, mama):
    from apps.lernen import ki_services

    ki_services.zuordnung_setzen("tutor", cloud)
    cloud.aktiv = True
    cloud.save()
    assert "Einwilligung fehlt" in eltern_client.get(reverse("lernen:ki")).content.decode()
    ki_services.anbieter_aktivieren(cloud, einwilligung=True, akteur=mama)
    html = eltern_client.get(reverse("lernen:ki")).content.decode()
    assert "bereit" in html


def test_englische_oberflaeche(eltern_client):
    eltern_client.cookies["nestwerk_sprache"] = "en"
    html = eltern_client.get(reverse("lernen:ki")).content.decode()
    assert "AI connection" in html and "Which provider for what?" in html
