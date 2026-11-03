"""Töne der Prüfungsvorbereitung (SPEC 21.2, 21.7): ohne Vorwurf, nach Sprachstufe.

Aufbau wie ``texte``: je Schlüssel drei Sätze (Stufe 1 bis 3, ``gettext_noop``), übersetzt erst beim
Anzeigen. Verpasste Tage sind kein Fehler: der Plan passt sich an, die Punkte bleiben.
"""

from django.utils.translation import gettext, gettext_noop

from .texte import STUFE_MITTE

_TEXTE = {
    "angepasst": (
        gettext_noop("Kein Problem, ich habe den Plan angepasst. Wir machen einfach weiter."),
        gettext_noop("Kein Problem, ich habe den Plan angepasst."),
        gettext_noop("Kein Problem, der Plan ist angepasst."),
    ),
    "puffer_genutzt": (
        gettext_noop("Ich habe einen Puffertag genutzt, damit alles Platz hat."),
        gettext_noop("Dafür habe ich einen Puffertag genutzt, damit alles Platz hat."),
        gettext_noop("Ein Puffertag wurde dafür genutzt."),
    ),
    "zu_viel": (
        gettext_noop(
            "Das ist so zu viel. Du brauchst etwa %(braucht)s Minuten, hast aber nur etwa %(hat)s "
            "Minuten Zeit. Ich mache dir keinen vollen Plan, der nicht klappt. Du entscheidest, "
            "was wir ändern."
        ),
        gettext_noop(
            "Das ist so zu viel: Du brauchst etwa %(braucht)s Minuten und hast etwa %(hat)s "
            "Minuten Zeit. Ich plane nichts Überfülltes. Du entscheidest, was wir ändern."
        ),
        gettext_noop(
            "Das ist so zu viel: Bedarf etwa %(braucht)s Minuten, verfügbar etwa %(hat)s Minuten. "
            "Ein überfüllter Plan bringt nichts. Ihr entscheidet, was sich ändert."
        ),
    ),
    "vorschlag_frueher": (
        gettext_noop("Früher anfangen: Mit %(tage)s Tagen mehr Zeit würde es klappen."),
        gettext_noop("Früher anfangen: Mit etwa %(tage)s Tagen mehr Zeit würde es klappen."),
        gettext_noop("Früher beginnen: Etwa %(tage)s Tage mehr Zeit würden reichen."),
    ),
    "vorschlag_kleiner": (
        gettext_noop("Den Stoff kleiner machen: Etwa %(fragen)s Fragen weniger, dann passt es."),
        gettext_noop("Den Stoff verkleinern: Mit etwa %(fragen)s Fragen weniger passt es."),
        gettext_noop("Stoff verkleinern: Etwa %(fragen)s Fragen weniger würden reichen."),
    ),
    "vorschlag_ziel": (
        gettext_noop(
            "Pro Tag etwas länger üben: %(minuten)s Minuten statt deines Ziels. Nur, wenn du das "
            "möchtest."
        ),
        gettext_noop(
            "Das Tagesziel etwas erhöhen: auf %(minuten)s Minuten. Nur, wenn du das möchtest."
        ),
        gettext_noop(
            "Das Tagesziel auf %(minuten)s Minuten erhöhen. Das ist ein Vorschlag, du entscheidest."
        ),
    ),
    "vorschlag_keiner": (
        gettext_noop("Gerade sehe ich keinen kleinen Ausweg. Sprich mit deinen Eltern darüber."),
        gettext_noop("Hier sehe ich keinen kleinen Ausweg. Sprich mit deinen Eltern darüber."),
        gettext_noop("Hier hilft keine kleine Änderung. Sprecht gemeinsam über Termin und Stoff."),
    ),
    "termin_vorbei": (
        gettext_noop("Der Termin ist nicht in der Zukunft. Wähle einen Tag nach heute."),
        gettext_noop("Der Termin muss nach heute liegen. Wähle einen späteren Tag."),
        gettext_noop("Der Termin muss in der Zukunft liegen."),
    ),
    "kein_stoff": (
        gettext_noop("Wähle zuerst aus, was du lernen musst."),
        gettext_noop("Wähle zuerst den Stoff aus, den du lernen musst."),
        gettext_noop("Wähle zuerst den Stoff für die Prüfung aus."),
    ),
    "knapp": (
        gettext_noop("Der Termin ist bald. Fang am besten heute an, Schritt für Schritt."),
        gettext_noop("Der Termin ist bald. Fang am besten heute an."),
        gettext_noop("Der Termin ist nah. Beginne am besten heute."),
    ),
    "heute_frei": (
        gettext_noop("Heute steht nichts an. Du darfst trotzdem üben."),
        gettext_noop("Heute steht nichts im Plan. Üben darfst du trotzdem."),
        gettext_noop("Heute ist nichts geplant. Freiwilliges Üben ist möglich."),
    ),
    "heute_puffer": (
        gettext_noop("Heute ist ein Puffertag. Er ist da, falls mal etwas ausfällt."),
        gettext_noop("Heute ist ein Puffertag, eine Reserve für den Fall, dass etwas ausfällt."),
        gettext_noop("Heute ist ein Puffertag (Reserve)."),
    ),
    "portion_geschafft": (
        gettext_noop("Portion geschafft! Das war ein guter Schritt."),
        gettext_noop("Portion geschafft. Ein guter Schritt."),
        gettext_noop("Portion erledigt."),
    ),
    "woche_geschafft": (
        gettext_noop("Du hast diese Woche deinen Plan eingehalten! Das ist stark."),
        gettext_noop("Planwoche eingehalten. Das ist richtig gut."),
        gettext_noop("Planwoche eingehalten."),
    ),
    "vorbereitet": (
        gettext_noop("Dein Plan für %(titel)s ist geschafft. Du hast dich gut vorbereitet!"),
        gettext_noop("Dein Prüfungsplan für %(titel)s ist geschafft. Gut vorbereitet!"),
        gettext_noop("Prüfungsplan eingehalten: %(titel)s ist vorbereitet."),
    ),
    "probe_staerke": (
        gettext_noop("Das kannst du schon gut."),
        gettext_noop("Das sitzt schon gut."),
        gettext_noop("Hier bist du sicher."),
    ),
    "probe_mitte": (
        gettext_noop("Das ist auf einem guten Weg."),
        gettext_noop("Das ist auf gutem Weg."),
        gettext_noop("Hier bist du auf gutem Weg."),
    ),
    "probe_ueben": (
        gettext_noop("Das üben wir noch ein bisschen."),
        gettext_noop("Das üben wir noch."),
        gettext_noop("Das lohnt sich noch zu üben."),
    ),
    "probe_hinweis": (
        gettext_noop(
            "Das ist keine Note. Es zeigt dir nur, was du schon gut kannst und was du noch üben "
            "magst."
        ),
        gettext_noop(
            "Das ist keine Note. Es zeigt nur, was schon sitzt und was du noch üben kannst."
        ),
        gettext_noop("Das ist keine Note, sondern ein Hinweis auf Stärken und Übungsbedarf."),
    ),
    "pause_im_zeitraum": (
        gettext_noop("In dieser Zeit hast du %(tage)s Tage Pause. Die plane ich nicht ein."),
        gettext_noop("%(tage)s Tage Pause sind eingetragen. Die plane ich nicht ein."),
        gettext_noop("%(tage)s Pausentage sind eingetragen und bleiben ohne Plan."),
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
