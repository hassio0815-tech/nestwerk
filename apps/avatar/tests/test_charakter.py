"""Charakter-Bildschirm der Dungeon-Seite: Slot-Zustände, Slot-Filter im Shop, Figurenname
(setzen, prüfen, Eltern-Reset) und Snapshot in der Ruhmeshalle."""

import pytest
from django.urls import reverse

from apps.avatar import services
from apps.avatar.models import Avatar, RuhmeshallenEintrag
from apps.avatar.tests.test_ruhmeshalle import (  # noqa: F401  (Fixtures und Helfer)
    MONTAG,
    ausbauen,
    bau_start,
    held,
    kind,
    mod,
)
from apps.kern.models import AuditEintrag

pytestmark = pytest.mark.django_db


def seite(client):
    return client.get(reverse("oberflaeche:dungeon")).content.decode()


def zustand(html, slot):
    import re

    treffer = re.search(rf'data-slot="{slot}" data-zustand="([a-z_]+)"', html)
    return treffer.group(1) if treffer else None


def test_slots_leer_im_bau_und_gefuellt(kind, kind_client, uhr):
    html = seite(kind_client)
    assert "data-charakter" in html and "data-ziel" in html
    assert {zustand(html, s) for s in ("kopf", "koerper", "hand")} == {"leer"}
    services.mod_kaufen(kind, mod("ritter", "kopf"))
    html = seite(kind_client)
    assert zustand(html, "kopf") == "im_bau" and "fertig" in html
    uhr.weiter(days=8)
    services.mods_fertigstellen()
    html = seite(kind_client)
    assert zustand(html, "kopf") == "gefuellt"
    assert mod("ritter", "kopf").name in html and "Fertig seit" in html
    assert zustand(html, "hand") == "leer"


def test_leerer_slot_fuehrt_in_den_gefilterten_shop(kind, kind_client):
    html = seite(kind_client)
    assert "/kind/mods/?slot=hand" in html
    shop = kind_client.get("/kind/mods/?slot=hand").content.decode()
    assert 'data-slot-filter="hand"' in shop
    assert mod("ritter", "hand").name in shop
    assert mod("ritter", "kopf").name not in shop
    alle = kind_client.get("/kind/mods/?slot=gibtsnicht").content.decode()
    assert "data-slot-filter" not in alle and mod("ritter", "kopf").name in alle


def test_name_setzen_bereinigen_und_pruefen(kind, kind_client):
    url = reverse("avatar:name")
    antwort = kind_client.post(url, {"name": "  Ritter\u0007 \t Max\n "}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200
    assert Avatar.objects.get(pk=kind.pk).name == "Ritter Max"
    assert "Ritter Max" in seite(kind_client)
    zu_lang = kind_client.post(url, {"name": "x" * 21}, HTTP_HX_REQUEST="true")
    assert zu_lang.status_code == 422 and "höchstens 20" in zu_lang.content.decode()
    assert Avatar.objects.get(pk=kind.pk).name == "Ritter Max"
    kind_client.post(url, {"name": "   "})  # leer = Name entfernen
    assert Avatar.objects.get(pk=kind.pk).name == ""
    assert services.avatar_name(kind) == kind.anzeigename  # Fallback


def test_eltern_setzen_zurueck_mit_protokoll(kind, kind_client, eltern_client):
    services.avatar_name_setzen(kind, "Doofname")
    assert kind_client.post(reverse("avatar:name_zuruecksetzen", args=[kind.pk])).status_code == 403
    antwort = eltern_client.post(reverse("avatar:name_zuruecksetzen", args=[kind.pk]))
    assert antwort.status_code == 302
    assert Avatar.objects.get(pk=kind.pk).name == ""
    eintrag = AuditEintrag.objects.get(aktion="avatar.name_zurueckgesetzt")
    assert eintrag.details["alt"] == "Doofname"
    assert (
        "Doofname" not in eltern_client.get(reverse("oberflaeche:eltern_dungeon")).content.decode()
    )


def test_ruhmeshalle_speichert_namens_snapshot(held, uhr):
    services.avatar_name_setzen(held, "Sir Anna")
    eintrag, _ = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    assert RuhmeshallenEintrag.objects.get(pk=eintrag.pk).avatar_name == "Sir Anna"
    services.avatar_name_setzen(held, "Neuer Name")
    assert RuhmeshallenEintrag.objects.get(pk=eintrag.pk).avatar_name == "Sir Anna"
