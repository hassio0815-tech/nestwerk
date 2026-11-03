"""Feste Sätze des Tutors (SPEC 21.2, 21.3): Ton nach Sprachstufe, wie ``texte.py``.

Diese Sätze erscheinen, wenn der Tutor **nicht** die KI sprechen lässt: abgelehnte Lösungsbitte,
Rollenwechsel-Versuch, zurückgehaltene Antwort, Limit, Urteil über einen Lösungsversuch. Jeder
Satz ist ein ``gettext_noop``-Tripel (Stufe 1 bis Klasse 4, Stufe 2 Klasse 5-7, Stufe 3 ab Klasse
8) und wird erst beim Anzeigen übersetzt (docs/i18n.md). Gelobt wird, was das Kind tut; "noch
nicht" statt "falsch"; nie eine Lösung.
"""

from django.utils.translation import gettext, gettext_noop

from .texte import STUFE_MITTE

_TEXTE = {
    "begruessung": (
        gettext_noop(
            "Hallo! Ich bin dein Lern-Tutor. Ich helfe dir, Aufgaben selbst zu lösen. "
            "Woran arbeitest du gerade?"
        ),
        gettext_noop(
            "Hallo! Ich bin dein Lern-Tutor. Ich erkläre dir Dinge und helfe dir, Aufgaben selbst "
            "zu lösen. Woran arbeitest du gerade?"
        ),
        gettext_noop(
            "Hallo! Ich bin dein Lern-Tutor. Ich erkläre Zusammenhänge und helfe dir, Aufgaben "
            "selbst zu lösen. Woran arbeitest du?"
        ),
    ),
    "umlenkung_loesung": (
        gettext_noop(
            "Die Aufgabe löse ich nicht für dich. Aber ich helfe dir dabei! Erzähl mir: Was sollst "
            "du machen?"
        ),
        gettext_noop(
            "Die Aufgabe löse ich nicht für dich, aber ich helfe dir, sie selbst zu schaffen. Was "
            "ist bei der Aufgabe gefragt?"
        ),
        gettext_noop(
            "Lösen werde ich die Aufgabe nicht, aber ich helfe dir beim Lösungsweg. Was ist "
            "gefragt, und wo hängst du?"
        ),
    ),
    "rollenwechsel": (
        gettext_noop(
            "Ich bleibe dein Lern-Tutor. Lass uns weiter lernen! Woran arbeitest du gerade?"
        ),
        gettext_noop(
            "Ich bleibe dein Lern-Tutor und halte mich an meine Regeln. Woran arbeitest du?"
        ),
        gettext_noop("Ich bleibe bei meiner Rolle als Lern-Tutor. Woran arbeitest du gerade?"),
    ),
    "zurueckgehalten": (
        gettext_noop(
            "Das sollst du selbst herausfinden, du schaffst das! Was weißt du schon? Wenn du mehr "
            "Hilfe möchtest, drück auf den Knopf."
        ),
        gettext_noop(
            "Das verrate ich dir nicht, du schaffst das selbst. Was weißt du schon? Mit dem Knopf "
            "bekommst du mehr Hilfe."
        ),
        gettext_noop(
            "Die Lösung nenne ich dir nicht. Schreib mir, was du schon hast. Mit dem Knopf "
            "bekommst du bei Bedarf mehr Hilfe."
        ),
    ),
    "limit_tag": (
        gettext_noop(
            "Für heute haben wir genug geredet. Morgen geht's weiter. Mach jetzt eine Pause!"
        ),
        gettext_noop(
            "Für heute ist Schluss mit Fragen. Morgen geht's weiter. Mach jetzt eine Pause!"
        ),
        gettext_noop(
            "Für heute ist das Limit erreicht. Morgen geht's weiter. Gönn dir eine Pause."
        ),
    ),
    "max_stufe": (
        gettext_noop(
            "Mehr Hilfe kann ich dir hier nicht geben, den Rest schaffst du selbst. Probier es "
            "aus und zeig mir deinen Versuch!"
        ),
        gettext_noop(
            "Mehr Hilfe als bis hierhin gebe ich nicht, den letzten Schritt gehst du selbst. "
            "Probier es aus und zeig mir deinen Versuch."
        ),
        gettext_noop(
            "Das war die höchste Hilfestufe. Den letzten Schritt gehst du selbst. Zeig mir danach "
            "gern deinen Versuch."
        ),
    ),
    "nichts_zu_helfen": (
        gettext_noop("Erzähl mir zuerst, woran du arbeitest. Dann helfe ich dir."),
        gettext_noop("Schreib mir zuerst, bei welcher Aufgabe du Hilfe brauchst."),
        gettext_noop("Beschreib zuerst die Aufgabe, bei der du Hilfe brauchst."),
    ),
    "urteil_richtig": (
        gettext_noop("Super, das stimmt! Du hast gut nachgedacht und bist drangeblieben."),
        gettext_noop("Das stimmt. Gut gedacht und gut durchgehalten."),
        gettext_noop("Das stimmt. Sauber gearbeitet."),
    ),
    "urteil_teilweise": (
        gettext_noop("Ein gutes Stück hast du schon! Ein Teil passt noch nicht ganz."),
        gettext_noop("Das ist schon ein gutes Stück. Ein Teil passt noch nicht ganz."),
        gettext_noop("Ein Teil stimmt schon, ein Teil noch nicht."),
    ),
    "urteil_noch_nicht": (
        gettext_noop("Noch nicht ganz. Das ist okay, so lernt man. Du bleibst dran!"),
        gettext_noop("Noch nicht ganz. Das ist okay, Versuche gehören zum Lernen."),
        gettext_noop("Noch nicht richtig. Versuche gehören dazu."),
    ),
    "urteil_unklar": (
        gettext_noop(
            "Das kann ich gerade nicht sicher sagen. Erzähl mir, wie du vorgegangen bist."
        ),
        gettext_noop(
            "Das kann ich gerade nicht sicher beurteilen. Erzähl mir, wie du vorgegangen bist."
        ),
        gettext_noop(
            "Das kann ich gerade nicht sicher beurteilen. Beschreib, wie du vorgegangen bist."
        ),
    ),
    "tipp": (
        gettext_noop("Tipp:"),
        gettext_noop("Tipp:"),
        gettext_noop("Hinweis:"),
    ),
    "mehr_hilfe_angebot": (
        gettext_noop("Wenn du magst, drück auf „Ich brauche mehr Hilfe“."),
        gettext_noop("Wenn du magst, drück auf „Ich brauche mehr Hilfe“."),
        gettext_noop("Bei Bedarf gibt es mit „Ich brauche mehr Hilfe“ den nächsten Schritt."),
    ),
    "ki_fehler": (
        gettext_noop("Gerade klappt es nicht. Probier es gleich noch einmal."),
        gettext_noop("Gerade klappt es nicht. Versuch es gleich noch einmal."),
        gettext_noop("Das hat gerade nicht geklappt. Versuch es gleich noch einmal."),
    ),
}


def ton(schluessel, stufe=STUFE_MITTE):
    """Der Satz zu ``schluessel`` in der Sprachstufe, übersetzt."""
    return gettext(_TEXTE[schluessel][stufe - 1])


def schluessel():
    return tuple(_TEXTE)


def msgid(schluessel, stufe=STUFE_MITTE):
    """Der unübersetzte Satz (für Tests und Ereignisse)."""
    return _TEXTE[schluessel][stufe - 1]
