"""Texte der Wochenansichten (SPEC 21.9, 21.10): Wochen-Titel und Handlungsvorschläge.

Alles Deutsch als msgid (``gettext_noop``), übersetzt erst beim Anzeigen. Ein Vorschlag ist ein
Schlüssel mit Parametern, nie ein fertiger Satz: so bleibt er in jeder Sprache lesbar. Der Ton
ist ein Angebot für ein Gespräch, nie eine Bewertung."""

from dataclasses import dataclass, field

from django.utils.translation import gettext, gettext_noop

_TITEL = {
    "uebungsmeister": (
        gettext_noop("Übungsmeister"),
        gettext_noop("Am häufigsten das eigene Tagesziel geschafft."),
    ),
    "aufsteiger": (
        gettext_noop("Aufsteiger"),
        gettext_noop("Im Vergleich zur Vorwoche mehr Treffer und weniger Hilfe."),
    ),
    "durchbeisser": (
        gettext_noop("Durchbeißer"),
        gettext_noop("Die meisten eigenen Fehler selbst geklärt."),
    ),
    "entdecker": (
        gettext_noop("Entdecker"),
        gettext_noop("Ein neues Thema angefangen."),
    ),
}

_VORSCHLAEGE = {
    "wochenziel_geschafft": gettext_noop(
        "Das Wochenziel ist geschafft. Ein kurzes Lob freut das Kind."
    ),
    "kein_uebungstag": gettext_noop(
        "Diese Woche gab es noch keinen Übungstag. Ein gemeinsamer Start mit 5 Minuten kann helfen."
    ),
    "weniger_tage": gettext_noop(
        "Es waren %(tage)s von %(soll)s Übungstagen. Ein fester Zeitpunkt am Tag macht das Üben "
        "leichter."
    ),
    "schwaeche": gettext_noop(
        "Im Fach %(fach)s fiel %(thema)s schwer. Plane %(minuten)s Minuten %(thema)s ein."
    ),
    "viel_hilfe": gettext_noop(
        "Das Kind hat oft Hilfe genutzt. Schaut zusammen, welche Hilfe wirklich nötig war."
    ),
    "weniger_hilfe": gettext_noop(
        "Das Kind braucht weniger Hilfe als in den Wochen davor. Sagt ihm ruhig, dass ihr das seht."
    ),
    "tutor_hohe_stufe": gettext_noop(
        "Der Tutor musste oft auf hoher Stufe helfen. Lasst das Kind erklären, was es schon "
        "versteht."
    ),
    "zu_optimistisch": gettext_noop(
        "Das Kind hat sich öfter besser eingeschätzt, als es lief. Sprecht darüber, woran man "
        "merkt, ob man etwas schon kann."
    ),
    "traut_sich_zu_wenig": gettext_noop(
        "Das Kind kann mehr, als es sich zutraut. Sagt ihm das ruhig."
    ),
    "meldung_zu_schwer": gettext_noop(
        "Das Kind meldet, dass %(fach)s zu schwer war. Fragt nach, was genau schwer war."
    ),
    "meldung_zu_leicht": gettext_noop(
        "Das Kind meldet, dass %(fach)s zu leicht war. Schlagt die Herausforderung vor."
    ),
    "pruefung_ohne_plan": gettext_noop(
        "Für die Prüfung %(titel)s (%(fach)s) am %(datum)s passt noch kein Plan. Schaut gemeinsam "
        "auf die Vorschläge im Realitätscheck."
    ),
    "pruefung_knapp": gettext_noop(
        "Die Prüfung %(titel)s ist in %(tage)s Tagen. Vom Plan sind %(prozent)s Prozent geschafft. "
        "Plant gemeinsam einen zusätzlichen Termin ein."
    ),
}


def titel_name(schluessel):
    return gettext(_TITEL[schluessel][0])


def titel_beschreibung(schluessel):
    return gettext(_TITEL[schluessel][1])


def titel_schluessel():
    return tuple(_TITEL)


def vorschlag_schluessel():
    return tuple(_VORSCHLAEGE)


@dataclass(frozen=True)
class Vorschlag:
    """Handlungsvorschlag: ``schluessel`` + ``parameter`` (msgid wird erst beim Anzeigen
    übersetzt)."""

    schluessel: str
    parameter: dict = field(default_factory=dict)

    @property
    def msgid(self):
        return _VORSCHLAEGE[self.schluessel]

    @property
    def text(self):
        text = gettext(self.msgid)
        return text % self.parameter if self.parameter else text
