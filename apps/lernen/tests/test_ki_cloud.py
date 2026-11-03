"""Cloud-Erkennung (SPEC 21.6): im Zweifel Cloud."""

import pytest

from apps.lernen.ki import ist_cloud

LOKAL = [
    "http://localhost:11434/v1",
    "http://LOCALHOST/v1",
    "http://127.0.0.1:8000/v1",
    "http://127.1.2.3/v1",
    "http://[::1]:8000/v1",
    "http://10.0.0.5:11434/v1",
    "http://172.16.0.9/v1",
    "http://172.31.255.1/v1",
    "http://192.168.1.20:4000/v1",
    "http://169.254.10.10/v1",
    "http://[fd12:3456::1]/v1",
    "http://[::ffff:192.168.1.1]/v1",
    "http://dein-ki-server:11434",
    "http://ollama/v1",
    "http://ki.local/v1",
    "http://ki.fritz.local./v1",
    "http://x.localhost/v1",
    "http://router.home.arpa/v1",
    "https://dein-ki-server.local:8443/v1",
]

CLOUD = [
    "https://api.example.com/v1",
    "http://8.8.8.8/v1",
    "http://172.32.0.1/v1",  # knapp außerhalb 172.16/12
    "http://192.169.0.1/v1",
    "http://100.64.0.1/v1",  # Tailscale/CGNAT: nicht privat im Sinn der Regel
    "http://[2a00:1450::1]/v1",
    "http://ki.example.com/v1",
    "http://meinlocal.example.com/v1",
    "http://localhost.example.com/v1",
    "http://localhost@evil.example.com/v1",
    "https://ki.internal/v1",
    "",
    "kein url",
    "ftp://localhost/v1",
    "http://",
    "http://[::1/v1",
]


@pytest.mark.parametrize("url", LOKAL)
def test_lokale_adressen(url):
    assert ist_cloud("openai_kompatibel", url) is False


@pytest.mark.parametrize("url", CLOUD)
def test_cloud_adressen(url):
    assert ist_cloud("openai_kompatibel", url) is True


@pytest.mark.parametrize("typ", ["anthropic", "openai"])
def test_cloud_typen_immer_cloud(typ):
    assert ist_cloud(typ, "http://localhost:1234") is True
    assert ist_cloud(typ, "") is True
