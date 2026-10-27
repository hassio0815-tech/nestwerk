"""Zweisprachigkeit: Push und Mail kommen in der Sprache des Empfängers (Worker ohne Request)."""

import json
from unittest import mock

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.benachrichtigung import push, router, texte, versand
from apps.benachrichtigung.models import Benachrichtigung, Zustellung
from apps.konten.tests.conftest import angemeldet

from .conftest import TYP_ENTSCHEIDUNG, veroeffentlichen

pytestmark = pytest.mark.django_db

ABO = {"endpoint": "https://web.push.apple.com/abc", "keys": {"p256dh": "BPkey", "auth": "authkey"}}


@pytest.fixture
def webpush(monkeypatch):
    mock_ = mock.Mock(return_value=mock.Mock(status_code=201))
    monkeypatch.setattr(push, "webpush", mock_)
    return mock_


def senden(benutzer, kanal):
    z = Zustellung.objects.get(benachrichtigung__empfaenger=benutzer, kanal_id=kanal)
    versand.zustellung_senden(z.pk)


def test_push_fuer_englischen_empfaenger_ist_englisch(katalog, mama, papa, webpush):
    mama.sprache = "en"
    mama.save()
    push.abo_speichern(mama, ABO)
    push.abo_speichern(papa, {**ABO, "endpoint": "https://web.push.apple.com/papa"})
    with texte.isoliert():
        texte.text_registrieren(
            TYP_ENTSCHEIDUNG,
            titel="Aufgabe bestätigt!",
            text="„{aufgabe}“ ist geschafft. Gut gemacht!",
        )
        router.router(veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"aufgabe": "Müll"}))
    senden(mama, "push")
    nachricht = json.loads(webpush.call_args.kwargs["data"])["notification"]
    assert nachricht["title"] == "Task approved!"
    assert nachricht["body"] == "“Müll” is done. Well done!"
    senden(papa, "push")
    nachricht = json.loads(webpush.call_args.kwargs["data"])["notification"]
    assert nachricht["title"] == "Aufgabe bestätigt!"
    assert Benachrichtigung.objects.get(empfaenger=mama).titel == "Task approved!"


def test_mail_fuer_englischen_empfaenger_ist_englisch(katalog, mama, smtp):
    mama.sprache = "en"
    mama.save()
    with texte.isoliert():
        texte.text_registrieren(TYP_ENTSCHEIDUNG, titel="Aufgabe bestätigt!")
        router.router(veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"aufgabe": "Müll"}))
    senden(mama, "email")
    nachricht = django_mail.outbox[0]
    assert nachricht.subject == "Nestwerk: Task approved!"
    assert "Hi Mama," in nachricht.body and "Notification settings" in nachricht.body
    html, _ = nachricht.alternatives[0]
    assert '<html lang="en">' in html and ">Open<" not in html  # kein Link ohne Deep-Link


def test_englische_seiten(client, mama):
    mama.sprache = "en"
    mama.save()
    angemeldet(client, mama)
    liste = client.get(reverse("benachrichtigung:liste")).content.decode()
    assert "Nothing has happened yet" in liste and "Keine" not in liste
    einst = client.get(reverse("benachrichtigung:einstellungen")).content.decode()
    assert "Quiet hours" in einst and "Turn on notifications" in einst
    assert 'data-push-text-aktivieren-fehler="That did not work' in einst


def test_offline_seite_setzt_lang(client):
    seite = client.get(reverse("benachrichtigung:offline"), headers={"accept-language": "en"})
    html = seite.content.decode()
    assert '<html lang="en">' in html and "No connection" in html
