import pytest

from apps.konten import services as konten_services
from apps.konten.tests.conftest import PIN


@pytest.fixture
def kind_a(db):
    return konten_services.kind_anlegen("Testkind A", PIN)


@pytest.fixture
def kind_b(db):
    return konten_services.kind_anlegen("Testkind B", PIN)
