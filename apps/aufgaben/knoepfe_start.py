"""Bibliothek -> Schnell-Knöpfe: aus jeder aktiven Vorlage wird ein Knopf (Aufgabe "bei Bedarf").

Reine Logik ohne Modell-Importe, damit die Datenmigration 0016 (historische Modelle) und der
Job ``schnellknoepfe_sicherstellen`` (echte Modelle) denselben Code nutzen. Die Klassen
``Aufgabe``/``Vorlage`` werden übergeben.
"""

BEI_BEDARF = "bei_bedarf"
MODUS_EINER = "einer"
MODUS_JEDES = "jedes"

# Knöpfe, bei denen jedes Kind seine eigene Aufgabe bekommt (Einteilung der Startwerte).
# Der Rest ist "Einer für alle". Alte und neue Titel von "Zimmer gründlich" gehören dazu.
JEDES_TITEL = (
    "Zimmer aufräumen",
    "Zimmer gründlich",
    "Zimmer gründlich reinigen und aufräumen",
    "Wäsche zusammenlegen & einräumen",
    "Vokabeln lernen 15 Min",
    "Zimmer saugen",
)

# Die drei Start-Knöpfe legt ``schnellknopf.schnellknoepfe_sicherstellen`` mit eigenem Merker an.
START_TITEL = ("Restmüll", "Biomüll", "Altglas")

# Emoji für Vorlagen ohne eigenes Symbol (Bibliothek hatte nur bei den Start-Knöpfen eins)
EMOJI = {
    "Müll rausbringen": "🗑️",
    "Mülltonnen rausstellen": "🛢️",
    "Leergut": "🍺",
    "Spülmaschine ausräumen": "🍽️",
    "Spülmaschine einräumen": "🍽️",
    "Tisch decken/abräumen": "🍴",
    "Einkaufsliste": "🛒",
    "Wäsche waschen": "🧺",
    "Wäsche aufhängen": "👕",
    "Wäsche zusammenlegen & einräumen": "👚",
    "Waschmaschine ausräumen": "🧺",
    "Flur saugen": "🧹",
    "Zimmer saugen": "🧹",
    "Zimmer gründlich reinigen und aufräumen": "🧽",
    "Bad putzen": "🛁",
    "Rasen mähen": "🌱",
    "Auto aussaugen": "🚗",
    "Vokabeln lernen 15 Min": "📚",
}


def normal(titel) -> str:
    """Titel zum Vergleichen: ohne Rand-Leerzeichen, Groß-/Kleinschreibung egal."""
    return (titel or "").strip().casefold()


_JEDES = {normal(t) for t in JEDES_TITEL}


def modus_fuer(titel) -> str:
    return MODUS_JEDES if normal(titel) in _JEDES else MODUS_EINER


def aus_bibliothek_anlegen(Aufgabe, Vorlage, ersteller, protokoll=None) -> list:
    """Legt für jede aktive Vorlage ohne gleichnamigen Knopf einen Knopf an.

    "Gleichnamig" = normalisierter Titel einer beliebigen Bei-Bedarf-Aufgabe (auch pausiert oder
    beendet: wer einen Knopf beendet hat, will ihn nicht zurück). Die Start-Knöpfe (Restmüll ...)
    sind ausgenommen. Rückgabe: die neuen Aufgaben. ``protokoll(aufgabe)`` schreibt das Audit.
    """
    vorhanden = {
        normal(titel)
        for titel in Aufgabe.objects.filter(wiederholungsart=BEI_BEDARF).values_list(
            "titel", flat=True
        )
    }
    ausgenommen = {normal(t) for t in START_TITEL}
    neu = []
    for vorlage in Vorlage.objects.filter(aktiv=True).order_by("titel", "pk"):
        schluessel = normal(vorlage.titel)
        if schluessel in vorhanden or schluessel in ausgenommen:
            continue
        aufgabe = Aufgabe.objects.create(
            titel=vorlage.titel,
            punkte=vorlage.punkte,
            beschreibung=vorlage.beschreibung,
            freigabeart=vorlage.freigabeart,
            kategorie_id=vorlage.kategorie_id,
            vorlage_id=vorlage.pk,
            wiederholungsart=BEI_BEDARF,
            schnellknopf_wer="alle",
            schnellknopf_modus=modus_fuer(vorlage.titel),
            emoji=vorlage.emoji or EMOJI.get(vorlage.titel, ""),
            erstellt_von=ersteller,
        )
        vorhanden.add(schluessel)
        neu.append(aufgabe)
        if protokoll is not None:
            protokoll(aufgabe)
    return neu


def modus_der_knoepfe_setzen(Aufgabe) -> int:
    """Bestehende Knöpfe mit "Jedes-Kind"-Titel bekommen den Standard-Modus ``jedes``."""
    zaehler = 0
    for aufgabe in Aufgabe.objects.filter(
        wiederholungsart=BEI_BEDARF, schnellknopf_modus=MODUS_EINER
    ):
        if modus_fuer(aufgabe.titel) == MODUS_JEDES:
            Aufgabe.objects.filter(pk=aufgabe.pk).update(schnellknopf_modus=MODUS_JEDES)
            zaehler += 1
    return zaehler
