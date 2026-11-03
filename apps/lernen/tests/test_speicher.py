"""Speicher-Backend: Ordner je Kind, Pfadsicherheit, Limit (SPEC 21.5)."""

import os
from uuid import uuid4

import pytest

from apps.lernen.speicher import BEREICHE, Speicher, SpeicherFehler, SpeicherVoll


@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "lernen")


def test_ordner_anlegen_ist_idempotent(speicher):
    speicher.ordner_anlegen(7)
    speicher.ordner_anlegen(7)
    for bereich in BEREICHE:
        assert speicher.ordner(7, bereich).is_dir()
    assert speicher.kind_ordner(7).name == "kind_7"


def test_standard_basis_aus_settings(settings, tmp_path):
    settings.LERNEN_SPEICHER_DIR = tmp_path / "nas"
    assert Speicher().basis == (tmp_path / "nas").resolve()


def test_uuid_als_kind_id(speicher):
    kind_id = uuid4()
    speicher.ordner_anlegen(kind_id)
    assert speicher.kind_ordner(kind_id).name == f"kind_{kind_id}"


def test_kinder_haben_getrennte_ordner(speicher):
    speicher.speichern(1, "inbox", "a.txt", b"eins")
    speicher.speichern(2, "inbox", "a.txt", b"zwei")
    assert speicher.pfad(1, "inbox", "a.txt").read_bytes() == b"eins"
    assert speicher.pfad(2, "inbox", "a.txt").read_bytes() == b"zwei"


@pytest.mark.parametrize(
    "name", ["../x", "..", ".", "", "a/b", "/etc/passwd", "a\\b", ".versteckt", "a\x00b", None]
)
def test_unzulaessige_dateinamen(speicher, name):
    with pytest.raises(SpeicherFehler):
        speicher.pfad(1, "inbox", name)


@pytest.mark.parametrize("bereich", ["../kind_2/inbox", "", "INBOX", "archiv/..", None])
def test_unzulaessige_bereiche(speicher, bereich):
    with pytest.raises(SpeicherFehler):
        speicher.ordner(1, bereich)


@pytest.mark.parametrize("kind_id", [0, -1, "1", "../2", None, True, 1.5])
def test_unzulaessige_kind_ids(speicher, kind_id):
    with pytest.raises(SpeicherFehler):
        speicher.kind_ordner(kind_id)


def test_symlink_ausbruch_wird_abgewiesen(speicher, tmp_path):
    speicher.ordner_anlegen(1)
    aussen = tmp_path / "geheim.txt"
    aussen.write_text("geheim")
    os.symlink(aussen, speicher.ordner(1, "inbox") / "link.txt")
    with pytest.raises(SpeicherFehler):
        speicher.pfad(1, "inbox", "link.txt")
    # auch ein Ordner-Symlink bricht nicht aus
    os.symlink(tmp_path, speicher.kind_ordner(2))
    with pytest.raises(SpeicherFehler):
        speicher.ordner(2, "inbox")


def test_speichern_ueberschreibt_nie(speicher):
    speicher.speichern(1, "inbox", "a.txt", b"x")
    with pytest.raises(FileExistsError):
        speicher.speichern(1, "inbox", "a.txt", b"y")
    assert speicher.pfad(1, "inbox", "a.txt").read_bytes() == b"x"


def test_belegung_und_limit(speicher):
    assert speicher.belegt_bytes(1) == 0
    speicher.speichern(1, "inbox", "a.bin", b"x" * 600)
    speicher.speichern(1, "archiv", "b.bin", b"x" * 300)
    assert speicher.belegt_bytes(1) == 900
    assert speicher.belegt_bytes(2) == 0
    with pytest.raises(SpeicherVoll):
        speicher.speichern(1, "tests", "c.bin", b"x" * 101, limit_bytes=1000)
    assert not speicher.pfad(1, "tests", "c.bin").exists()
    speicher.speichern(1, "tests", "c.bin", b"x" * 100, limit_bytes=1000)


def test_verschieben_und_loeschen(speicher):
    speicher.speichern(1, "inbox", "a.txt", b"x")
    ziel = speicher.verschieben(1, "a.txt", "inbox", "archiv")
    assert ziel.read_bytes() == b"x"
    assert not speicher.pfad(1, "inbox", "a.txt").exists()
    with pytest.raises(FileNotFoundError):
        speicher.verschieben(1, "a.txt", "inbox", "archiv")
    assert speicher.loeschen(1, "archiv", "a.txt") is True
    assert speicher.loeschen(1, "archiv", "a.txt") is False
