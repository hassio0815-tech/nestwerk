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


# --- Etappe 4: lesen, Inbox-Blick, Übernehmen ----------------------------------------------------


def test_lesen(speicher):
    speicher.speichern(3, "inbox", "a.txt", b"Hallo")
    assert speicher.lesen(3, "inbox", "a.txt") == b"Hallo"
    assert speicher.lesen(3, "inbox", "a.txt", max_bytes=2) == b"Hal"  # eins mehr als erlaubt
    with pytest.raises(FileNotFoundError):
        speicher.lesen(3, "inbox", "gibts-nicht.txt")
    with pytest.raises(SpeicherFehler):
        speicher.lesen(3, "inbox", "../a.txt")


def test_inbox_dateien_und_uebernehmen(speicher, tmp_path):
    speicher.ordner_anlegen(4)
    inbox = speicher.ordner(4, "inbox")
    (inbox / "a.txt").write_bytes(b"A")
    (inbox / "mathe").mkdir()
    (inbox / "mathe" / "b.txt").write_bytes(b"BB")
    (inbox / "mathe" / "tief").mkdir()
    (inbox / "mathe" / "tief" / "c.txt").write_bytes(b"C")
    (inbox / ".versteckt").write_bytes(b"x")
    fremd = tmp_path / "fremd.txt"
    fremd.write_bytes(b"F")
    os.symlink(fremd, inbox / "link.txt")
    os.symlink(tmp_path, inbox / "linkordner")
    gefunden = {(d.hinweis, d.name, d.groesse) for d in speicher.inbox_dateien(4)}
    assert gefunden == {("", "a.txt", 1), ("mathe", "b.txt", 2)}
    datei = next(d for d in speicher.inbox_dateien(4) if d.name == "b.txt")
    ziel = speicher.uebernehmen(4, datei.pfad, "archiv", "neutral.txt")
    assert ziel.read_bytes() == b"BB" and not datei.pfad.exists()
    with pytest.raises(FileExistsError):
        speicher.uebernehmen(4, inbox / "a.txt", "archiv", "neutral.txt")
    with pytest.raises(FileNotFoundError):
        speicher.uebernehmen(4, inbox / "link.txt", "archiv", "x.txt")  # Symlink
    with pytest.raises(FileNotFoundError):
        speicher.uebernehmen(4, inbox / "weg.txt", "archiv", "x.txt")
    with pytest.raises(SpeicherFehler):
        speicher.uebernehmen(4, fremd, "archiv", "y.txt")  # außerhalb der inbox
    assert fremd.read_bytes() == b"F"


def test_inbox_dateien_ohne_ordner(speicher):
    assert speicher.inbox_dateien(9) == []
