"""Einstellungen von konten (DATA_MODEL 15.2). Definition hier, Startwerte per Datenmigration."""

import ipaddress

from django.core.exceptions import ValidationError

from apps.kern.einstellungen import Typ, definieren

PRIVATE_NETZE = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "::1/128",
    "fc00::/7",
]

STARTWERTE = {
    "konten.kind_pin_fehlversuche": 5,
    "konten.kind_pin_sperre_minuten": 5,
    "konten.kind_pin_sperre_max_minuten": 60,
    "konten.eltern_fehlversuche": 10,
    "konten.eltern_sperre_minuten": 15,
    "konten.sitzung_eltern_vertraut_tage": 90,
    "konten.sitzung_eltern_stunden": 12,
    "konten.sitzung_kind_persoenlich_tage": 365,
    "konten.kiosk_leerlauf_sekunden": 300,
    "konten.kiosk_warnung_sekunden": 30,
    "konten.kind_netze_cidr": PRIVATE_NETZE,
    "konten.vertraute_proxys": PRIVATE_NETZE,
}


def _cidr_pruefen(netze):
    for netz in netze:
        try:
            ipaddress.ip_network(netz, strict=False)
        except ValueError:
            raise ValidationError(
                f"'{netz}' ist kein gültiges Netz (CIDR, z. B. 192.168.1.0/24)"
            ) from None


def einstellungen_definieren():
    definieren(
        "konten.kind_pin_fehlversuche",
        Typ.GANZZAHL,
        "PIN-Fehlversuche bis zur Sperre (Kind)",
        minimum=1,
        maximum=20,
    )
    definieren(
        "konten.kind_pin_sperre_minuten",
        Typ.GANZZAHL,
        "Erste PIN-Sperre (Kind)",
        beschreibung="Jede weitere Sperre verdoppelt die Dauer, bis zum Höchstwert.",
        einheit="Minuten",
        minimum=1,
        maximum=1440,
    )
    definieren(
        "konten.kind_pin_sperre_max_minuten",
        Typ.GANZZAHL,
        "Höchstdauer der PIN-Sperre (Kind)",
        einheit="Minuten",
        minimum=1,
        maximum=1440,
    )
    definieren(
        "konten.eltern_fehlversuche",
        Typ.GANZZAHL,
        "Fehlversuche bis zur Sperre (Eltern-Login, je IP)",
        minimum=1,
        maximum=100,
    )
    definieren(
        "konten.eltern_sperre_minuten",
        Typ.GANZZAHL,
        "Sperre und Zählfenster (Eltern-Login)",
        einheit="Minuten",
        minimum=1,
        maximum=1440,
    )
    definieren(
        "konten.sitzung_eltern_vertraut_tage",
        Typ.GANZZAHL,
        "Eltern-Sitzung auf vertrautem Gerät",
        beschreibung="Gleitend: jede Nutzung verlängert.",
        einheit="Tage",
        minimum=1,
        maximum=730,
    )
    definieren(
        "konten.sitzung_eltern_stunden",
        Typ.GANZZAHL,
        "Eltern-Sitzung ohne vertrautes Gerät",
        einheit="Stunden",
        minimum=1,
        maximum=72,
    )
    definieren(
        "konten.sitzung_kind_persoenlich_tage",
        Typ.GANZZAHL,
        "Kinder-Sitzung auf persönlichem Gerät",
        beschreibung="Gleitend: jede Nutzung verlängert.",
        einheit="Tage",
        minimum=1,
        maximum=730,
    )
    definieren(
        "konten.kiosk_leerlauf_sekunden",
        Typ.GANZZAHL,
        "Abmeldung des Kiosk-Tablets nach Leerlauf",
        einheit="Sekunden",
        minimum=30,
        maximum=3600,
    )
    definieren(
        "konten.kiosk_warnung_sekunden",
        Typ.GANZZAHL,
        "Warnhinweis vor der Abmeldung (Kiosk)",
        einheit="Sekunden",
        minimum=0,
        maximum=600,
    )
    definieren(
        "konten.kind_netze_cidr",
        Typ.LISTE,
        "Netze für den Kinder-Login",
        beschreibung="Kinder können sich nur aus diesen Netzen anmelden. Leer = keine Prüfung.",
        element_typ=Typ.TEXT,
        validatoren=(_cidr_pruefen,),
    )
    definieren(
        "konten.vertraute_proxys",
        Typ.LISTE,
        "Vertrauenswürdige Proxys (X-Forwarded-For)",
        beschreibung="Nur von diesen Adressen wird X-Forwarded-For ausgewertet "
        "(Nginx Proxy Manager).",
        element_typ=Typ.TEXT,
        validatoren=(_cidr_pruefen,),
    )
