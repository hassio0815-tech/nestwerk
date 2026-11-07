"""Wochen-Digest für die Eltern (Etappe 13, E-3, Text X5).

Eine Nachricht pro Woche an alle Eltern (Push; Mail kann jedes Elternteil bei den
Benachrichtigungen zuschalten): Kopfzeile, je Kind zwei Zeilen (geübte Tage, ein Vorschlag),
offene Freigaben, Prüfungen. Höchstens 8 Zeilen. Kein Vergleich zwischen Kindern, keine Rangfolge:
die Kinder stehen in der Reihenfolge ihres Namens, jede Zeile handelt von einem Kind allein.

Das Ereignis enthält nur msgid und Parameter; übersetzt wird beim Zustellen in der Sprache jedes
Elternteils (``benachrichtigung.texte``).
"""

from datetime import timedelta

from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext_noop, ngettext

from apps.benachrichtigung import texte
from apps.ereignisse import services as ereignisse
from apps.ereignisse.models import Ereignis
from apps.kern import zeit
from apps.kern.einstellungen import wert
from apps.konten import selectors as konten

from . import events, material_selectors, tagesziel, woche_selectors

ZEILEN_MAX = 8

# Ein Vorschlag je Kind, kurz genug für eine Push-Zeile. Schlüssel wie in ``woche_texte``.
_VORSCHLAG = {
    "wochenziel_geschafft": (gettext_noop("Vorschlag: kurz loben."), ()),
    "kein_uebungstag": (gettext_noop("Vorschlag: gemeinsam mit 5 Minuten starten."), ()),
    "weniger_tage": (gettext_noop("Vorschlag: einen festen Übungszeitpunkt ausmachen."), ()),
    "schwaeche": (
        gettext_noop("Vorschlag: %(minuten)s Minuten %(thema)s einplanen."),
        ("minuten", "thema"),
    ),
    "viel_hilfe": (gettext_noop("Vorschlag: schauen, welche Hilfe nötig war."), ()),
    "weniger_hilfe": (gettext_noop("Vorschlag: sagen, dass ihr die Fortschritte seht."), ()),
    "tutor_hohe_stufe": (gettext_noop("Vorschlag: das Kind erklären lassen."), ()),
    "zu_optimistisch": (gettext_noop("Vorschlag: über das Einschätzen sprechen."), ()),
    "traut_sich_zu_wenig": (gettext_noop("Vorschlag: dem Kind sagen, dass es mehr kann."), ()),
    "meldung_zu_schwer": (
        gettext_noop("Vorschlag: nachfragen, was in %(fach)s schwer war."),
        ("fach",),
    ),
    "meldung_zu_leicht": (
        gettext_noop("Vorschlag: in %(fach)s eine Herausforderung anbieten."),
        ("fach",),
    ),
    "pruefung_ohne_plan": (
        gettext_noop("Vorschlag: für die Prüfung %(titel)s gemeinsam planen."),
        ("titel",),
    ),
    "pruefung_knapp": (
        gettext_noop("Vorschlag: für die Prüfung %(titel)s einen Termin ergänzen."),
        ("titel",),
    ),
}


# Einzahl und Mehrzahl als Paar (``ngettext`` beim Zustellen, ``zeilen_text``)
KOPF = (
    "Lernwoche %(kw)s: %(geuebt)s von %(n)s Kind hat an %(tage)s+ Tagen geübt.",
    "Lernwoche %(kw)s: %(geuebt)s von %(n)s Kindern haben an %(tage)s+ Tagen geübt.",
)
TAGE = ("%(kind)s: %(n)s Tag geübt.", "%(kind)s: %(n)s Tage geübt.")
FREIGABEN = (
    "%(n)s Material wartet auf eure Freigabe.",
    "%(n)s Materialien warten auf eure Freigabe.",
)
PRUEFUNGEN = (
    "%(n)s Prüfung in den nächsten %(tage)s Tagen.",
    "%(n)s Prüfungen in den nächsten %(tage)s Tagen.",
)


def _msgids_fuer_makemessages(n):
    """Nur damit ``makemessages`` die Paare als Mehrzahl findet; die Texte stehen oben."""
    return (
        ngettext(
            "Lernwoche %(kw)s: %(geuebt)s von %(n)s Kind hat an %(tage)s+ Tagen geübt.",
            "Lernwoche %(kw)s: %(geuebt)s von %(n)s Kindern haben an %(tage)s+ Tagen geübt.",
            n,
        ),
        ngettext("%(kind)s: %(n)s Tag geübt.", "%(kind)s: %(n)s Tage geübt.", n),
        ngettext(
            "%(n)s Material wartet auf eure Freigabe.",
            "%(n)s Materialien warten auf eure Freigabe.",
            n,
        ),
        ngettext(
            "%(n)s Prüfung in den nächsten %(tage)s Tagen.",
            "%(n)s Prüfungen in den nächsten %(tage)s Tagen.",
            n,
        ),
    )


def _woche(jetzt):
    """Montag der Woche, über die berichtet wird: ab Freitag die laufende, vorher die letzte."""
    heute = zeit.heute(jetzt)
    montag = tagesziel.montag(heute)
    return heute, montag if heute.weekday() >= 4 else montag - timedelta(days=7)


def faellig(jetzt):
    """Ist jetzt Digest-Zeit? Am eingestellten Wochentag ab der eingestellten Uhrzeit (Ortszeit),
    bis Mitternacht. Der Dedupe-Schlüssel sorgt dafür, dass es dennoch nur einmal gesendet wird."""
    if not wert("lernen.digest_aktiv"):
        return False
    lokal = zeit.lokal(jetzt)
    return lokal.weekday() == wert("lernen.digest_wochentag") and lokal.time() >= wert(
        "lernen.digest_uhrzeit"
    )


def _zeile(msgid, plural=None, **parameter):
    eintrag = {"msgid": msgid, "parameter": parameter}
    if plural:
        eintrag["msgid_plural"] = plural
    return eintrag


def _vorschlag(bild):
    if not bild.vorschlaege:
        return None
    erster = bild.vorschlaege[0]
    msgid, felder = _VORSCHLAG[erster.schluessel]
    return _zeile(msgid, **{f: erster.parameter[f] for f in felder})


def _text(eintraege):
    with translation.override("de"):
        return texte.zeilen_text([e["zeile"] for e in eintraege])


def _kuerzen(eintraege):
    """Wirft das Unwichtigste zuerst weg, bis es passt: Prüfungen, Vorschläge (von hinten),
    Freigaben, dann Kinder von hinten. Die Kopfzeile bleibt."""
    reihenfolge = ("pruefungen", "vorschlag", "freigaben", "tage")
    while len(eintraege) > ZEILEN_MAX or len(_text(eintraege)) > texte.TEXT_MAX:
        for art in reihenfolge:
            kandidaten = [i for i, e in enumerate(eintraege) if e["art"] == art]
            if kandidaten:
                del eintraege[kandidaten[-1] if art != "pruefungen" else kandidaten[0]]
                break
        else:
            break
    return eintraege


def zeilen(jetzt):
    """``(kw, schluessel, zeilen)`` des Digests oder ``None``, wenn es keine Kinder gibt."""
    heute, montag = _woche(jetzt)
    kinder = sorted(konten.aktive_kinder(), key=lambda k: (k.anzeigename, k.pk))
    if not kinder:
        return None
    soll = wert("lernen.familienziel_tage")
    bilder = [woche_selectors.wochenbild(k, heute, montag) for k in kinder]
    kw = montag.isocalendar().week
    n = len(kinder)
    geuebt = sum(1 for b in bilder if b.tage_geuebt >= soll)

    eintraege = [
        {
            "art": "kopf",
            "zeile": _zeile(
                KOPF[0],
                KOPF[1],
                kw=kw,
                geuebt=geuebt,
                n=n,
                tage=soll,
            ),
        }
    ]
    for kind, bild in zip(kinder, bilder, strict=True):
        eintraege.append(
            {
                "art": "tage",
                "zeile": _zeile(
                    TAGE[0],
                    TAGE[1],
                    kind=kind.anzeigename,
                    n=bild.tage_geuebt,
                ),
            }
        )
        vorschlag = _vorschlag(bild)
        if vorschlag:
            eintraege.append({"art": "vorschlag", "zeile": vorschlag})
    offen = material_selectors.warten_auf_eltern().filter(kind__in=kinder).count()
    if offen:
        eintraege.append(
            {
                "art": "freigaben",
                "zeile": _zeile(
                    FREIGABEN[0],
                    FREIGABEN[1],
                    n=offen,
                ),
            }
        )
    pruefungen = sum(len(b.pruefungen) for b in bilder)
    if pruefungen:
        eintraege.append(
            {
                "art": "pruefungen",
                "zeile": _zeile(
                    PRUEFUNGEN[0],
                    PRUEFUNGEN[1],
                    n=pruefungen,
                    tage=wert("lernen.woche_pruefung_tage"),
                ),
            }
        )
    eintraege = _kuerzen(eintraege)
    return (
        kw,
        f"{events.WOCHENBILD}:{montag.isocalendar().year}-W{kw:02d}",
        [e["zeile"] for e in eintraege],
    )


@transaction.atomic
def senden(jetzt=None):
    """Veröffentlicht den Digest der Woche, wenn es ihn noch nicht gibt und Kinder da sind.
    Gibt ``True`` zurück, wenn ein neues Ereignis entstand."""
    jetzt = jetzt or zeit.jetzt()
    inhalt = zeilen(jetzt)
    if inhalt is None:
        return False
    kw, schluessel, liste = inhalt
    if Ereignis.objects.filter(schluessel=schluessel).exists():
        return False
    ereignisse.veroeffentlichen(
        events.WOCHENBILD, daten={"kw": kw, "zeilen": liste}, schluessel=schluessel
    )
    return True
