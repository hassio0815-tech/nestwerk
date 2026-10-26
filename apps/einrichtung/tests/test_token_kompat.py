def test_setup_token_alter_name(monkeypatch):
    """Bestehende Installationen setzen weiter FAMKO_SETUP_TOKEN."""
    from apps.einrichtung import zustand

    monkeypatch.delenv("NESTWERK_SETUP_TOKEN", raising=False)
    monkeypatch.setenv("FAMKO_SETUP_TOKEN", " abc ")
    assert zustand.erwartetes_token() == "abc"
