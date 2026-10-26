import pytest
from django.test import Client


@pytest.fixture(autouse=True)
def _erzwingen(settings):
    settings.EINRICHTUNG_ERZWINGEN = True
    settings.ALLOWED_HOSTS = ["testserver", "localhost"]


@pytest.fixture
def c(db):
    return Client()


def url(nr):
    return f"/einrichtung/schritt/{nr}/"


ELTERN = {
    "eltern1_name": "Anna",
    "eltern1_rolle": "mama",
    "eltern1_email": "anna@example.org",
    "eltern2_name": "Ben",
    "eltern2_rolle": "papa",
    "eltern2_email": "ben@example.org",
    "passwort": "Sommer-Wiese-42",
    "passwort2": "Sommer-Wiese-42",
}
KINDER = {
    "anzahl": "3",
    "kind-0-name": "Max",
    "kind-0-pin": "1357",
    "kind-0-pin2": "1357",
    "kind-0-farbe": "blau",
    "kind-1-name": "Leo",
    "kind-1-pin": "2468",
    "kind-1-pin2": "2468",
    "kind-2-name": "",
}
SMTP = {
    "host": "smtp.example.org",
    "port": "587",
    "sicherheit": "starttls",
    "benutzername": "nestwerk@example.org",
    "passwort": "geheim-smtp-pw",
    "absender": "nestwerk@example.org",
    "testadresse": "anna@example.org",
}
NETZ = {
    "basis_url": "https://nestwerk.example.org",
    "kind_netze": "192.168.0.0/16\n127.0.0.0/8",
    "proxys": "192.168.1.5",
}
ZEIT = {"zeitzone": "Europe/Berlin", "go_live_datum": ""}
