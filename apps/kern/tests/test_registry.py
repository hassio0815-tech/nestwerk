import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.kern.registry import Kachel, Metrik, Provider, UnbekannterEintrag


def test_kacheln_nach_zielgruppe_und_reihenfolge(leere_registry):
    r = leere_registry
    r.kachel_registrieren(Kachel("b.zwei", "b", "Zwei", "b/zwei.html", {r.KIND}, reihenfolge=20))
    r.kachel_registrieren(Kachel("a.eins", "a", "Eins", "a/eins.html", {r.KIND, r.TABLET}))
    r.kachel_registrieren(Kachel("c.drei", "c", "Drei", "c/drei.html", {r.ELTERN}, reihenfolge=5))
    assert [k.schluessel for k in r.kacheln(r.KIND)] == ["b.zwei", "a.eins"]
    assert [k.schluessel for k in r.kacheln(r.TABLET)] == ["a.eins"]
    assert [k.schluessel for k in r.kacheln(r.ELTERN)] == ["c.drei"]
    with pytest.raises(ValueError):
        r.kacheln("gast")


def test_kachel_braucht_gueltige_zielgruppe():
    with pytest.raises(ImproperlyConfigured):
        Kachel("a.x", "a", "X", "a/x.html", {"gast"})
    with pytest.raises(ImproperlyConfigured):
        Kachel("a.x", "a", "X", "a/x.html", set())


def test_doppelte_registrierung_ist_fehler(leere_registry):
    r = leere_registry
    r.metrik_registrieren(Metrik("avatar.ausbaustufe_voll", "avatar", "Ausbaustufe voll"))
    with pytest.raises(ImproperlyConfigured):
        r.metrik_registrieren(Metrik("avatar.ausbaustufe_voll", "avatar", "nochmal"))


def test_metriken(leere_registry):
    r = leere_registry
    r.metrik_registrieren(Metrik("avatar.ausbaustufe_voll", "avatar", "Ausbaustufe voll"))
    r.metrik_registrieren(Metrik("aufgaben.erledigt", "aufgaben", "Erledigte Aufgaben"))
    assert r.metrik("avatar.ausbaustufe_voll").bezeichnung == "Ausbaustufe voll"
    assert [m.schluessel for m in r.metriken()] == ["aufgaben.erledigt", "avatar.ausbaustufe_voll"]
    assert [m.schluessel for m in r.metriken("avatar")] == ["avatar.ausbaustufe_voll"]
    with pytest.raises(UnbekannterEintrag):
        r.metrik("lernen.minuten")


def test_fortschritts_provider(leere_registry):
    r = leere_registry
    r.provider_registrieren(
        Provider(
            "avatar.ausbaustufe_fortschritt",
            "avatar",
            "Ausbaustufe",
            lambda kind: {"kind": kind, "fehlend": 2},
        )
    )
    assert r.provider_vorhanden("avatar.ausbaustufe_fortschritt")
    assert r.fortschritt("avatar.ausbaustufe_fortschritt", "Anna") == {"kind": "Anna", "fehlend": 2}
    assert not r.provider_vorhanden("lernen.fortschritt")
    with pytest.raises(UnbekannterEintrag):
        r.fortschritt("lernen.fortschritt", "Anna")


def test_isoliert_setzt_zurueck(leere_registry):
    r = leere_registry
    with r.isoliert():
        r.metrik_registrieren(Metrik("x.y", "x", "XY"))
        assert len(r.metriken()) == 1
    assert r.metriken() == []
