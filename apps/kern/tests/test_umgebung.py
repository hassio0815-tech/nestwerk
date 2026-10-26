import importlib

import pytest

from apps.kern.umgebung import umgebung


def test_neuer_praefix_hat_vorrang(monkeypatch):
    monkeypatch.setenv("FAMKO_BEISPIEL", "alt")
    monkeypatch.setenv("NESTWERK_BEISPIEL", "neu")
    assert umgebung("BEISPIEL") == "neu"


def test_alter_praefix_als_fallback(monkeypatch):
    monkeypatch.delenv("NESTWERK_BEISPIEL", raising=False)
    monkeypatch.setenv("FAMKO_BEISPIEL", "alt")
    assert umgebung("BEISPIEL") == "alt"


def test_standardwert(monkeypatch):
    monkeypatch.delenv("NESTWERK_BEISPIEL", raising=False)
    monkeypatch.delenv("FAMKO_BEISPIEL", raising=False)
    assert umgebung("BEISPIEL", "std") == "std"
    assert umgebung("BEISPIEL") is None


@pytest.mark.parametrize(
    ("alt_vorhanden", "neu_vorhanden", "erwartet"),
    [
        (True, False, "famko.sqlite3"),
        (True, True, "nestwerk.sqlite3"),
        (False, False, "nestwerk.sqlite3"),
    ],
)
def test_datenbankdatei_bestehender_installation(
    monkeypatch, tmp_path, alt_vorhanden, neu_vorhanden, erwartet
):
    (tmp_path / "db").mkdir()
    if alt_vorhanden:
        (tmp_path / "db" / "famko.sqlite3").write_bytes(b"")
    if neu_vorhanden:
        (tmp_path / "db" / "nestwerk.sqlite3").write_bytes(b"")
    monkeypatch.delenv("NESTWERK_DATA_DIR", raising=False)
    monkeypatch.setenv("FAMKO_DATA_DIR", str(tmp_path))  # alter Name als Fallback
    from nestwerk.settings import basis

    try:
        neu = importlib.reload(basis)
        assert neu.DATABASES["default"]["NAME"].name == erwartet
    finally:
        monkeypatch.undo()
        importlib.reload(basis)
