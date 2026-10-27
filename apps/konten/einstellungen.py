"""Einstellungen von konten (DATA_MODEL 15.2). Definition hier, Startwerte per Datenmigration."""

import ipaddress

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

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
                _("'%(netz)s' ist kein gültiges Netz (CIDR, z. B. 192.168.1.0/24)") % {"netz": netz}
            ) from None


def einstellungen_definieren():
    definieren(
        "konten.kind_pin_fehlversuche",
        Typ.GANZZAHL,
        gettext_lazy("PIN-Fehlversuche bis zur Sperre (Kind)"),
        minimum=1,
        maximum=20,
    )
    definieren(
        "konten.kind_pin_sperre_minuten",
        Typ.GANZZAHL,
        gettext_lazy("Erste PIN-Sperre (Kind)"),
        beschreibung=gettext_lazy("Jede weitere Sperre verdoppelt die Dauer, bis zum Höchstwert."),
        einheit=gettext_lazy("Minuten"),
        minimum=1,
        maximum=1440,
    )
    definieren(
        "konten.kind_pin_sperre_max_minuten",
        Typ.GANZZAHL,
        gettext_lazy("Höchstdauer der PIN-Sperre (Kind)"),
        einheit=gettext_lazy("Minuten"),
        minimum=1,
        maximum=1440,
    )
    definieren(
        "konten.eltern_fehlversuche",
        Typ.GANZZAHL,
        gettext_lazy("Fehlversuche bis zur Sperre (Eltern-Login, je IP)"),
        minimum=1,
        maximum=100,
    )
    definieren(
        "konten.eltern_sperre_minuten",
        Typ.GANZZAHL,
        gettext_lazy("Sperre und Zählfenster (Eltern-Login)"),
        einheit=gettext_lazy("Minuten"),
        minimum=1,
        maximum=1440,
    )
    definieren(
        "konten.sitzung_eltern_vertraut_tage",
        Typ.GANZZAHL,
        gettext_lazy("Eltern-Sitzung auf vertrautem Gerät"),
        beschreibung=gettext_lazy("Gleitend: jede Nutzung verlängert."),
        einheit=gettext_lazy("Tage"),
        minimum=1,
        maximum=730,
    )
    definieren(
        "konten.sitzung_eltern_stunden",
        Typ.GANZZAHL,
        gettext_lazy("Eltern-Sitzung ohne vertrautes Gerät"),
        einheit=gettext_lazy("Stunden"),
        minimum=1,
        maximum=72,
    )
    definieren(
        "konten.sitzung_kind_persoenlich_tage",
        Typ.GANZZAHL,
        gettext_lazy("Kinder-Sitzung auf persönlichem Gerät"),
        beschreibung=gettext_lazy("Gleitend: jede Nutzung verlängert."),
        einheit=gettext_lazy("Tage"),
        minimum=1,
        maximum=730,
    )
    definieren(
        "konten.kiosk_leerlauf_sekunden",
        Typ.GANZZAHL,
        gettext_lazy("Abmeldung des Kiosk-Tablets nach Leerlauf"),
        einheit=gettext_lazy("Sekunden"),
        minimum=30,
        maximum=3600,
    )
    definieren(
        "konten.kiosk_warnung_sekunden",
        Typ.GANZZAHL,
        gettext_lazy("Warnhinweis vor der Abmeldung (Kiosk)"),
        einheit=gettext_lazy("Sekunden"),
        minimum=0,
        maximum=600,
    )
    definieren(
        "konten.kind_netze_cidr",
        Typ.LISTE,
        gettext_lazy("Netze für den Kinder-Login"),
        beschreibung=gettext_lazy(
            "Kinder können sich nur aus diesen Netzen anmelden. Leer = keine Prüfung."
        ),
        element_typ=Typ.TEXT,
        validatoren=(_cidr_pruefen,),
    )
    definieren(
        "konten.vertraute_proxys",
        Typ.LISTE,
        gettext_lazy("Vertrauenswürdige Proxys (X-Forwarded-For)"),
        beschreibung=gettext_lazy(
            "Nur von diesen Adressen wird X-Forwarded-For ausgewertet (Nginx Proxy Manager)."
        ),
        element_typ=Typ.TEXT,
        validatoren=(_cidr_pruefen,),
    )
