import pytest
from django.db import connection


@pytest.mark.django_db
def test_ohne_worker_ist_der_status_degradiert_aber_200(client):
    antwort = client.get("/gesundheit/")
    assert antwort.status_code == 200
    assert antwort.json() == {"status": "degradiert", "worker": {"lebt": False, "herzschlag": None}}


@pytest.mark.django_db
def test_mit_worker_herzschlag_ist_der_status_ok(client):
    from apps.ereignisse import worker

    worker.herzschlag()
    antwort = client.get("/gesundheit/")
    assert antwort.status_code == 200
    korpus = antwort.json()
    assert korpus["status"] == "ok"
    assert korpus["worker"]["lebt"] is True and korpus["worker"]["herzschlag"]


@pytest.mark.django_db
def test_alter_herzschlag_ist_degradiert(client):
    from datetime import timedelta

    from django.utils import timezone

    from apps.ereignisse.models import WorkerHerzschlag
    from apps.ereignisse.worker import WORKER_NAME

    WorkerHerzschlag.objects.create(
        name=WORKER_NAME, inhaber="x", zuletzt=timezone.now() - timedelta(minutes=10)
    )
    antwort = client.get("/gesundheit/")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "degradiert"


@pytest.mark.django_db
def test_datenbankfehler_liefert_503(client, monkeypatch):
    from django.db import DatabaseError

    from apps.ereignisse import selectors

    def kaputt():
        raise DatabaseError("weg")

    monkeypatch.setattr(selectors, "worker_herzschlag", kaputt)
    antwort = client.get("/gesundheit/")
    assert antwort.status_code == 503
    assert antwort.json()["status"] == "fehler"


@pytest.mark.django_db
def test_sqlite_pragmas_aktiv():
    with connection.cursor() as cur:

        def pragma(name):
            cur.execute(f"PRAGMA {name}")
            return cur.fetchone()[0]

        assert pragma("journal_mode") == "wal"
        assert pragma("synchronous") == 1  # NORMAL
        assert pragma("busy_timeout") == 5000
        assert pragma("foreign_keys") == 1
        assert pragma("secure_delete") == 1


@pytest.mark.django_db
def test_healthcheck_host_ist_auch_mit_domain_erlaubt(client, settings):
    """Regression B-01: compose-Healthcheck ruft 127.0.0.1:8000 auf, .env setzt nur die Domain."""
    from nestwerk.settings.basis import allowed_hosts

    settings.ALLOWED_HOSTS = allowed_hosts("nestwerk.example.org")
    assert settings.ALLOWED_HOSTS == ["nestwerk.example.org", "localhost", "127.0.0.1"]
    antwort = client.get("/gesundheit/", HTTP_HOST="127.0.0.1:8000")
    assert antwort.status_code == 200
    assert client.get("/gesundheit/", HTTP_HOST="boese.example").status_code == 400


def test_allowed_hosts_ohne_doppelte():
    from nestwerk.settings.basis import allowed_hosts

    assert allowed_hosts("") == ["localhost", "127.0.0.1"]
    assert allowed_hosts(" localhost , a.b ") == ["localhost", "a.b", "127.0.0.1"]


def test_zeitzone_und_sprache(settings):
    assert settings.TIME_ZONE == "Europe/Berlin"
    assert settings.LANGUAGE_CODE == "de"
    assert settings.USE_TZ is True
