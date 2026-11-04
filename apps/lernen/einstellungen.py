"""Einstellungen von lernen (SPEC 21.12). Startwerte per Datenmigration 0002, generisch."""

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

from .speicher import pfad_pruefen


def speicher_pfad_pruefen(pfad):
    """Validator der Einstellung: leer = Standard, sonst Pfad und Schreibtest."""
    if pfad:
        pfad_pruefen(pfad)


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


# Etappe 6 (Prüfungsvorbereitung): Migration 0013 legt fehlende Werte an.
STARTWERTE_PRUEFUNG = {
    "lernen.pruefung_puffer_rhythmus": 5,
    "lernen.pruefung_min_antworten": 8,
    "lernen.pruefung_min_sekunden": 300,
    "lernen.pruefung_vorlauf_tage": 14,
    "lernen.pruefung_max_planlaenge": 42,
    "lernen.pruefung_sekunden_pro_frage": 45,
    "lernen.pruefung_portion_minuten": 10,
    "lernen.pruefung_wiederholung_prozent": 40,
    "lernen.pruefung_leicht_minuten": 10,
    "lernen.pruefung_wochentage": [0, 1, 2, 3, 4, 5, 6],
    "lernen.pruefung_ziel_zuschlag_max": 15,
    "lernen.pruefung_probe_fragen": 15,
    "lernen.pruefung_probe_staerke_prozent": 80,
    "lernen.pruefung_probe_schwaeche_prozent": 60,
    "lernen.pruefung_punkte_woche": 3,
    "lernen.pruefung_punkte_vorbereitet": 10,
}

# Etappe 7 (Familienansicht, Titel, Wochenbild): Migration 0014 legt fehlende Werte an.
STARTWERTE_WOCHE = {
    "lernen.titel_anzeigen": True,
    "lernen.familienziel_tage": 4,
    "lernen.titel_min_versuche": 8,
    "lernen.titel_min_fehler": 3,
    "lernen.woche_tendenz_prozent": 5,
    "lernen.woche_schwaeche_fehler": 4,
    "lernen.woche_schwaeche_prozent": 40,
    "lernen.woche_hilfe_hoch_prozent": 40,
    "lernen.woche_pruefung_tage": 14,
}

# Etappe 8 (Einrichtungs-Assistent): Migration 0015 legt den Wert an. Leer = Docker-Volume.
STARTWERTE_EINRICHTUNG = {"lernen.speicher_pfad": ""}


# Etappe 10a (Mathe-Generator, SPEC 21.13): Migration 0017 legt fehlende Werte an.
STARTWERTE_MATHE = {
    "lernen.mathe_rechenarten_aus": [],
    "lernen.mathe_aufgaben_je_runde": 0,
    "lernen.mathe_zahlenraum_max": 0,
    "lernen.mathe_ziel_von_prozent": 70,
    "lernen.mathe_ziel_bis_prozent": 85,
    "lernen.mathe_fenster": 8,
    "lernen.mathe_pruefung_aufgaben": 12,
    "lernen.mathe_aufbewahren_tage": 60,
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

    definieren(
        "lernen.speicher_pfad",
        Typ.TEXT,
        _("Speicherort der Lernmappen (gemounteter Pfad)"),
        beschreibung=_(
            "Leer: Docker-Volume (Standard). Sonst der Ordner im Container, in den z. B. ein NAS "
            "eingebunden ist. Nestwerk prüft, ob der Ordner da ist und beschreibbar. Bereits "
            "abgelegte Dateien werden nicht verschoben."
        ),
        max_laenge=300,
        validatoren=[speicher_pfad_pruefen],
    )

    _definieren_ueben()
    _definieren_ki()
    _definieren_material()
    _definieren_tutor()
    _definieren_pruefung()
    _definieren_woche()
    _definieren_mathe()


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


def _definieren_pruefung():
    """Einstellungen für Prüfungsplan, Portionen und Probe-Prüfung (SPEC 21.7)."""
    definieren(
        "lernen.pruefung_puffer_rhythmus",
        Typ.GANZZAHL,
        _("Prüfung: ein Puffertag je so viele Lerntage"),
        beschreibung=_(
            "0 heißt: keine Puffertage. Puffertage bleiben frei, falls ein Tag ausfällt."
        ),
        einheit=_("Tage"),
        minimum=0,
        maximum=30,
    )
    definieren(
        "lernen.pruefung_min_antworten",
        Typ.GANZZAHL,
        _("Prüfung: Antworten je Portion"),
        beschreibung=_(
            "So viele Fragen muss ein Kind bei einer Portion beantworten, damit sie als erledigt "
            "zählt. Ein bloßer Klick genügt nie."
        ),
        minimum=1,
        maximum=100,
    )
    definieren(
        "lernen.pruefung_min_sekunden",
        Typ.GANZZAHL,
        _("Prüfung: Mindestzeit je Portion"),
        beschreibung=_(
            "Alternativ zählt eine Portion als erledigt, wenn so lange geübt wurde "
            "(mindestens eine Antwort)."
        ),
        einheit=_("Sekunden"),
        minimum=30,
        maximum=3600,
    )
    definieren(
        "lernen.pruefung_vorlauf_tage",
        Typ.GANZZAHL,
        _("Prüfung: empfohlener Vorlauf"),
        beschreibung=_("Ist der Termin näher, steht ein freundlicher Hinweis, dass es knapp wird."),
        einheit=_("Tage"),
        minimum=1,
        maximum=120,
    )
    definieren(
        "lernen.pruefung_max_planlaenge",
        Typ.GANZZAHL,
        _("Prüfung: längster Plan"),
        beschreibung=_("So viele Tage vor dem Termin beginnt der Plan frühestens."),
        einheit=_("Tage"),
        minimum=7,
        maximum=180,
    )
    definieren(
        "lernen.pruefung_sekunden_pro_frage",
        Typ.GANZZAHL,
        _("Prüfung: Zeit je Frage (Schätzung)"),
        beschreibung=_("Daraus rechnet der Plan, wie viele Minuten der Stoff braucht."),
        einheit=_("Sekunden"),
        minimum=5,
        maximum=600,
    )
    definieren(
        "lernen.pruefung_portion_minuten",
        Typ.GANZZAHL,
        _("Prüfung: Größe einer Portion"),
        beschreibung=_(
            "So viele Minuten dauert eine Portion höchstens (nie mehr als das Tagesziel)."
        ),
        einheit=_("Minuten"),
        minimum=1,
        maximum=120,
    )
    definieren(
        "lernen.pruefung_wiederholung_prozent",
        Typ.GANZZAHL,
        _("Prüfung: Zeit für eine Wiederholung"),
        beschreibung=_("Anteil der Lernzeit einer Portion, den eine Wiederholung braucht."),
        einheit=_("Prozent"),
        minimum=10,
        maximum=100,
    )
    definieren(
        "lernen.pruefung_leicht_minuten",
        Typ.GANZZAHL,
        _("Prüfung: leichter Tag vor der Prüfung"),
        beschreibung=_("So viele Minuten leichte Wiederholung stehen am letzten Lerntag."),
        einheit=_("Minuten"),
        minimum=1,
        maximum=60,
    )
    definieren(
        "lernen.pruefung_wochentage",
        Typ.LISTE,
        _("Prüfung: Lerntage der Woche"),
        beschreibung=_("An diesen Wochentagen plant der Plan (0 = Montag bis 6 = Sonntag)."),
        element_typ=Typ.GANZZAHL,
        minimum=0,
        maximum=6,
        validatoren=(_mindestens_ein_tag,),
    )
    definieren(
        "lernen.pruefung_ziel_zuschlag_max",
        Typ.GANZZAHL,
        _("Prüfung: größte Erhöhung des Tagesziels im Vorschlag"),
        beschreibung=_(
            "Weiter als so viele Minuten über das Tagesziel hinaus schlägt der Plan nie vor."
        ),
        einheit=_("Minuten"),
        minimum=0,
        maximum=60,
    )
    definieren(
        "lernen.pruefung_probe_fragen",
        Typ.GANZZAHL,
        _("Probe-Prüfung: Anzahl Fragen"),
        minimum=3,
        maximum=100,
    )
    definieren(
        "lernen.pruefung_probe_staerke_prozent",
        Typ.GANZZAHL,
        _("Probe-Prüfung: ab hier ist es eine Stärke"),
        beschreibung=_("Anteil richtiger Antworten je Thema. Nur ein Hinweis, keine Note."),
        einheit=_("Prozent"),
        minimum=1,
        maximum=100,
    )
    definieren(
        "lernen.pruefung_probe_schwaeche_prozent",
        Typ.GANZZAHL,
        _("Probe-Prüfung: darunter ist es noch zu üben"),
        beschreibung=_("Anteil richtiger Antworten je Thema. Nur ein Hinweis, keine Note."),
        einheit=_("Prozent"),
        minimum=0,
        maximum=99,
    )
    definieren(
        "lernen.pruefung_punkte_woche",
        Typ.GANZZAHL,
        _("Punkte: Planwoche eingehalten"),
        beschreibung=_(
            "Fester kleiner Betrag, wenn alle Portionen einer Woche erledigt sind. Es zählt das "
            "Lernpunkte-Tageslimit."
        ),
        einheit=_("Punkte"),
        minimum=0,
        maximum=100,
    )
    definieren(
        "lernen.pruefung_punkte_vorbereitet",
        Typ.GANZZAHL,
        _("Punkte: Prüfung vorbereitet"),
        beschreibung=_(
            "Fester kleiner Betrag, wenn der Plan geschafft ist. Es zählt das "
            "Lernpunkte-Tageslimit."
        ),
        einheit=_("Punkte"),
        minimum=0,
        maximum=100,
    )


def _definieren_woche():
    """Familienansicht, Wochen-Titel und Eltern-Wochenbild (SPEC 21.9, 21.10)."""
    definieren(
        "lernen.titel_anzeigen",
        Typ.BOOL,
        _("Wochen-Titel anzeigen"),
        beschreibung=_(
            "Übungsmeister, Aufsteiger, Durchbeißer, Entdecker: Anerkennung ohne Punkte. "
            "Aus: Die Titel erscheinen nirgends."
        ),
    )
    definieren(
        "lernen.familienziel_tage",
        Typ.GANZZAHL,
        _("Lern-Familienziel: Übungstage"),
        beschreibung=_(
            "Alle Kinder üben an so vielen Tagen der Woche. Pausentage senken, was verlangt wird."
        ),
        einheit=_("Tage"),
        minimum=1,
        maximum=7,
    )
    definieren(
        "lernen.titel_min_versuche",
        Typ.GANZZAHL,
        _("Aufsteiger: mindestens so viele Antworten pro Woche"),
        beschreibung=_("Erst ab dieser Zahl in beiden Wochen vergleicht der Titel Aufsteiger."),
        einheit=_("Antworten"),
        minimum=1,
        maximum=500,
    )
    definieren(
        "lernen.titel_min_fehler",
        Typ.GANZZAHL,
        _("Durchbeißer: mindestens so viele Fehler in der Woche"),
        beschreibung=_("Der Titel misst, wie viele der eigenen Fehler das Kind selbst klärt."),
        einheit=_("Fehler"),
        minimum=1,
        maximum=100,
    )
    definieren(
        "lernen.woche_tendenz_prozent",
        Typ.GANZZAHL,
        _("Wochenbild: ab hier gilt eine Veränderung als Tendenz"),
        beschreibung=_("Prozentpunkte gegenüber der Vorwoche (Treffer und Hilfe)."),
        einheit=_("Prozentpunkte"),
        minimum=1,
        maximum=50,
    )
    definieren(
        "lernen.woche_schwaeche_fehler",
        Typ.GANZZAHL,
        _("Wochenbild: Schwäche ab so vielen Fehlversuchen im Thema"),
        einheit=_("Fehlversuche"),
        minimum=1,
        maximum=100,
    )
    definieren(
        "lernen.woche_schwaeche_prozent",
        Typ.GANZZAHL,
        _("Wochenbild: Schwäche ab diesem Anteil Fehler im Thema"),
        beschreibung=_("Nur ein Hinweis für Gespräche, keine Note."),
        einheit=_("Prozent"),
        minimum=1,
        maximum=100,
    )
    definieren(
        "lernen.woche_hilfe_hoch_prozent",
        Typ.GANZZAHL,
        _("Wochenbild: ab hier gilt die Hilfe als oft genutzt"),
        beschreibung=_("Anteil der Antworten, bei denen das Kind Hilfe benutzt hat."),
        einheit=_("Prozent"),
        minimum=1,
        maximum=100,
    )
    definieren(
        "lernen.woche_pruefung_tage",
        Typ.GANZZAHL,
        _("Wochenbild: Prüfungen so viele Tage im Voraus erwähnen"),
        einheit=_("Tage"),
        minimum=1,
        maximum=90,
    )


def _definieren_mathe():
    """Einstellungen des Mathe-Generators (SPEC 21.13): lokal, ohne KI."""
    from .mathe.registry import schluessel_alle

    definieren(
        "lernen.mathe_rechenarten_aus",
        Typ.LISTE,
        _("Mathe: abgeschaltete Rechenarten"),
        beschreibung=format_lazy(
            "{} {}",
            _(
                "Diese Rechenarten kommen beim Mathe-Üben nicht vor (ein Schlüssel je Zeile). "
                "Leer: alle sind an. Mögliche Schlüssel:"
            ),
            ", ".join(schluessel_alle()),
        ),
        element_typ=Typ.TEXT,
        auswahl=schluessel_alle(),
    )
    definieren(
        "lernen.mathe_aufgaben_je_runde",
        Typ.GANZZAHL,
        _("Mathe: Aufgaben je Runde"),
        beschreibung=_("0: Die Zahl hängt von der Intensität ab (wie bei den Vokabeln)."),
        minimum=0,
        maximum=50,
    )
    definieren(
        "lernen.mathe_zahlenraum_max",
        Typ.GANZZAHL,
        _("Mathe: Obergrenze für Zahlen"),
        beschreibung=_(
            "0: keine Obergrenze. Sonst bleiben die Zahlen der Aufgaben bei Plus, Minus, "
            "Malnehmen und Prozent unter diesem Wert (mindestens 20)."
        ),
        minimum=0,
        maximum=1_000_000,
    )
    definieren(
        "lernen.mathe_ziel_von_prozent",
        Typ.GANZZAHL,
        _("Mathe: Zielbereich richtig, von"),
        beschreibung=_("Unter diesem Anteil richtiger Antworten wird die Aufgabe leichter."),
        einheit=_("Prozent"),
        minimum=0,
        maximum=100,
    )
    definieren(
        "lernen.mathe_ziel_bis_prozent",
        Typ.GANZZAHL,
        _("Mathe: Zielbereich richtig, bis"),
        beschreibung=_("Über diesem Anteil richtiger Antworten wird die Aufgabe schwerer."),
        einheit=_("Prozent"),
        minimum=0,
        maximum=100,
    )
    definieren(
        "lernen.mathe_fenster",
        Typ.GANZZAHL,
        _("Mathe: so viele letzte Antworten zählen für die Anpassung"),
        minimum=4,
        maximum=30,
    )
    definieren(
        "lernen.mathe_pruefung_aufgaben",
        Typ.GANZZAHL,
        _("Mathe: Aufgaben je Prüfungsthema"),
        beschreibung=_(
            "So viele Aufgaben legt der Prüfungsplan je Mathe-Thema fest (Portionen und "
            "Probe-Prüfung ziehen daraus)."
        ),
        minimum=4,
        maximum=60,
    )
    definieren(
        "lernen.mathe_aufbewahren_tage",
        Typ.GANZZAHL,
        _("Mathe: erzeugte Aufgaben aufbewahren"),
        beschreibung=_(
            "Ältere Aufgaben ohne Wiederholungstermin werden gelöscht, mit ihren Antworten."
        ),
        einheit=_("Tage"),
        minimum=7,
        maximum=730,
    )


def _mindestens_ein_tag(liste):
    if not liste:
        raise ValueError(_("Mindestens ein Wochentag."))


def _mindestens_zwei(liste):
    if len(liste) < 2 or liste != sorted(liste):
        raise ValueError(_("Mindestens zwei Abstände, aufsteigend."))
