"""Eltern wählen Avatar (Haut, Haar, Frisur, Outfit): Speichern, Rechte, Anzeige, Outfits."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.avatar import selectors, services
from apps.avatar.generator import bibliothek, renderer, svgsicher
from apps.avatar.models import ElternAvatar

from .conftest import angemeldet

pytestmark = pytest.mark.django_db

OUTFITS = [t["schluessel"] for t in bibliothek.eltern_outfits() if t["schluessel"] != "eltern"]
FIGUR = {"haut": "haut5", "haar": "haar7", "frisur": "lang"}


def _koerper(svg):
    return svg.split('shape-rendering="crispEdges">', 1)[1]


def test_es_gibt_zehn_eltern_outfits_nur_fuer_eltern():
    assert len(OUTFITS) == 10
    assert {"eltern_it", "eltern_maker"} <= set(OUTFITS)
    for schluessel in OUTFITS:
        assert bibliothek.thema(schluessel)["nur_eltern"] is True
        assert schluessel not in {t["schluessel"] for t in bibliothek.kind_themen()}
        assert schluessel not in {t.schluessel for t in selectors.waehlbare_themen()}
    assert bibliothek.eltern_outfits()[0]["schluessel"] == "eltern"


@pytest.mark.parametrize("outfit", OUTFITS)
def test_jedes_outfit_rendert_gueltiges_svg(outfit):
    figur = bibliothek.figur()
    for schluessel, werte in (
        ("haut", figur["hautfarben"]),
        ("haar", figur["haarfarben"]),
        ("frisur", figur["frisuren"]),
    ):
        for wert in werte:
            svg = renderer.rendern({"thema": outfit, "figur": {schluessel: wert}})
            assert svgsicher.svg_pruefen(svg) is None
    assert renderer.rendern({"thema": outfit}) != renderer.rendern({"thema": "eltern"})


def test_ohne_wahl_bleibt_die_hash_figur(mama):
    assert not ElternAvatar.objects.exists()
    erwartet = renderer.rendern(services.eltern_standard_zustand(mama))
    assert services.svg_fuer(mama)[1] == erwartet
    assert services.eltern_zustand(mama)["thema"] == "eltern"


def test_eltern_koennen_waehlen_und_speichern(eltern_client, mama):
    antwort = eltern_client.post(reverse("avatar:eltern_wahl"), {**FIGUR, "outfit": "eltern_rock"})
    assert antwort.status_code == 302
    wahl = ElternAvatar.objects.get(pk=mama.pk)
    assert (wahl.outfit, wahl.figur) == ("eltern_rock", FIGUR)
    hash_, svg = services.svg_fuer(mama)
    assert hash_ == wahl.render_hash
    assert svg == renderer.rendern({"thema": "eltern_rock", "figur": FIGUR})
    seite = eltern_client.get(reverse("avatar:eltern_wahl")).content.decode()
    assert 'value="eltern_rock" checked' in seite and 'value="haut5" checked' in seite


def test_wahl_aendert_den_render_hash(mama):
    vorher = services.svg_fuer(mama)[0]
    services.eltern_avatar_waehlen(mama, "eltern_it", FIGUR)
    erster = services.svg_fuer(mama)[0]
    services.eltern_avatar_waehlen(mama, "eltern_koch", FIGUR)
    zweiter = services.svg_fuer(mama)[0]
    assert len({vorher, erster, zweiter}) == 3
    assert ElternAvatar.objects.get(pk=mama.pk).render_hash == zweiter
    assert Client().get(services.bild_url(mama)).status_code == 200


def test_ungueltige_wahl_wird_abgewiesen(mama):
    for outfit in ("ritter", "gibtsnicht", ""):
        with pytest.raises(services.AvatarFehler):
            services.eltern_avatar_waehlen(mama, outfit, FIGUR)
    with pytest.raises(services.AvatarFehler):
        services.eltern_avatar_waehlen(mama, "eltern_it", {"haut": "haut99"})
    assert not ElternAvatar.objects.exists()


def test_kind_kann_kein_eltern_outfit_setzen(anna):
    with pytest.raises(services.AvatarFehler):
        services.avatar_waehlen(anna, "eltern_it", {})
    with pytest.raises(services.AvatarFehler):
        services.eltern_avatar_waehlen(anna, "eltern_it", FIGUR)
    services.avatar_waehlen(anna, "ritter", {})
    with pytest.raises(services.ModFehler):
        services.thema_wechseln(anna, "eltern_it", pruefwert="")


def test_eltern_route_fuer_kinder_verboten(kind_client):
    assert kind_client.get(reverse("avatar:eltern_wahl")).status_code == 403
    antwort = kind_client.post(reverse("avatar:eltern_wahl"), {"outfit": "eltern_it"})
    assert antwort.status_code == 403
    assert not ElternAvatar.objects.exists()


def test_kinder_sehen_eltern_outfits_nicht(kind_client):
    html = kind_client.get(reverse("avatar:kind_wahl")).content.decode()
    assert "IT-Admin" not in html and "eltern_it" not in html


def test_live_vorschau_per_htmx(eltern_client):
    antwort = eltern_client.get(
        reverse("avatar:eltern_wahl"),
        {"outfit": "eltern_held", "haut": "haut2"},
        HTTP_HX_REQUEST="true",
    )
    html = antwort.content.decode()
    assert antwort.status_code == 200 and "<html" not in html
    assert "Superheld" in html and 'value="eltern_held" checked' in html


def test_einstellungen_verlinken_den_avatar(eltern_client):
    html = eltern_client.get(reverse("oberflaeche:einstellungen")).content.decode()
    assert reverse("avatar:eltern_wahl") in html


def test_anzeige_nutzt_die_gewaehlte_figur(mama):
    services.eltern_avatar_waehlen(mama, "eltern_zauberer", FIGUR)
    erwartet = _koerper(renderer.rendern({"thema": "eltern_zauberer", "figur": FIGUR}))
    standard = _koerper(renderer.rendern(services.eltern_standard_zustand(mama)))
    for name in ("oberflaeche:eltern_heim", "oberflaeche:familie"):
        html = angemeldet(Client(), mama).get(reverse(name)).content.decode()
        assert erwartet in html, name
        assert standard not in html, name


def test_cache_aufraeumen_behaelt_eltern_bilder(mama):
    services.eltern_avatar_waehlen(mama, "eltern_chill", FIGUR)
    hash_ = ElternAvatar.objects.get(pk=mama.pk).render_hash
    from datetime import timedelta

    from apps.avatar.models import RenderCache
    from apps.kern import zeit

    RenderCache.objects.filter(pk=hash_).update(zuletzt_genutzt=zeit.jetzt() - timedelta(days=90))
    services.cache_aufraeumen()
    assert RenderCache.objects.filter(pk=hash_).exists()
