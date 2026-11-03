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
            "Nein: sie sind sofort nutzbar. Pro Kind lässt sich das auf der Lernen-Seite ändern."
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
    _definieren_ki()
    _definieren_material()
    _definieren_tutor()


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


# Etappe 3 (KI-Anbindung): Migration 0007 legt fehlende Werte an. KI ist standardmäßig aus.
STARTWERTE_KI = {
    "lernen.ki_timeout_sekunden": 60,
    "lernen.ki_max_versuche": 3,
    "lernen.ki_backoff_sekunden": 60,
    "lernen.ki_mindestabstand_sekunden": 2,
    "lernen.ki_auftraege_pro_lauf": 10,
}


def _definieren_ki():
    definieren(
        "lernen.ki_timeout_sekunden",
        Typ.GANZZAHL,
        _("KI: Zeitlimit pro Aufruf"),
        beschreibung=_("Nach dieser Zeit ohne Antwort bricht der Aufruf ab."),
        einheit=_("Sekunden"),
        minimum=5,
        maximum=600,
    )
    definieren(
        "lernen.ki_max_versuche",
        Typ.GANZZAHL,
        _("KI: Versuche pro Auftrag"),
        beschreibung=_("Nach so vielen Fehlversuchen wird ein Hintergrund-Auftrag aufgegeben."),
        minimum=1,
        maximum=10,
    )
    definieren(
        "lernen.ki_backoff_sekunden",
        Typ.GANZZAHL,
        _("KI: Wartezeit nach einem Fehler"),
        beschreibung=_("Basiswartezeit; sie vervierfacht sich mit jedem weiteren Fehlversuch."),
        einheit=_("Sekunden"),
        minimum=5,
        maximum=3600,
    )
    definieren(
        "lernen.ki_mindestabstand_sekunden",
        Typ.GANZZAHL,
        _("KI: Mindestabstand zwischen Hintergrund-Aufrufen"),
        beschreibung=_("Schont den Server und die Kosten. Gilt je Anbieter."),
        einheit=_("Sekunden"),
        minimum=0,
        maximum=600,
    )
    definieren(
        "lernen.ki_auftraege_pro_lauf",
        Typ.GANZZAHL,
        _("KI: Aufträge pro Lauf"),
        beschreibung=_("So viele Hintergrund-Aufträge bearbeitet ein Lauf höchstens."),
        minimum=1,
        maximum=100,
    )


# Etappe 4 (Material-Pipeline): Migration 0009 legt fehlende Werte an.
STARTWERTE_MATERIAL = {
    "lernen.upload_max_mb": 10,
    "lernen.auslesen_min_konfidenz": 60,
    "lernen.scan_ruhe_sekunden": 30,
    "lernen.scan_dateien_pro_lauf": 10,
    "lernen.fragen_je_material_max": 30,
}


def _definieren_material():
    definieren(
        "lernen.upload_max_mb",
        Typ.GANZZAHL,
        _("Upload: größte Datei"),
        beschreibung=_("Größere Fotos und Dokumente nimmt die Lernmappe nicht an."),
        einheit=_("MB"),
        minimum=1,
        maximum=40,
    )
    definieren(
        "lernen.auslesen_min_konfidenz",
        Typ.GANZZAHL,
        _("Auslesen: Mindest-Sicherheit für das Fach"),
        beschreibung=_("Ist die KI unsicherer, fragen wir die Eltern, zu welchem Fach es gehört."),
        einheit=_("Prozent"),
        minimum=0,
        maximum=100,
    )
    definieren(
        "lernen.scan_ruhe_sekunden",
        Typ.GANZZAHL,
        _("Ordner inbox: Ruhezeit einer Datei"),
        beschreibung=_(
            "Eine Datei im Ordner wird erst gelesen, wenn sie so lange unverändert ist."
        ),
        einheit=_("Sekunden"),
        minimum=0,
        maximum=3600,
    )
    definieren(
        "lernen.scan_dateien_pro_lauf",
        Typ.GANZZAHL,
        _("Ordner inbox: Dateien pro Lauf"),
        beschreibung=_("So viele neue Dateien übernimmt ein Lauf höchstens."),
        minimum=1,
        maximum=200,
    )
    definieren(
        "lernen.fragen_je_material_max",
        Typ.GANZZAHL,
        _("Fragen aus einem Material (Obergrenze)"),
        beschreibung=_("Mehr Fragen speichern wir aus einem Upload nicht."),
        minimum=1,
        maximum=100,
    )


# Etappe 5 (Tutor): Migration 0011 legt fehlende Werte an. ``lernen.tutor_aktiv`` gibt es seit
# Etappe 1 (Standard aus).
STARTWERTE_TUTOR = {
    "lernen.tutor_vergleich_nach_versuch": True,
    "lernen.tutor_nachrichten_pro_tag": 30,
    "lernen.tutor_laenge_nachricht": 500,
    "lernen.tutor_laenge_antwort": 700,
    "lernen.tutor_gespraeche_gleichzeitig": 3,
    "lernen.tutor_aufbewahrung_tage": 90,
}


def _definieren_tutor():
    definieren(
        "lernen.tutor_vergleich_nach_versuch",
        Typ.BOOL,
        _("Tutor: Versuch mit dem richtigen Weg vergleichen"),
        beschreibung=_(
            "Ja: Nach einem eigenen Versuch des Kindes darf der Tutor kurz sagen, ob er stimmt und "
            "wo der Denkfehler liegt. Die Lösung nennt er nie. Nein: Er sagt nur, ob es passt."
        ),
    )
    definieren(
        "lernen.tutor_nachrichten_pro_tag",
        Typ.GANZZAHL,
        _("Tutor: Nachrichten pro Kind und Tag"),
        beschreibung=_("Danach gibt es einen freundlichen Hinweis auf morgen und eine Pause."),
        minimum=1,
        maximum=500,
    )
    definieren(
        "lernen.tutor_laenge_nachricht",
        Typ.GANZZAHL,
        _("Tutor: Länge einer Nachricht des Kindes"),
        beschreibung=_("Längere Nachrichten werden nicht gesendet."),
        einheit=_("Zeichen"),
        minimum=50,
        maximum=5000,
    )
    definieren(
        "lernen.tutor_laenge_antwort",
        Typ.GANZZAHL,
        _("Tutor: Länge einer Antwort"),
        beschreibung=_("Längere Antworten werden gekürzt. Kurze Antworten lesen sich leichter."),
        einheit=_("Zeichen"),
        minimum=100,
        maximum=4000,
    )
    definieren(
        "lernen.tutor_gespraeche_gleichzeitig",
        Typ.GANZZAHL,
        _("Tutor: offene Gespräche gleichzeitig"),
        beschreibung=_("Mehr offene Gespräche pro Kind gibt es nicht."),
        minimum=1,
        maximum=20,
    )
    definieren(
        "lernen.tutor_aufbewahrung_tage",
        Typ.GANZZAHL,
        _("Tutor: Gespräche aufbewahren"),
        beschreibung=_("Ältere Gespräche werden automatisch gelöscht."),
        einheit=_("Tage"),
        minimum=1,
        maximum=3650,
    )


def _mindestens_zwei(liste):
    if len(liste) < 2 or liste != sorted(liste):
        raise ValueError(_("Mindestens zwei Abstände, aufsteigend."))
