"""Deterministik (Snapshots), Leistung, alle Themen, Sicherheit der Ausgabe."""

import os
import re
import time
from pathlib import Path

import pytest

from apps.avatar.generator import bauplaene, bibliothek, renderer, svgsicher

SNAPSHOTS = Path(__file__).parent / "snapshots"
THEMEN = sorted(bibliothek.themen())


def ritter_komplett():
    plaene = [p for p in bibliothek.bauplaene_aus_dateien() if p["thema"] == "ritter"]
    mods = {
        p["slot"]: {"teile": p["teile"], "svg_override": None}
        for p in plaene
        if p["seltenheit"] == 1
    }
    return {
        "thema": "ritter",
        "figur": {"haut": "haut3", "haar": "haar2", "frisur": "struppig"},
        "mods": mods,
    }


FAELLE = {
    "ritter_grund": {"thema": "ritter"},
    "weltraum_grund_lang": {
        "thema": "weltraum",
        "figur": {"haut": "haut5", "haar": "haar7", "frisur": "lang"},
    },
    "eltern_grund": {
        "thema": "eltern",
        "figur": {"haut": "haut1", "haar": "haar4", "frisur": "kurz"},
    },
    "ritter_komplett": ritter_komplett(),
}


@pytest.mark.parametrize("name", sorted(FAELLE))
def test_snapshot(name):
    """Byte-gleiche Ausgabe. Nach bewusster Änderung neu erzeugen: AVATAR_SNAPSHOT_UPDATE=1."""
    svg = renderer.rendern(FAELLE[name])
    datei = SNAPSHOTS / f"{name}.svg"
    if os.environ.get("AVATAR_SNAPSHOT_UPDATE") == "1":
        SNAPSHOTS.mkdir(exist_ok=True)
        datei.write_text(svg, encoding="utf-8")
    assert datei.read_text(encoding="utf-8") == svg, f"Snapshot {name} weicht ab"


def test_gleiche_eingabe_gleiches_svg_und_gleicher_hash():
    z = ritter_komplett()
    a, b = renderer.rendern(z), renderer.rendern(dict(z))
    assert a == b
    assert renderer.hash_von(z) == renderer.hash_von({**z, "figur": dict(z["figur"])})
    assert a.encode() == b.encode()


def test_reihenfolge_der_schluessel_ist_egal():
    a = {"thema": "ritter", "figur": {"haut": "haut1", "haar": "haar1", "frisur": "kurz"}}
    b = {"figur": {"frisur": "kurz", "haar": "haar1", "haut": "haut1"}, "thema": "ritter"}
    assert renderer.hash_von(a) == renderer.hash_von(b)
    assert renderer.rendern(a) == renderer.rendern(b)


def test_standardfigur_gleich_ausdrueckliche_standardfigur():
    assert renderer.hash_von({"thema": "ninja"}) == renderer.hash_von(
        {"thema": "ninja", "figur": bibliothek.STANDARD_FIGUR}
    )


def test_aenderungen_aendern_den_hash():
    basis = renderer.hash_von({"thema": "ritter"})
    assert renderer.hash_von({"thema": "pirat"}) != basis
    assert renderer.hash_von({"thema": "ritter", "figur": {"haut": "haut6"}}) != basis
    assert renderer.hash_von(ritter_komplett()) != basis


@pytest.mark.parametrize("thema", THEMEN)
def test_jedes_thema_rendert_die_grundfigur(thema):
    figur = bibliothek.figur()
    for frisur in figur["frisuren"]:
        svg = renderer.rendern({"thema": thema, "figur": {"frisur": frisur}})
        assert svg.startswith("<svg ") and svg.endswith("</svg>")
        assert svgsicher.svg_pruefen(svg) is None
    for haut in figur["hautfarben"]:
        renderer.rendern({"thema": thema, "figur": {"haut": haut}})
    for haar in figur["haarfarben"]:
        renderer.rendern({"thema": thema, "figur": {"haar": haar}})


def test_es_gibt_zehn_kinder_themen_und_ein_eltern_thema():
    assert len(bibliothek.kind_themen()) == 10
    assert {t["schluessel"] for t in bibliothek.kind_themen()} == {
        "ritter",
        "weltraum",
        "ninja",
        "roboter",
        "pirat",
        "wikinger",
        "fussballer",
        "basketballer",
        "rennfahrer",
        "dschungel",
    }
    assert bibliothek.thema("eltern")["nur_eltern"] is True
    assert len(bibliothek.slot_schluessel()) == 6


def test_render_dauert_unter_50_ms_ohne_cache():
    z = ritter_komplett()
    messungen = []
    for _ in range(20):
        start = time.perf_counter()
        renderer.rendern(z)
        messungen.append((time.perf_counter() - start) * 1000)
    assert max(messungen) < 50, messungen


def test_ausgabe_ohne_skript_style_und_externe_referenzen():
    svg = renderer.rendern(ritter_komplett())
    for verboten in (
        "<script",
        "onload",
        "href",
        "style=",
        "foreignObject",
        "http://",
        "https://",
        "url(",
    ):
        assert verboten not in svg.replace("http://www.w3.org/2000/svg", "")
    assert svg.count("<svg") == 1


def test_alle_formen_aller_slots_mit_allen_mustern():
    for slot in bibliothek.slot_schluessel():
        for form in bibliothek.formen(slot):
            for muster in bibliothek.MUSTER:
                z = {
                    "thema": "pirat",
                    "mods": {slot: {"teile": [bauplaene.teile_probe(form, muster)]}},
                }
                assert svgsicher.svg_pruefen(renderer.rendern(z)) is None


def test_mod_aendert_das_bild_nur_im_eigenen_slot():
    ohne = renderer.rendern({"thema": "ritter"})
    mit = renderer.rendern(
        {"thema": "ritter", "mods": {"hand": {"teile": [bauplaene.teile_probe("hammer")]}}}
    )
    assert ohne != mit


def test_spiegeln_und_versatz():
    a = renderer.rendern({"thema": "ritter", "mods": {"hand": {"teile": [{"form": "schwert"}]}}})
    b = renderer.rendern(
        {"thema": "ritter", "mods": {"hand": {"teile": [{"form": "schwert", "spiegeln": True}]}}}
    )
    c = renderer.rendern(
        {"thema": "ritter", "mods": {"hand": {"teile": [{"form": "schwert", "dx": 2}]}}}
    )
    assert len({a, b, c}) == 3


def test_ausserhalb_des_rasters_wird_beschnitten():
    svg = renderer.rendern(
        {"thema": "ritter", "mods": {"hand": {"teile": [{"form": "schwert", "dx": -8}]}}}
    )
    assert not re.search(r"M-\d|M\d+ -\d", svg)
    assert svgsicher.svg_pruefen(svg) is None


@pytest.mark.parametrize(
    "zustand",
    [
        {"thema": "gibtsnicht"},
        {"thema": "ritter", "figur": {"haut": "haut99"}},
        {"thema": "ritter", "figur": {"frisur": "irokese"}},
        {"thema": "ritter", "mods": {"kopf": {"teile": [{"form": "gibtsnicht"}]}}},
        {"thema": "ritter", "mods": {"kopf": {"teile": [{"form": "kappe", "muster": "zebra"}]}}},
        {
            "thema": "ritter",
            "mods": {"kopf": {"teile": [{"form": "kappe", "farben": {"a": "rot"}}]}},
        },
        {
            "thema": "ritter",
            "mods": {"kopf": {"teile": [{"form": "kappe", "farben": {"z": "p1"}}]}},
        },
        {"thema": "ritter", "mods": {"kopf": {"teile": [{"form": "kappe", "dx": 99}]}}},
        {"thema": "ritter", "mods": {"unbekannt": {"teile": [{"form": "kappe"}]}}},
        {"thema": "ritter", "mods": {"kopf": {"teile": [{"form": "kappe"}] * 7}}},
    ],
)
def test_ungueltige_eingaben_werfen_renderfehler(zustand):
    with pytest.raises(renderer.RenderFehler):
        renderer.rendern(zustand)


def test_override_ersetzt_den_mod_und_wird_geprueft():
    gut = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 48">'
        '<rect x="4" y="4" width="6" height="6" fill="#ff0000"/></svg>'
    )
    svg = renderer.rendern(
        {"thema": "ritter", "mods": {"hand": {"teile": [], "svg_override": gut}}}
    )
    assert '<rect fill="#ff0000" height="6" width="6" x="4" y="4"/>' in svg
    assert svgsicher.svg_pruefen(svg) is None
    boese = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(renderer.RenderFehler, match="script"):
        renderer.rendern(
            {"thema": "ritter", "mods": {"hand": {"teile": [], "svg_override": boese}}}
        )
