"""Einstellungen von lernen (SPEC 21.12). Startwerte per Datenmigration 0002, generisch."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "lernen.tagesziel_minuten": 20,
    "lernen.mindesttag_minuten": 5,
    "lernen.lernpunkte_tageslimit": 10,
    "lernen.freigabe_durch_eltern": True,
    "lernen.speicher_limit_mb": 500,
    "lernen.tutor_aktiv": False,
}

# Etappe 2 (Üben ohne KI): Migration 0005 legt fehlende Werte an, bestehende bleiben unberührt.
STARTWERTE_UEBEN = {
    "lernen.lernpunkte_aktiv": True,
    "lernen.tagesziel_punkte": 5,
    "lernen.box_abstaende_tage": [1, 3, 7, 14],
    "lernen.fragen_aufwaermen": 5,
    "lernen.fragen_normal": 10,
    "lernen.fragen_herausforderung": 15,
    "lernen.leerlauf_sekunden": 120,
    "lernen.ziel_senken_nach_tagen": 2,
    "lernen.ziel_schritt_minuten": 5,
    "lernen.ziel_vorschlag_tage": 8,
    "lernen.serie_tage_pro_woche": 3,
    "lernen.ferien_schalter": False,
    "lernen.frust_fehler_folge": 3,
    "lernen.frust_schnell_ms": 1500,
    "lernen.frust_schnell_anzahl": 4,
}


def einstellungen_definieren():
    definieren(
        "lernen.tagesziel_minuten",
        Typ.GANZZAHL,
        _("Tagesziel Lernzeit"),
        beschreibung=_("So viele Minuten pro Tag gelten als Ziel."),
        einheit=_("Minuten"),
        minimum=1,
        maximum=240,
    )
    definieren(
        "lernen.mindesttag_minuten",
        Typ.GANZZAHL,
        _("Mindesttag Lernzeit"),
        beschreibung=_("Ab so vielen Minuten zählt ein Tag als geübt."),
        einheit=_("Minuten"),
        minimum=1,
        maximum=120,
    )
    definieren(
        "lernen.lernpunkte_tageslimit",
        Typ.GANZZAHL,
        _("Lernpunkte pro Tag (Obergrenze)"),
        beschreibung=_("Mehr Punkte als dieser Wert gibt das Lernen pro Kind und Tag nicht."),
        einheit=_("Punkte"),
        minimum=0,
        maximum=1000,
    )
    definieren(
        "lernen.freigabe_durch_eltern",
        Typ.BOOL,
        _("Eltern geben Fragen frei"),
        beschreibung=_(
            "Ja: Fragen aus Uploads sind erst nach der Freigabe durch die Eltern nutzbar. "
            "Nein: sie sind sofort nutzbar."
        ),
    )
    definieren(
        "lernen.speicher_limit_mb",
        Typ.GANZZAHL,
        _("Speicherplatz pro Kind"),
        beschreibung=_("So viel Platz darf die Lernmappe eines Kindes höchstens belegen."),
        einheit=_("MB"),
        minimum=10,
        maximum=1_000_000,
    )
    definieren(
        "lernen.tutor_aktiv",
        Typ.BOOL,
        _("KI-Tutor aktiv"),
        beschreibung=_("Gilt für die ganze Familie. Standardmäßig aus."),
    )

    _definieren_ueben()


def _definieren_ueben():
    """Einstellungen für Üben, Tagesziel, Serie und Frust-Erkennung (SPEC 21.2, 21.12)."""
    definieren(
        "lernen.lernpunkte_aktiv",
        Typ.BOOL,
        _("Lernpunkte vergeben"),
        beschreibung=_(
            "Aus: Das Lernen gibt keine Punkte. Zeit, Serie und Rückschau gibt es trotzdem."
        ),
    )
    definieren(
        "lernen.tagesziel_punkte",
        Typ.GANZZAHL,
        _("Punkte für das Tagesziel"),
        beschreibung=_(
            "Fester Betrag, sobald das Tagesziel erreicht ist. Es zählt die Beteiligung, "
            "nicht die Menge richtiger Antworten."
        ),
        einheit=_("Punkte"),
        minimum=0,
        maximum=100,
    )
    definieren(
        "lernen.box_abstaende_tage",
        Typ.LISTE,
        _("Abstände der Wiederholung"),
        beschreibung=_(
            "Nach wie vielen Tagen eine Frage wiederkommt, je Box. Richtig: eine Box weiter. "
            "Noch nicht richtig: zurück in die erste Box."
        ),
        einheit=_("Tage"),
        element_typ=Typ.GANZZAHL,
        minimum=1,
        maximum=365,
        validatoren=(_mindestens_zwei,),
    )
    for schluessel, bezeichnung in (
        ("lernen.fragen_aufwaermen", _("Fragen je Runde: Aufwärmen")),
        ("lernen.fragen_normal", _("Fragen je Runde: Normal")),
        ("lernen.fragen_herausforderung", _("Fragen je Runde: Herausforderung")),
    ):
        definieren(schluessel, Typ.GANZZAHL, bezeichnung, minimum=1, maximum=100)
    definieren(
        "lernen.leerlauf_sekunden",
        Typ.GANZZAHL,
        _("Längste Denkpause"),
        beschreibung=_("Längere Pausen zwischen zwei Schritten zählen nicht als Lernzeit."),
        einheit=_("Sekunden"),
        minimum=10,
        maximum=3600,
    )
    definieren(
        "lernen.ziel_senken_nach_tagen",
        Typ.GANZZAHL,
        _("Ziel senken nach verfehlten Tagen"),
        beschreibung=_("Nach so vielen verfehlten Tagen sinkt das persönliche Tagesziel."),
        einheit=_("Tage"),
        minimum=1,
        maximum=14,
    )
    definieren(
        "lernen.ziel_schritt_minuten",
        Typ.GANZZAHL,
        _("Schritt beim Anpassen des Ziels"),
        einheit=_("Minuten"),
        minimum=1,
        maximum=60,
    )
    definieren(
        "lernen.ziel_vorschlag_tage",
        Typ.GANZZAHL,
        _("Erreichte Tage für einen Vorschlag"),
        beschreibung=_(
            "Hat ein Kind in den letzten 14 Tagen so oft sein Ziel erreicht, wird ein höheres "
            "Ziel vorgeschlagen (nie automatisch gesetzt)."
        ),
        einheit=_("Tage"),
        minimum=1,
        maximum=14,
    )
    definieren(
        "lernen.serie_tage_pro_woche",
        Typ.GANZZAHL,
        _("Geübte Tage pro Woche für die Serie"),
        beschreibung=_("Eine Woche zählt für die Serie, wenn so viele Tage geübt wurden."),
        einheit=_("Tage"),
        minimum=1,
        maximum=7,
    )
    definieren(
        "lernen.ferien_schalter",
        Typ.BOOL,
        _("Ferien"),
        beschreibung=_("An: Die Serie wird geschont, es wird kein Tagesziel verlangt."),
    )
    definieren(
        "lernen.frust_fehler_folge",
        Typ.GANZZAHL,
        _("Frust-Erkennung: Fehler in Folge"),
        beschreibung=_("So viele Antworten hintereinander „noch nicht“ senken die Stufe."),
        minimum=2,
        maximum=20,
    )
    definieren(
        "lernen.frust_schnell_ms",
        Typ.GANZZAHL,
        _("Frust-Erkennung: sehr schnelle Antwort"),
        beschreibung=_("Antworten unter dieser Zeit gelten als Durchklicken."),
        einheit=_("Millisekunden"),
        minimum=200,
        maximum=10000,
    )
    definieren(
        "lernen.frust_schnell_anzahl",
        Typ.GANZZAHL,
        _("Frust-Erkennung: schnelle Antworten in Folge"),
        minimum=2,
        maximum=20,
    )


def _mindestens_zwei(liste):
    if len(liste) < 2 or liste != sorted(liste):
        raise ValueError(_("Mindestens zwei Abstände, aufsteigend."))
