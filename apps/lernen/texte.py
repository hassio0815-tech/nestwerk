"""Töne und Rückmeldungen beim Üben (SPEC 21.2: Prozesslob, "noch nicht" statt "falsch").

Die Sprache richtet sich nach der Klassenstufe: Stufe 1 bis Klasse 4, Stufe 2 Klasse 5-7,
Stufe 3 ab Klasse 8 (unbekannt: Stufe 2). Alle Sätze sind Daten (``gettext_noop``-Tripel,
je Stufe einer) und werden erst beim Anzeigen in der Sprache des Benutzers übersetzt
(docs/i18n.md). Gelobt wird, was das Kind tut (üben, dranbleiben, nachdenken), nie die Person.
"""

from django.utils.translation import gettext, gettext_noop

STUFE_JUENGER = 1
STUFE_MITTE = 2
STUFE_AELTER = 3


def stufe_fuer(klassenstufe):
    """Sprachstufe für eine Klassenstufe (``None`` = unbekannt = mittlere Stufe)."""
    if klassenstufe is None:
        return STUFE_MITTE
    if klassenstufe <= 4:
        return STUFE_JUENGER
    return STUFE_MITTE if klassenstufe <= 7 else STUFE_AELTER


_TEXTE = {
    "richtig": (
        gettext_noop("Super, das hast du gewusst!"),
        gettext_noop("Richtig, gut gemerkt."),
        gettext_noop("Richtig."),
    ),
    "fast": (
        gettext_noop("Fast! Schau noch einmal genau hin. Du hast einen kleinen Dreher drin."),
        gettext_noop("Fast richtig. Ein kleiner Tippfehler ist drin. Versuch es noch einmal."),
        gettext_noop("Fast richtig, es ist ein Tippfehler. Korrigiere ihn."),
    ),
    "noch_nicht": (
        gettext_noop("Das kannst du noch nicht. Das macht nichts, jetzt kennst du es besser."),
        gettext_noop("Noch nicht. Schau dir die Lösung an, sie kommt bald wieder."),
        gettext_noop("Noch nicht richtig. Die Lösung steht unten, die Frage kommt wieder."),
    ),
    "loesung": (
        gettext_noop("Gut, dass du nachgeschaut hast. So lernt man."),
        gettext_noop("Nachschauen ist erlaubt. Die Frage kommt später wieder."),
        gettext_noop("Nachschauen ist Teil des Lernens. Die Frage kommt wieder."),
    ),
    "frust": (
        gettext_noop(
            "Das war ganz schön viel auf einmal. Wir machen es etwas leichter. Magst du eine "
            "kleine Pause machen?"
        ),
        gettext_noop(
            "Das war gerade zäh. Ich stelle es etwas leichter ein. Eine kleine Pause könnte helfen."
        ),
        gettext_noop(
            "Das läuft gerade nicht rund. Die Stufe ist jetzt niedriger. Eine kurze Pause ist "
            "sinnvoll."
        ),
    ),
    "ende": (
        gettext_noop("Toll, dass du geübt hast!"),
        gettext_noop("Gut, dass du drangeblieben bist."),
        gettext_noop("Gut gemacht. Regelmäßig üben zahlt sich aus."),
    ),
    "ziel_geschafft": (
        gettext_noop("Du hast dein Tagesziel geschafft! Das ist richtig stark."),
        gettext_noop("Tagesziel geschafft. Das Dranbleiben zählt."),
        gettext_noop("Tagesziel erreicht. Danke fürs Dranbleiben."),
    ),
    "ziel_gesenkt": (
        gettext_noop(
            "Wir machen dein Tagesziel erst einmal kleiner: %(minuten)s Minuten. Kleine Schritte "
            "zählen auch."
        ),
        gettext_noop("Dein Tagesziel ist jetzt %(minuten)s Minuten. Kleine Schritte sind okay."),
        gettext_noop(
            "Dein Tagesziel wurde auf %(minuten)s Minuten angepasst. Das ist kein Rückschritt."
        ),
    ),
    "ziel_vorschlag": (
        gettext_noop(
            "Du hast oft geübt! Sollen wir dein Tagesziel auf %(minuten)s Minuten machen?"
        ),
        gettext_noop("Du bist gut dabei. Magst du dein Tagesziel auf %(minuten)s Minuten erhöhen?"),
        gettext_noop(
            "Du erreichst dein Ziel regelmäßig. Vorschlag: %(minuten)s Minuten. Du entscheidest."
        ),
    ),
    "serie": (
        gettext_noop("Du übst schon seit %(wochen)s Wochen regelmäßig!"),
        gettext_noop("%(wochen)s Wochen in Folge geübt."),
        gettext_noop("Serie: %(wochen)s Wochen."),
    ),
    "serie_neu": (
        gettext_noop("Jede Woche ist ein neuer Start. Alles, was du gesammelt hast, bleibt."),
        gettext_noop("Eine neue Woche, ein neuer Start. Deine Punkte bleiben."),
        gettext_noop("Neue Woche, neuer Start. Deine Punkte bleiben unverändert."),
    ),
    "vergleich_passt": (
        gettext_noop("Du hast dich richtig eingeschätzt!"),
        gettext_noop("Deine Einschätzung hat gestimmt."),
        gettext_noop("Deine Einschätzung war treffend."),
    ),
    "vergleich_mehr": (
        gettext_noop("Du kannst mehr, als du gedacht hast!"),
        gettext_noop("Du wusstest mehr, als du erwartet hast."),
        gettext_noop("Du wusstest mehr als erwartet."),
    ),
    "vergleich_weniger": (
        gettext_noop("Einiges ist noch neu für dich. Das üben wir weiter."),
        gettext_noop("Einiges war schwerer als gedacht. Das kommt bald wieder dran."),
        gettext_noop("Einiges war schwerer als erwartet. Es kommt zur Wiederholung."),
    ),
}


def ton(schluessel, stufe=STUFE_MITTE, **parameter):
    """Der Satz zu ``schluessel`` in der Sprachstufe, übersetzt, mit eingesetzten Parametern."""
    text = gettext(_TEXTE[schluessel][stufe - 1])
    return text % parameter if parameter else text


def schluessel():
    return tuple(_TEXTE)


def msgid(schluessel, stufe=STUFE_MITTE):
    """Der unübersetzte Satz, z. B. für ein Ereignis, das erst beim Rendern übersetzt wird."""
    return _TEXTE[schluessel][stufe - 1]
