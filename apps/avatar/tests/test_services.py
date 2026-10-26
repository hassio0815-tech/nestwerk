from datetime import timedelta

import pytest

from apps.avatar import selectors, services
from apps.avatar.generator import bibliothek, renderer
from apps.avatar.models import Avatar, ModDefinition, RenderCache

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leerer_speicher():
    services._SPEICHER.clear()


def test_erstwahl_legt_avatar_und_cache_an(anna):
    avatar = services.avatar_waehlen(
        anna, "ritter", {"haut": "haut3", "haar": "haar1", "frisur": "lang"}
    )
    assert avatar.thema.schluessel == "ritter"
    assert avatar.figur == {"haut": "haut3", "haar": "haar1", "frisur": "lang"}
    assert len(avatar.render_hash) == 64
    assert RenderCache.objects.filter(pk=avatar.render_hash).exists()
    assert selectors.hat_avatar(anna)


def test_erstwahl_nur_einmal(anna):
    services.avatar_waehlen(anna, "ritter", {})
    with pytest.raises(services.AvatarFehler, match="schon"):
        services.avatar_waehlen(anna, "pirat", {})
    assert Avatar.objects.get(pk=anna.pk).thema.schluessel == "ritter"


@pytest.mark.parametrize(
    "thema, figur",
    [
        ("eltern", {}),
        ("gibtsnicht", {}),
        ("", {}),
        ("ritter", {"haut": "haut99"}),
        ("ritter", {"haar": "x"}),
        ("ritter", {"frisur": "glatze"}),
    ],
)
def test_erstwahl_prueft_eingaben(anna, thema, figur):
    with pytest.raises(services.AvatarFehler):
        services.avatar_waehlen(anna, thema, figur)
    assert not Avatar.objects.exists()


def test_eltern_waehlen_keinen_avatar(mama):
    with pytest.raises(services.AvatarFehler):
        services.avatar_waehlen(mama, "ritter", {})


def test_slot_belegen_aendert_hash_und_bild(anna):
    avatar = services.avatar_waehlen(anna, "ritter", {})
    vorher = avatar.render_hash
    svg_vorher = services.svg_fuer(anna)[1]
    services.slot_belegen(anna, "kopf", "ritter-kopf-1")
    avatar.refresh_from_db()
    assert avatar.angelegt == {"kopf": "ritter-kopf-1"}
    assert avatar.render_hash != vorher
    assert services.svg_fuer(anna)[1] != svg_vorher
    services.slot_leeren(anna, "kopf")
    avatar.refresh_from_db()
    assert avatar.render_hash == vorher and avatar.angelegt == {}


def test_slot_belegen_prueft_slot_thema_und_status(anna):
    services.avatar_waehlen(anna, "pirat", {})
    with pytest.raises(services.AvatarFehler, match="Thema"):
        services.slot_belegen(anna, "kopf", "ritter-kopf-1")
    with pytest.raises(services.AvatarFehler, match="Slot"):
        services.slot_belegen(anna, "hand", "ritter-kopf-1")
    with pytest.raises(services.AvatarFehler, match="Unbekannt"):
        services.slot_belegen(anna, "kopf", "gibtsnicht")


def test_inaktiver_mod_nicht_belegbar(anna):
    services.avatar_waehlen(anna, "ritter", {})
    ModDefinition.objects.filter(schluessel="ritter-kopf-1").update(aktiv=False)
    with pytest.raises(services.AvatarFehler, match="verfügbar"):
        services.slot_belegen(anna, "kopf", "ritter-kopf-1")


def test_figur_aendern(anna):
    avatar = services.avatar_waehlen(anna, "ritter", {})
    vorher = avatar.render_hash
    services.figur_aendern(anna, {"haut": "haut6", "haar": "haar8", "frisur": "struppig"})
    avatar.refresh_from_db()
    assert avatar.figur["haut"] == "haut6" and avatar.render_hash != vorher
    with pytest.raises(services.AvatarFehler):
        services.figur_aendern(anna, {"haut": "nope"})


def test_cache_trifft_und_rendert_nur_einmal(anna, monkeypatch):
    services.avatar_waehlen(anna, "ritter", {})
    aufrufe = []
    original = renderer.rendern
    monkeypatch.setattr(renderer, "rendern", lambda z: aufrufe.append(1) or original(z))
    services._SPEICHER.clear()
    a = services.svg_fuer(anna)
    b = services.svg_fuer(anna)
    assert a == b and aufrufe == []  # Hash steht am Avatar, Bild kommt aus dem Cache
    RenderCache.objects.all().delete()
    services._SPEICHER.clear()
    c = services.svg_fuer(anna)
    assert c == a and aufrufe == [1]  # nach Verlust des Caches wird neu gerendert


def test_gleiche_eingabe_teilt_sich_eine_cache_zeile(anna, ben):
    services.avatar_waehlen(anna, "ritter", {})
    services.avatar_waehlen(ben, "ritter", {})
    assert Avatar.objects.get(pk=anna.pk).render_hash == Avatar.objects.get(pk=ben.pk).render_hash
    assert RenderCache.objects.count() == 1


def test_eltern_figur_ohne_datenbankeintrag_und_stabil(mama, papa):
    h1, svg1 = services.svg_fuer(mama)
    h2, _ = services.svg_fuer(mama)
    assert h1 == h2
    assert not Avatar.objects.exists()
    assert svg1.startswith("<svg")
    z = services.eltern_zustand(mama)
    assert z["thema"] == "eltern" and "mods" not in z
    assert z["figur"]["haut"] in bibliothek.ELTERN_HAUT


def test_kind_ohne_wahl_bekommt_neutrale_figur(anna):
    h, svg = services.svg_fuer(anna)
    assert svg.startswith("<svg")
    assert h == renderer.hash_von(services.NEUTRAL)


def test_bild_url_enthaelt_den_hash(anna):
    h, _ = services.svg_fuer(anna)
    assert services.bild_url(anna) == f"/avatar/{h}.svg"


def test_defekter_mod_kippt_das_bild_nicht(anna):
    avatar = services.avatar_waehlen(anna, "ritter", {})
    services.slot_belegen(anna, "kopf", "ritter-kopf-1")
    services.slot_belegen(anna, "hand", "ritter-hand-1")
    ModDefinition.objects.filter(schluessel="ritter-kopf-1").update(
        svg_override='<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>'
    )
    avatar.refresh_from_db()
    h, svg = services.hash_aktualisieren(avatar)
    assert "<script" not in svg
    ohne_kopf = renderer.hash_von(
        {
            **services.zustand_von(avatar),
            "mods": {"hand": services.zustand_von(avatar)["mods"]["hand"]},
        }
    )
    assert h == ohne_kopf


def test_cache_aufraeumen_loescht_nur_verwaiste_alte(anna, uhr, monkeypatch):
    from apps.kern import zeit

    avatar = services.avatar_waehlen(anna, "ritter", {})
    RenderCache.objects.create(hash="a" * 64, svg="<svg/>")
    RenderCache.objects.create(hash="b" * 64, svg="<svg/>")
    spaeter = zeit.jetzt() + timedelta(days=40)
    monkeypatch.setattr(zeit, "jetzt", lambda: spaeter)
    RenderCache.objects.filter(pk="b" * 64).update(zuletzt_genutzt=spaeter)
    assert services.cache_aufraeumen(tage=30) == 1
    assert set(RenderCache.objects.values_list("pk", flat=True)) == {avatar.render_hash, "b" * 64}
