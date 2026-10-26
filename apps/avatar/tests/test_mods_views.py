"""AP26: Oberfläche Mod-Shop, Kauf, Werkstatt, Themenwechsel-Dialog, Eltern-Bauaufträge."""

import itertools
import re
from datetime import UTC, datetime, timedelta

import pytest

from apps.avatar import services
from apps.avatar.models import Avatar, BesitzStatus, ModBesitz, ModDefinition
from apps.punkte import services as punkte_services
from apps.punkte.models import Art
from apps.spielregeln.models import Rang

pytestmark = pytest.mark.django_db
_n = itertools.count()


def gutschrift(kind, n):
    punkte_services.buchen(
        kind, Art.AUFGABE, n, schluessel=f"v:{next(_n)}", quelle_modul="aufgaben", von=None
    )


def mod(slot, seltenheit=1, thema="ritter"):
    return ModDefinition.objects.get(
        thema__schluessel=thema, slot__schluessel=slot, seltenheit=seltenheit
    )


@pytest.fixture
def mit_avatar(anna, uhr):
    uhr.jetzt = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    services.avatar_waehlen(anna, "ritter", {})
    gutschrift(anna, 500)
    return anna


def test_shop_ohne_avatar_leitet_zur_wahl(kind_client):
    antwort = kind_client.get("/kind/mods/")
    assert antwort.status_code == 302 and antwort["Location"].endswith("/kind/avatar/")


def test_shop_zeigt_gruppen_sperren_und_preise(kind_client, mit_avatar):
    html = kind_client.get("/kind/mods/").content.decode()
    assert "Mod-Shop" in html
    assert html.count('data-gruppe="') == 6
    assert "ab Rang Uncommon" in html
    assert "0/6 im Rang Common" in html
    assert "Schmiede" in html  # Inszenierung Ritter


def test_detail_und_kauf(kind_client, mit_avatar):
    m = mod("kopf")
    html = kind_client.get(f"/kind/mods/{m.schluessel}/").content.decode()
    assert "Kaufen für 40 Punkte" in html
    assert "2 Tage in der Schmiede" in html
    antwort = kind_client.post(f"/kind/mods/{m.schluessel}/kaufen/")
    assert antwort.status_code == 302 and "ok=gekauft" in antwort["Location"]
    assert ModBesitz.objects.get().status == BesitzStatus.IM_BAU
    # Doppelklick: kein zweiter Kauf
    antwort = kind_client.post(f"/kind/mods/{m.schluessel}/kaufen/")
    assert antwort.status_code == 409
    assert ModBesitz.objects.count() == 1
    html = kind_client.get("/kind/mods/?ok=gekauft").content.decode()
    assert "fertig in 2 Tagen" in html
    assert "wird geschmiedet" in html


def test_gesperrter_mod_nicht_kaufbar(kind_client, mit_avatar):
    m = mod("kopf", 3)
    html = kind_client.get(f"/kind/mods/{m.schluessel}/").content.decode()
    assert "Ab Rang Rare" in html
    assert kind_client.post(f"/kind/mods/{m.schluessel}/kaufen/").status_code == 409
    assert not ModBesitz.objects.exists()


def test_fremder_mod_404(kind_client, mit_avatar):
    assert kind_client.get(f"/kind/mods/{mod('kopf', 1, 'pirat').schluessel}/").status_code == 404


def test_dashboard_kachel_werkstatt(kind_client, mit_avatar):
    services.mod_kaufen(mit_avatar, mod("kopf"))
    html = kind_client.get("/kind/dungeon/").content.decode()
    assert "Meine Schmiede" in html
    assert "fertig in 2 Tagen" in html
    assert "0/6 im Rang Common" in html


def test_anlegen_und_ablegen(kind_client, mit_avatar, uhr):
    m = mod("hand")
    services.mod_kaufen(mit_avatar, m)
    uhr.weiter(days=3)
    services.mods_fertigstellen()
    assert kind_client.post("/kind/mods/slot/hand/ablegen/").status_code == 302
    assert "hand" not in Avatar.objects.get(pk=mit_avatar.pk).angelegt
    assert kind_client.post(f"/kind/mods/{m.schluessel}/anlegen/").status_code == 302
    assert Avatar.objects.get(pk=mit_avatar.pk).angelegt["hand"] == m.schluessel


def test_themenwechsel_dialog_zeigt_zahlen_und_wechselt(kind_client, mit_avatar, uhr):
    services.mod_kaufen(mit_avatar, mod("kopf"))
    services.mod_kaufen(mit_avatar, mod("hand"))
    uhr.weiter(days=10)
    services.mods_fertigstellen()
    html = kind_client.get("/kind/avatar/thema/?thema=pirat").content.decode()
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Du verlierst 2 Mods im Wert von 80 Punkten." in text
    assert "fällt von 2 auf 0" in text  # Zeitbremse: W44 + W45 je ein Mod
    assert "brauchst du wieder 6 Mods" in text
    assert "mindestens 6 Wochen" in text
    assert "keine Punkte zurück" in text
    pruefwert = re.search(r'name="pruefwert" value="([^"]+)"', html).group(1)
    antwort = kind_client.post(
        "/kind/avatar/thema/", {"thema": "pirat", "pruefwert": pruefwert, "verstanden": "on"}
    )
    assert antwort.status_code == 302
    assert Avatar.objects.get(pk=mit_avatar.pk).thema.schluessel == "pirat"


def test_themenwechsel_veralteter_pruefwert_zeigt_warnung_neu(kind_client, mit_avatar):
    antwort = kind_client.post("/kind/avatar/thema/", {"thema": "pirat", "pruefwert": "x"})
    assert antwort.status_code == 409
    assert Avatar.objects.get(pk=mit_avatar.pk).thema.schluessel == "ritter"


def test_eltern_bauauftraege_und_sofort(eltern_client, mit_avatar):
    besitz = services.mod_kaufen(mit_avatar, mod("kopf"))
    html = eltern_client.get("/eltern/mods/").content.decode()
    assert "Sofort fertigstellen" in html and "Anna" in html
    antwort = eltern_client.post(f"/eltern/mods/bau/{besitz.pk}/fertig/")
    assert antwort.status_code == 302
    besitz.refresh_from_db()
    assert besitz.status == BesitzStatus.FERTIG


def test_eltern_aendern_standards(eltern_client, mit_avatar):
    daten = {}
    for r in Rang.objects.all():
        daten[f"preis_{r.stufe}"] = r.mod_preis
        daten[f"bauzeit_{r.stufe}"] = str(r.bauzeit_stunden / 24).replace(".", ",")
    daten["preis_1"] = 55
    daten["bauzeit_1"] = "1,5"
    daten["faktor_preis"] = "1,0"
    daten["faktor_bauzeit"] = "1,0"
    antwort = eltern_client.post("/eltern/mods/standards/", daten)
    assert antwort.status_code == 302
    r = Rang.objects.get(stufe=1)
    assert (r.mod_preis, r.bauzeit_stunden) == (55, 36)
    assert Rang.objects.get(stufe=2).bauzeit_stunden == 72
    daten["faktor_preis"] = "9"
    assert eltern_client.post("/eltern/mods/standards/", daten).status_code == 400


def test_kind_darf_eltern_seite_nicht(kind_client, mit_avatar):
    assert kind_client.get("/eltern/mods/").status_code in (302, 403)


def test_eltern_kachel(eltern_client, mit_avatar):
    services.mod_kaufen(mit_avatar, mod("kopf"))
    html = eltern_client.get("/eltern/dungeon/").content.decode()
    assert "Mods und Bauaufträge" in html
    assert "1 im Bau" in html


def test_bauzeit_null_sofort_fertig(kind_client, mit_avatar):
    m = mod("kopf")
    m.bauzeit_stunden = 0
    m.save()
    antwort = kind_client.post(f"/kind/mods/{m.schluessel}/kaufen/")
    assert "ok=fertig" in antwort["Location"]
    assert ModBesitz.objects.get().status == BesitzStatus.FERTIG
    assert timedelta(0) == ModBesitz.objects.get().fertig_am - ModBesitz.objects.get().gekauft_am
