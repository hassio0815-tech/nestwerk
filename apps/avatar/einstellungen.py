"""Einstellungen von avatar (AP26, AP27). Definition hier, Startwerte per Datenmigration
0003/0004."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    # SPEC 11.4 Zeitbremse: höchstens ein neu fertiger Mod je Woche zählt für die Ausbaustufe
    "avatar.max_zaehlende_mods_woche": 1,
    # O3/E1: nach God Mode alle 26 aktiven Wochen ein neues Mod-Set (und Sondertag, AP27)
    "avatar.godmode_zyklus_aktivwochen": 26,
}

# P3-A: Ruhmeshalle (Entscheidung 33), Startwert per Datenmigration 0006
RUHMESHALLE_STARTWERTE = {"avatar.ruhmeshalle_ausbaustufe": 6}


def einstellungen_definieren():
    definieren(
        "avatar.max_zaehlende_mods_woche",
        Typ.GANZZAHL,
        _("Zählende Mods pro Woche"),
        beschreibung=_(
            "So viele neu fertige Mods zählen je Woche für die Ausbaustufe. Weitere "
            "Mods sind sofort nutzbar und zählen ab der nächsten freien Woche (Warteschlange)."
        ),
        einheit=_("Mods"),
        minimum=1,
        maximum=6,
    )
    definieren(
        "avatar.godmode_zyklus_aktivwochen",
        Typ.GANZZAHL,
        _("God-Mode-Zyklus"),
        beschreibung=_(
            "Nach dem Aufstieg in God Mode gibt es alle so viele aktiven Wochen ein "
            "neues Mod-Set. Wer das Set des Zyklus fertig baut, verdient einen Sondertag."
        ),
        einheit=_("aktive Wochen"),
        minimum=4,
        maximum=104,
    )
    definieren(
        "avatar.ruhmeshalle_ausbaustufe",
        Typ.GANZZAHL,
        _("Ruhmeshalle ab Ausbaustufe"),
        beschreibung=_(
            "Ab dieser Ausbaustufe im aktuellen Rang kann ein Kind seinen Helden in die "
            "Ruhmeshalle stellen und mit einem neuen Thema von vorn beginnen."
        ),
        einheit=_("Slots"),
        minimum=1,
        maximum=6,
    )
