import pytest
from django.test import Client
from django.urls import reverse

from apps.avatar import services
from apps.avatar.generator import svgsicher
from apps.avatar.models import Avatar

from .conftest import client_fuer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leerer_speicher():
    services._SPEICHER.clear()


# --- Auslieferung ---------------------------------------------------------------------------------


def test_svg_wird_mit_cache_header_etag_und_csp_ausgeliefert(anna):
    services.avatar_waehlen(anna, "ritter", {})
    url = services.bild_url(anna)
    antwort = Client().get(url)  # ohne Anmeldung: die Tablet-Startseite zeigt Avatare ohne Login
    assert antwort.status_code == 200
    assert antwort["Content-Type"] == "image/svg+xml"
    assert antwort["Cache-Control"] == "public, max-age=31536000, immutable"
    assert antwort["ETag"] == f'"{url.split("/")[-1][:-4]}"'
    assert "script-src" not in antwort["Content-Security-Policy"]
    assert "default-src 'none'" in antwort["Content-Security-Policy"]
    assert antwort["X-Content-Type-Options"] == "nosniff"
    inhalt = antwort.content.decode()
    assert svgsicher.svg_pruefen(inhalt) is None
    assert "<script" not in inhalt


def test_etag_liefert_304(anna):
    services.avatar_waehlen(anna, "ritter", {})
    url = services.bild_url(anna)
    antwort = Client().get(url, headers={"If-None-Match": Client().get(url)["ETag"]})
    assert antwort.status_code == 304 and not antwort.content
    assert antwort["Cache-Control"].startswith("public")


@pytest.mark.parametrize(
    "pfad", ["/avatar/" + "0" * 64 + ".svg", "/avatar/zzz.svg", "/avatar/" + "A" * 64 + ".svg"]
)
def test_unbekannter_hash_ist_404(pfad):
    assert Client().get(pfad).status_code == 404


def test_nur_get(anna):
    services.avatar_waehlen(anna, "ritter", {})
    assert Client().post(services.bild_url(anna)).status_code == 405


def test_svg_endpunkt_ist_passiv_verlaengert_keine_sitzung():
    from apps.avatar import views
    from apps.konten.zugriff import ist_passiv

    assert ist_passiv(views.svg)


# --- Erstwahl -------------------------------------------------------------------------------------


def test_wahlseite_zeigt_zehn_themen_und_vorschau(kind_client):
    antwort = kind_client.get(reverse("avatar:kind_wahl"))
    assert antwort.status_code == 200
    inhalt = antwort.content.decode()
    assert inhalt.count('name="thema"') == 10
    assert inhalt.count("<svg") >= 11
    for name in ("Ritter", "Weltraum-Forscher", "Ninja", "Dschungel-Entdecker"):
        assert name in inhalt
    assert "style=" not in inhalt and "<script>" not in inhalt


def test_vorschau_per_htmx_ist_nur_ein_ausschnitt(kind_client):
    antwort = kind_client.get(
        reverse("avatar:kind_wahl") + "?thema=pirat&haut=haut5&frisur=lang",
        headers={"HX-Request": "true"},
    )
    inhalt = antwort.content.decode()
    assert "<html" not in inhalt
    assert 'value="pirat" checked' in inhalt


def test_ungueltige_vorschau_werte_fallen_auf_standard_zurueck(kind_client):
    antwort = kind_client.get(reverse("avatar:kind_wahl") + "?thema=x&haut=%3Cscript%3E")
    assert antwort.status_code == 200 and "<script>" not in antwort.content.decode()


def test_erstwahl_speichert_und_leitet_zum_dashboard(kind_client, anna):
    antwort = kind_client.post(
        reverse("avatar:kind_wahl"),
        {"thema": "ninja", "haut": "haut4", "haar": "haar2", "frisur": "struppig"},
    )
    assert antwort.status_code == 302 and antwort.url == reverse("oberflaeche:kind_heim")
    avatar = Avatar.objects.get(pk=anna.pk)
    assert avatar.thema.schluessel == "ninja" and avatar.figur["frisur"] == "struppig"


def test_erstwahl_ohne_thema_zeigt_fehler(kind_client):
    antwort = kind_client.post(reverse("avatar:kind_wahl"), {"haut": "haut1"})
    assert antwort.status_code == 200 and "Thema" in antwort.content.decode()
    assert not Avatar.objects.exists()


def test_ungueltige_figurwerte_werden_beim_speichern_auf_standard_gesetzt(kind_client, anna):
    kind_client.post(
        reverse("avatar:kind_wahl"), {"thema": "ritter", "haut": "boese", "frisur": "x"}
    )
    assert Avatar.objects.get(pk=anna.pk).figur == {
        "haut": "haut2",
        "haar": "haar3",
        "frisur": "kurz",
    }


def test_wahl_nur_einmal_danach_weiterleitung(kind_client, anna):
    services.avatar_waehlen(anna, "ritter", {})
    assert kind_client.get(reverse("avatar:kind_wahl")).status_code == 302
    kind_client.post(reverse("avatar:kind_wahl"), {"thema": "pirat"})
    assert Avatar.objects.get(pk=anna.pk).thema.schluessel == "ritter"


def test_eltern_und_anonyme_duerfen_nicht_waehlen(eltern_client):
    assert eltern_client.get(reverse("avatar:kind_wahl")).status_code in (302, 403)
    assert Client().get(reverse("avatar:kind_wahl")).status_code in (302, 403)
    assert not Avatar.objects.exists()


# --- Einbindung in Oberflächen -------------------------------------------------------------------


def test_kinderdashboard_zeigt_aufruf_ohne_avatar_und_figur_mit_avatar(kind_client, anna):
    inhalt = kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    assert 'data-kachel="avatar.kind_avatar"' in inhalt
    assert reverse("avatar:kind_wahl") in inhalt
    services.avatar_waehlen(anna, "pirat", {})
    inhalt = kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    assert 'data-kachel="avatar.kind_avatar"' not in inhalt
    assert 'class="avatar-bild avatar-bild--gross"' in inhalt
    assert "avatar-platz__buchstabe" not in inhalt


def test_tablet_und_startseite_zeigen_die_figuren(anna, ben, tablet):
    services.avatar_waehlen(anna, "ritter", {})
    services.avatar_waehlen(ben, "roboter", {"frisur": "lang"})
    c = client_fuer(tablet)
    inhalt = c.get(reverse("oberflaeche:tablet")).content.decode()
    assert inhalt.count('class="avatar-bild avatar-bild--gross"') == 2
    assert "Avatar von Anna" in inhalt and "avatar-platz__buchstabe" not in inhalt
    start = Client().get("/").content.decode()
    assert start.count("avatar-bild--gross") == 2


def test_eltern_kinderuebersicht_zeigt_figuren(eltern_client, anna):
    services.avatar_waehlen(anna, "wikinger", {})
    inhalt = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert "avatar-bild--klein" in inhalt
    assert inhalt.count("Avatar von Anna") == 1
    assert "Avatar von Mama" in inhalt  # Eltern-Avatar im Gruß


def test_seiten_mit_figuren_sind_csp_konform(eltern_client, kind_client):
    for antwort in (
        kind_client.get(reverse("oberflaeche:kind_heim")),
        eltern_client.get(reverse("oberflaeche:eltern_heim")),
    ):
        csp = antwort["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "unsafe-inline" not in csp
        inhalt = antwort.content.decode()
        assert "<svg" in inhalt
        assert " onload=" not in inhalt and "javascript:" not in inhalt


# --- Galerie --------------------------------------------------------------------------------------


def test_galerie_nur_im_debug_modus(settings):
    settings.DEBUG = False
    assert Client().get(reverse("avatar:galerie")).status_code == 404
    settings.DEBUG = True
    antwort = Client().get(reverse("avatar:galerie"))
    assert antwort.status_code == 200
    inhalt = antwort.content.decode()
    for name in (
        "Ritter",
        "Weltraum-Forscher",
        "Ninja",
        "Roboter",
        "Pirat",
        "Wikinger",
        "Fußballer",
        "Basketballer",
        "Rennfahrer",
        "Dschungel-Entdecker",
    ):
        assert name in inhalt
    assert inhalt.count("<svg") >= 20  # 10 Themen, dunkel und hell


def test_kleine_ansicht_zeigt_nur_kopf_und_schultern(anna):
    from django.template import Context, Template

    services.avatar_waehlen(anna, "ritter", {})
    vorlage = Template(
        '{% load avatar_tags %}{% avatar_bild b "klein" %}|{% avatar_bild b "gross" %}'
    )
    klein, gross = vorlage.render(Context({"b": anna})).split("|")
    assert 'viewBox="4 2 24 24"' in klein and 'viewBox="0 0 32 48"' in gross
    assert 'role="img" aria-label="Avatar von Anna"' in klein
