"""Adapter gegen einen lokalen Fake-Server (kein echtes Netz, keine echten Schlüssel)."""

import json
import socket

import pytest

from apps.lernen import ki
from apps.lernen.ki import (
    KiAnfrage,
    KiAnfrageFehler,
    KiAusgabeFehler,
    KiAuthFehler,
    KiBild,
    KiKonfigurationsFehler,
    KiLimitFehler,
    KiServerFehler,
    KiVerbindungsFehler,
    KiZeitueberschreitung,
    basis,
    transport,
)

from .ki_fake import FakeServer, anthropic_antwort, openai_antwort

SCHLUESSEL = "test-schluessel-nicht-echt"


@pytest.fixture
def server():
    with FakeServer() as s:
        yield s


def _anfrage(**kw):
    kw.setdefault("system", "Du bist ein Test.")
    kw.setdefault("nachricht", "Hallo")
    kw.setdefault("timeout", 5)
    return KiAnfrage(**kw)


def _kompatibel(server, key=""):
    return ki.adapter_erzeugen(
        "openai_kompatibel", basis_url=server.url + "/v1", modell="testmodell", api_key=key
    )


# --- OpenAI-kompatibel ---------------------------------------------------------------------------


def test_kompatibel_chat_ohne_key(server):
    server.antwort(openai_antwort("Hi", 7, 2))
    antwort = _kompatibel(server).chat(_anfrage())
    pfad, header, body = server.anfragen[0]
    assert pfad == "/v1/chat/completions"
    assert "authorization" not in header
    assert body["model"] == "testmodell"
    assert body["messages"][0] == {"role": "system", "content": "Du bist ein Test."}
    assert body["messages"][1] == {"role": "user", "content": "Hallo"}
    assert body["max_tokens"] == 1024
    assert "response_format" not in body
    assert (antwort.text, antwort.tokens_ein, antwort.tokens_aus, antwort.json) == (
        "Hi",
        7,
        2,
        None,
    )


def test_kompatibel_mit_key_bild_und_json(server):
    server.antwort(openai_antwort('{"a": 1}'))
    bild = KiBild("image/png", b"\x89PNGdaten")
    antwort = _kompatibel(server, SCHLUESSEL).chat(
        _anfrage(bilder=(bild,), json_ausgabe=True, schema={"type": "object"})
    )
    _, header, body = server.anfragen[0]
    assert header["authorization"] == f"Bearer {SCHLUESSEL}"
    inhalt = body["messages"][1]["content"]
    assert inhalt[0] == {"type": "text", "text": "Hallo"}
    assert inhalt[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON" in body["messages"][0]["content"] and '"object"' in body["messages"][0]["content"]
    assert antwort.json == {"a": 1}


def test_kompatibel_ohne_system_und_teile_als_liste(server):
    server.antwort({"choices": [{"message": {"content": [{"text": "A"}, {"text": "B"}, 5]}}]})
    antwort = _kompatibel(server).chat(_anfrage(system=""))
    assert server.anfragen[0][2]["messages"][0]["role"] == "user"
    assert antwort.text == "AB"
    assert antwort.tokens_ein is None


@pytest.mark.parametrize(
    ("status", "klasse"),
    [
        (401, KiAuthFehler),
        (403, KiAuthFehler),
        (429, KiLimitFehler),
        (408, KiZeitueberschreitung),
        (504, KiZeitueberschreitung),
        (500, KiServerFehler),
        (503, KiServerFehler),
        (400, KiAnfrageFehler),
        (404, KiAnfrageFehler),
    ],
)
def test_statuscodes_werden_fehlerklassen(server, status, klasse):
    server.antwort({"error": {"message": f"geheim {SCHLUESSEL}"}}, status=status)
    with pytest.raises(klasse) as exc:
        _kompatibel(server, SCHLUESSEL).chat(_anfrage())
    assert exc.value.status == status
    assert SCHLUESSEL not in str(exc.value) and SCHLUESSEL not in repr(exc.value)


def test_wiederholbarkeit_der_fehlerklassen():
    assert all(
        k.wiederholbar
        for k in (KiVerbindungsFehler, KiZeitueberschreitung, KiLimitFehler, KiServerFehler)
    )
    assert not any(k.wiederholbar for k in (KiAuthFehler, KiAnfrageFehler, KiKonfigurationsFehler))


@pytest.mark.parametrize(
    "body", ["kein json", {"choices": []}, {"choices": [{"message": {"content": "  "}}]}, [1], None]
)
def test_unbrauchbare_antworten(server, body):
    server.antwort("" if body is None else body)
    with pytest.raises(KiAusgabeFehler):
        _kompatibel(server).chat(_anfrage())


def test_json_ausgabe_mit_codezaun_und_fehler(server):
    server.antwort(openai_antwort('```json\n{"x": [1, 2]}\n```'))
    assert _kompatibel(server).chat(_anfrage(json_ausgabe=True)).json == {"x": [1, 2]}
    server.antwort(openai_antwort("das ist kein JSON"))
    with pytest.raises(KiAusgabeFehler):
        _kompatibel(server).chat(_anfrage(json_ausgabe=True))


def test_zeitueberschreitung(server):
    server.antwort(openai_antwort(), verzoegerung=1.5)
    with pytest.raises(KiZeitueberschreitung):
        _kompatibel(server).chat(_anfrage(timeout=0.3))


def test_verbindung_abgelehnt():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    adapter = ki.adapter_erzeugen(
        "openai_kompatibel", basis_url=f"http://127.0.0.1:{port}/v1", modell="m"
    )
    with pytest.raises(KiVerbindungsFehler):
        adapter.chat(_anfrage())


def test_weiterleitung_wird_nicht_gefolgt(server):
    server.antwort("", status=302, header={"Location": "http://127.0.0.1:9/x"})
    with pytest.raises(KiAnfrageFehler) as exc:
        _kompatibel(server, SCHLUESSEL).chat(_anfrage())
    assert exc.value.status == 302
    assert len(server.anfragen) == 1


def test_zu_grosse_antwort_wird_abgelehnt(server, monkeypatch):
    monkeypatch.setattr(transport, "MAX_ANTWORT_BYTES", 10)
    server.antwort(openai_antwort("x" * 100))
    with pytest.raises(KiAnfrageFehler):
        _kompatibel(server).chat(_anfrage())


def test_zu_grosse_fehlerantwort_liefert_nur_status(server, monkeypatch):
    monkeypatch.setattr(transport, "MAX_ANTWORT_BYTES", 10)
    server.antwort({"error": "x" * 100}, status=500)
    with pytest.raises(KiServerFehler):
        _kompatibel(server).chat(_anfrage())


# --- URL-Prüfung und Konfiguration ---------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://host/v1",
        "file:///etc/passwd",
        "http://",
        "http://nutzer:pw@host/v1",
        "http://host/v1?x=1",
        "http://host/v1#f",
        "http://host:abc/v1",
        "dein-ki-server:11434",
    ],
)
def test_ungueltige_urls(url):
    with pytest.raises(KiKonfigurationsFehler):
        transport.url_pruefen(url)


def test_gueltige_urls_ohne_schraegstrich():
    assert (
        transport.url_pruefen(" http://dein-ki-server:11434/v1/ ")
        == "http://dein-ki-server:11434/v1"
    )


def test_adapter_ohne_url_oder_modell():
    with pytest.raises(KiKonfigurationsFehler):
        ki.adapter_erzeugen("openai_kompatibel", basis_url="", modell="m").chat(_anfrage())
    with pytest.raises(KiKonfigurationsFehler):
        ki.adapter_erzeugen("openai_kompatibel", basis_url="http://x", modell=" ")
    with pytest.raises(KiKonfigurationsFehler):
        ki.adapter_erzeugen("unbekannt", basis_url="http://x", modell="m")


def test_repr_zeigt_nie_key_oder_inhalt():
    a = ki.adapter_erzeugen("anthropic", basis_url="", modell="m", api_key=SCHLUESSEL)
    assert SCHLUESSEL not in repr(a)
    anfrage = KiAnfrage(
        system="GEHEIMSYSTEM", nachricht="GEHEIMNACHRICHT", bilder=(KiBild("image/png", b"BILD"),)
    )
    text = repr(anfrage)
    assert "GEHEIM" not in text and "BILD" not in text
    assert "GEHEIM" not in repr(basis.KiAntwort(text="GEHEIMTEXT"))


# --- Anthropic und OpenAI ------------------------------------------------------------------------


def test_anthropic_chat(server):
    server.antwort(anthropic_antwort('{"k": 1}', 5, 4))
    adapter = ki.adapter_erzeugen(
        "anthropic", basis_url=server.url + "/v1", modell="testmodell", api_key=SCHLUESSEL
    )
    bild = KiBild("image/jpeg", b"jpg")
    antwort = adapter.chat(_anfrage(bilder=(bild,), json_ausgabe=True))
    pfad, header, body = server.anfragen[0]
    assert pfad == "/v1/messages"
    assert header["x-api-key"] == SCHLUESSEL
    assert header["anthropic-version"]
    assert "authorization" not in header
    assert body["model"] == "testmodell" and body["max_tokens"] == 1024
    assert "JSON" in body["system"]
    teile = body["messages"][0]["content"]
    assert teile[0]["type"] == "image" and teile[0]["source"]["media_type"] == "image/jpeg"
    assert teile[1] == {"type": "text", "text": "Hallo"}
    assert (antwort.json, antwort.tokens_ein, antwort.tokens_aus) == ({"k": 1}, 5, 4)


def test_anthropic_ohne_system_und_fehler(server):
    adapter = ki.adapter_erzeugen("anthropic", basis_url=server.url, modell="m", api_key="k")
    server.antwort({"content": [{"type": "text", "text": '{"a":1}'}]})
    assert adapter.chat(_anfrage(system="", json_ausgabe=False)).text == '{"a":1}'
    assert "system" not in server.anfragen[0][2]
    server.antwort({"foo": 1})
    with pytest.raises(KiAusgabeFehler):
        adapter.chat(_anfrage())
    server.antwort({"content": [{"type": "tool_use"}]})
    with pytest.raises(KiAusgabeFehler):
        adapter.chat(_anfrage())
    server.antwort({}, status=529)
    with pytest.raises(KiServerFehler):
        adapter.chat(_anfrage())


def test_anthropic_standard_url_und_ohne_key(server):
    assert ki.adapter_erzeugen("anthropic", basis_url="", modell="m").basis_url == (
        "https://api.anthropic.com"
    )
    adapter = ki.adapter_erzeugen("anthropic", basis_url=server.url, modell="m")
    server.antwort(anthropic_antwort())
    adapter.chat(_anfrage())
    assert "x-api-key" not in server.anfragen[0][1]


def test_openai_nutzt_max_completion_tokens(server):
    adapter = ki.adapter_erzeugen(
        "openai", basis_url=server.url + "/v1", modell="m", api_key=SCHLUESSEL
    )
    assert ki.adapter_erzeugen("openai", basis_url="", modell="m").basis_url == (
        "https://api.openai.com/v1"
    )
    server.antwort(openai_antwort())
    adapter.chat(_anfrage(max_tokens=77))
    body = server.anfragen[0][2]
    assert body["max_completion_tokens"] == 77 and "max_tokens" not in body
    assert server.anfragen[0][1]["authorization"] == f"Bearer {SCHLUESSEL}"


def test_zahl_ignoriert_unsinn():
    assert basis.zahl(5) == 5
    assert basis.zahl(True) is None
    assert basis.zahl("5") is None
    assert json.loads('{"a": 1}') == {"a": 1}
