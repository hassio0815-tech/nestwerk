import pytest
from django.db import connection


@pytest.mark.django_db
def test_gesundheit_liefert_200(client):
    antwort = client.get("/gesundheit/")
    assert antwort.status_code == 200
    assert antwort.json() == {"status": "ok"}


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


def test_zeitzone_und_sprache(settings):
    assert settings.TIME_ZONE == "Europe/Berlin"
    assert settings.LANGUAGE_CODE == "de"
    assert settings.USE_TZ is True
