"""Eine Basis-URL für Mail- und Push-Links: DB-Einstellung vor settings.BASIS_URL (AP17)."""

import pytest

from apps.benachrichtigung import push, pushschluessel, registry
from apps.benachrichtigung.kanaele import absolute_url
from apps.kern import adressen, einstellungen
from apps.kern.models import Einstellung


def db_wert(wert):
    Einstellung.objects.update_or_create(
        schluessel="einrichtung.basis_url", defaults={"wert": wert, "modul": "einrichtung"}
    )


def test_db_wert_hat_vorrang_vor_settings(db, settings):
    settings.BASIS_URL = "https://alt.example"
    db_wert("https://nestwerk.example.org/")
    assert adressen.basis_url() == "https://nestwerk.example.org"
    assert absolute_url("/kind/") == "https://nestwerk.example.org/kind/"
    assert pushschluessel.kontakt() == "https://nestwerk.example.org"


def test_ohne_db_wert_gilt_settings(db, settings):
    settings.BASIS_URL = "https://alt.example/"
    db_wert("")
    assert adressen.basis_url() == "https://alt.example"
    Einstellung.objects.filter(schluessel="einrichtung.basis_url").delete()
    assert adressen.basis_url() == "https://alt.example"
    assert absolute_url("/x") == "https://alt.example/x"


def test_aenderung_im_dashboard_wirkt_sofort(db, settings):
    settings.BASIS_URL = ""
    db_wert("")
    einstellungen.setzen("einrichtung.basis_url", "https://neu.example", akteur=None)
    assert absolute_url("/") == "https://neu.example/"


def test_push_ohne_jede_basis_url_ist_nicht_konfiguriert(db, settings):
    settings.BASIS_URL = ""
    db_wert("")
    with pytest.raises(registry.NichtKonfiguriert):
        push._eigene_origin_url("/")
