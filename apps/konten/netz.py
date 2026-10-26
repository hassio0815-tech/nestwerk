"""Client-IP hinter dem Proxy und Heimnetz-Prüfung (ARCHITECTURE 4.3).

``X-Forwarded-For`` wird nur ausgewertet, wenn die direkte Gegenstelle (``REMOTE_ADDR``) in
``konten.vertraute_proxys`` steht. Dann zählt genau der **rechteste** Eintrag: ihn hat unser
einziger Proxy (Nginx Proxy Manager) angehängt, alles links davon kann der Client frei
erfinden. Unlesbare Adressen -> ``None`` (fail closed).

Bewusst kein "von rechts den ersten nicht vertrauten Eintrag nehmen" (Review AP19, B-02): Der
Startwert der vertrauten Proxys sind alle privaten Netze, und Heimnetz-Clients sind selbst
privat. Ein Kind im WLAN hätte mit ``X-Forwarded-For: <beliebig>`` sonst jede Adresse
vortäuschen und so das Rate-Limit des Eltern-Logins (je IP) umgehen können. Topologie mit nur
einem Proxy-Hop: ARCHITECTURE 3 (kein cloudflared, E20).
"""

import ipaddress

from apps.kern import einstellungen


def _netze(werte):
    return [ipaddress.ip_network(w, strict=False) for w in werte]


def _adresse(text):
    try:
        adresse = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    # IPv4-gemappte IPv6-Adressen (::ffff:1.2.3.4) wie IPv4 behandeln
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped:
        return adresse.ipv4_mapped
    return adresse


def _enthalten(netze, adresse):
    return any(adresse.version == n.version and adresse in n for n in netze)


def client_ip(request):
    """Adresse des Clients als ``ipaddress``-Objekt oder ``None`` (unbekannt/unlesbar)."""
    direkt = _adresse(request.META.get("REMOTE_ADDR", ""))
    if direkt is None:
        return None
    proxys = _netze(einstellungen.wert("konten.vertraute_proxys"))
    if not _enthalten(proxys, direkt):
        return direkt
    kette = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not kette.strip():
        return direkt
    # Nur der vom Proxy selbst angehängte (rechteste) Eintrag ist vertrauenswürdig
    return _adresse(kette.split(",")[-1])


def client_ip_text(request):
    adresse = client_ip(request)
    return str(adresse) if adresse else None


def kind_login_erlaubt(request):
    """Kinder-Login nur aus den Heimnetzen (``konten.kind_netze_cidr``). Leere Liste = aus."""
    netze = _netze(einstellungen.wert("konten.kind_netze_cidr"))
    if not netze:
        return True
    adresse = client_ip(request)
    return adresse is not None and _enthalten(netze, adresse)
