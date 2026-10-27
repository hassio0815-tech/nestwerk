"""Einstellungen von aufgaben (DATA_MODEL 15.2). Definition hier, Startwerte per Datenmigration."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "aufgaben.instanz_horizont_tage": 14,
    "aufgaben.vorwarnung_stunden_vorher": 3,
    "aufgaben.reservierung_stunden": 48,
    "aufgaben.erinnerung_kind_stunden_vorher": 6,
}

# Kinderablauf (AP12), Datenmigration 0006
STARTWERTE_ABLAUF = {
    "aufgaben.sonderpunkte_deckel_aktiv": True,
    "aufgaben.sonderpunkte_deckel_prozent": 50,
    "aufgaben.mitbewerben_erlaubt": True,
    "aufgaben.kind_vorschau_tage": 1,
}

# Nachbessern (Vertrauen prüfen), Datenmigration 0009
STARTWERTE_NACHBESSERN = {"aufgaben.nachbessern_stunden": 48}

# Nachweis-Fotos (AP13), Datenmigration 0007 (Review AP19, B-09: vorher Django-Setting/Konstante)
STARTWERTE_NACHWEIS = {
    "aufgaben.nachweis_max_upload_mb": 15,
    "aufgaben.nachweis_max_anzahl": 3,
    "aufgaben.nachweis_max_kante_px": 1600,
}


def einstellungen_definieren():
    definieren(
        "aufgaben.instanz_horizont_tage",
        Typ.GANZZAHL,
        _("Vorlauf für Aufgaben mit Zeitfenster"),
        beschreibung=_("So viele Tage im Voraus werden Termine mit Zeitfenster angelegt."),
        einheit=_("Tage"),
        minimum=1,
        maximum=90,
    )
    definieren(
        "aufgaben.vorwarnung_stunden_vorher",
        Typ.GANZZAHL,
        _("Vorwarnung an Eltern vor 'nicht übernommen'"),
        beschreibung=_(
            "Stunden vor Fensterende, wenn noch kein Kind die Aufgabe übernommen hat. "
            "0 = keine Vorwarnung."
        ),
        einheit=_("Stunden"),
        minimum=0,
        maximum=72,
    )
    definieren(
        "aufgaben.nachbessern_stunden",
        Typ.GANZZAHL,
        _("Frist zum Nachbessern"),
        beschreibung=_(
            "So lange hat ein Kind Zeit, eine zurückgegebene Aufgabe zu verbessern. "
            "Danach verfällt sie ohne Punkte."
        ),
        einheit=_("Stunden"),
        minimum=1,
        maximum=720,
    )
    definieren(
        "aufgaben.reservierung_stunden",
        Typ.GANZZAHL,
        _("Reservierung ohne Frist läuft ab nach"),
        beschreibung=_(
            "Gilt für Aufgaben ohne Zeitfenster. Mit Zeitfenster endet die "
            "Reservierung mit der Frist."
        ),
        einheit=_("Stunden"),
        minimum=1,
        maximum=720,
    )
    definieren(
        "aufgaben.erinnerung_kind_stunden_vorher",
        Typ.GANZZAHL,
        _("Erinnerung an das Kind vor Reservierungsablauf"),
        einheit=_("Stunden"),
        minimum=0,
        maximum=72,
    )
    definieren(
        "aufgaben.sonderpunkte_deckel_aktiv",
        Typ.BOOL,
        _("Obergrenze für Sonderpunkte"),
        beschreibung=_("Aus = keine Obergrenze (außer eine Aufgabe hat einen eigenen Wert)."),
    )
    definieren(
        "aufgaben.sonderpunkte_deckel_prozent",
        Typ.GANZZAHL,
        _("Sonderpunkte höchstens"),
        beschreibung=_(
            "Anteil am Punktwert der Aufgabe (aufgerundet). Eine Aufgabe kann einen "
            "eigenen Wert haben."
        ),
        einheit="%",
        minimum=0,
        maximum=1000,
    )
    definieren(
        "aufgaben.mitbewerben_erlaubt",
        Typ.BOOL,
        _("Mehrere Kinder dürfen dieselbe Aufgabe wählen"),
        beschreibung=_(
            "An: Ein weiteres Kind kann eine schon reservierte Aufgabe auch wählen, "
            "dann entscheiden die Eltern (Konflikt). Aus: Wer zuerst wählt, bekommt sie."
        ),
    )
    definieren(
        "aufgaben.kind_vorschau_tage",
        Typ.GANZZAHL,
        _("Kinder sehen Termine im Voraus"),
        beschreibung=_(
            "0 = nur heute, 1 = heute und morgen usw. Aufgaben ohne Termin sind immer sichtbar."
        ),
        einheit=_("Tage"),
        minimum=0,
        maximum=14,
    )
    definieren(
        "aufgaben.nachweis_max_upload_mb",
        Typ.GANZZAHL,
        _("Nachweis-Foto höchstens"),
        beschreibung=_(
            "Größe eines hochgeladenen Fotos. Gespeichert wird es verkleinert und "
            "ohne Metadaten (GPS)."
        ),
        einheit="MB",
        minimum=1,
        maximum=50,
    )
    definieren(
        "aufgaben.nachweis_max_anzahl",
        Typ.GANZZAHL,
        _("Fotos je Meldung höchstens"),
        minimum=1,
        maximum=10,
    )
    definieren(
        "aufgaben.nachweis_max_kante_px",
        Typ.GANZZAHL,
        _("Nachweis-Foto wird verkleinert auf"),
        beschreibung=_("Längste Kante des gespeicherten Fotos."),
        einheit=_("Pixel"),
        minimum=400,
        maximum=4000,
    )
