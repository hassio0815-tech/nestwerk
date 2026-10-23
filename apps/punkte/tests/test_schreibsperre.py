"""Gemeinsame Schreibsperre für punkte und belohnung (Review AP19, B-10)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction

from apps.punkte import services

pytestmark = pytest.mark.django_db


def test_sperre_verlangt_transaktion(anna, monkeypatch):
    monkeypatch.setattr(type(connection), "in_atomic_block", False, raising=False)
    with pytest.raises(ImproperlyConfigured, match="atomic"):
        services.schreibsperre(anna)


def test_sperre_verlangt_immediate(anna, monkeypatch):
    optionen = dict(connection.settings_dict["OPTIONS"], transaction_mode="DEFERRED")
    monkeypatch.setitem(connection.settings_dict, "OPTIONS", optionen)
    with transaction.atomic(), pytest.raises(ImproperlyConfigured, match="IMMEDIATE"):
        services.schreibsperre(anna)
