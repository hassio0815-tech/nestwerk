import pytest


@pytest.fixture(autouse=True, scope="session")
def _flush_im_wartungsmodus():
    """Transaktionale Tests leeren die DB per ``flush`` (DELETE). Insert-only-Trigger erlauben
    DELETE nur im Wartungsmodus (``kern.db.wartung``)."""
    from django.test.testcases import TransactionTestCase

    from apps.kern.db import wartung

    original = TransactionTestCase._fixture_teardown

    def _fixture_teardown(self):
        with wartung():
            original(self)

    TransactionTestCase._fixture_teardown = _fixture_teardown
    yield
    TransactionTestCase._fixture_teardown = original


@pytest.fixture(autouse=True)
def _sprache_zuruecksetzen():
    """Eine englische Anfrage im Test-Client lässt Englisch im Thread aktiv; danach Deutsch."""
    from django.utils import translation

    yield
    translation.activate("de")
