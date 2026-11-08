"""Wechseltext der Startseite: gemischte Liste aus Sprüchen, Weisheiten, Fakten, eigenen Sprüchen
der Eltern und anonymen Familien-/Tages-Infos.

Datenschutz-Regel: Familien-Infos nennen NIE einen Namen (weder Kind noch Eltern), sondern
sprechen immer die ganze Familie an. Jede Info wird einzeln berechnet; ein Fehler darin
(fehlendes Modul, fehlende Einstellung, Datenfehler) lässt nur diese Info weg und kippt die
Startseite nie (wie ``kacheln``).

Sprache: Die Paare liegen in ``sprueche`` (Ausnahme von den ``.po``-Dateien, siehe
``docs/i18n.md``); gewählt wird über die aktive Sprache."""

import logging
import random
from zoneinfo import ZoneInfo

from django.utils import translation

from apps.aufgaben import selectors as aufgaben
from apps.aufgaben import services as aufgaben_services
from apps.kern import einstellungen, sprache, zeit
from apps.konten import begruessung

from . import sprueche

logger = logging.getLogger(__name__)

ANZAHL = 30
INFO_ANTEIL = 0.5  # etwa die Hälfte Familien-/Tages-Infos, wenn vorhanden
INFO_VARIANTEN = 2  # so viele Formulierungen je Info kommen in eine Liste
EIGENE_MAX = 8
EIGENE_SCHLUESSEL = "oberflaeche.eigene_sprueche"
# Mischung der festen Texte (Sprüche, Weisheiten, Fakten)
GEWICHT = {"spruch": 0.4, "weisheit": 0.25, "fakt": 0.35}


def _sprache():
    return (translation.get_language() or "de")[:2]


def _lokal(jetzt):
    try:
        return zeit.lokal(jetzt)
    except Exception:  # z. B. vor der Einrichtung ohne Zeitzone
        return jetzt.astimezone(ZoneInfo("Europe/Berlin"))


def _einheit(n, de, en, lang):
    """``(singular, plural)`` je Sprache -> passender Text für ``n``."""
    sg_pl = de if lang == "de" else en
    return sg_pl[0] if n == 1 else sg_pl[1]


# --- Familien- und Tages-Infos --------------------------------------------------------------
# Je Info: Liste von Varianten ``(de, en)`` mit benannten Platzhaltern. Namen kommen nie vor.

_LERNEN = [
    (
        "Heute wurden schon {n} {einheit} gelernt – die Gehirnzellen feiern 🧠",
        "{n} {einheit} of learning today – the brain cells are celebrating 🧠",
    ),
    (
        "Gemeinsam {n} {einheit} gelernt heute. Das Gehirn sagt: weiter so!",
        "{n} {einheit} of learning together today. The brain says: keep it up!",
    ),
    (
        "Schon {n} {einheit} Köpfchen-Training heute – ihr seid richtig schlau unterwegs",
        "Already {n} {einheit} of brain training today - you're on a smart path",
    ),
]
_LERNEN_NULL = [
    (
        "Heute wurde noch nicht gelernt – die Gehirnzellen machen ein Nickerchen 😴",
        "No learning yet today - the brain cells are taking a nap 😴",
    ),
    (
        "Die Lernecke wartet noch auf den ersten Besuch des Tages",
        "The learning corner is still waiting for its first visitor today",
    ),
]
_ZIEL_OFFEN = [
    (
        "Noch {n} {einheit} bis „{titel}“ – wer schnappt sich die nächste Aufgabe?",
        "{n} {einheit} to go until “{titel}” - who grabs the next chore?",
    ),
    (
        "Familienziel „{titel}“: Es fehlen nur noch {n} {einheit}",
        "Family goal “{titel}”: only {n} {einheit} still missing",
    ),
    (
        "Noch {n} {einheit} bis zum Familienziel – gemeinsam schaffen wir das!",
        "{n} {einheit} to the family goal - together we can do it!",
    ),
]
_ZIEL_ERREICHT = [
    (
        "Das Familienziel der Woche ist geschafft – Applaus für alle! 🎉",
        "This week's family goal is reached - a round of applause for everyone! 🎉",
    ),
    (
        "Familienziel erreicht! Das war richtig gute Teamarbeit",
        "Family goal reached! That was great teamwork",
    ),
]
_ERLEDIGT = [
    (
        "Heute wurden schon {n} {einheit} erledigt – die Familie ist in Fahrt",
        "{n} {einheit} done today - the family is on a roll",
    ),
    (
        "{n} {einheit} sind heute schon vom Tisch. Weiter so!",
        "{n} {einheit} are already ticked off today. Keep going!",
    ),
    ("Familien-Zwischenstand: {n} {einheit} geschafft ✅", "Family update: {n} {einheit} done ✅"),
]
_ERLEDIGT_NULL = [
    (
        "Heute ist noch alles offen – der erste Punkt wartet auf euch",
        "Everything is still open today - the first point is waiting for you",
    ),
    (
        "Noch nichts erledigt – der Tag ist aber noch jung!",
        "Nothing done yet - but the day is still young!",
    ),
]
_OFFEN_EINS = [
    ("1 freie Aufgabe wartet auf mutige Hände", "1 free chore is waiting for brave hands"),
    ("Frei zum Übernehmen: 1 Aufgabe. Fertig, los!", "Free to take: 1 chore. Ready, set, go!"),
]
_OFFEN_VIELE = [
    ("{n} freie Aufgaben warten auf mutige Hände", "{n} free chores are waiting for brave hands"),
    (
        "Frei zum Übernehmen: {n} Aufgaben. Fertig, los!",
        "Free to take: {n} chores. Ready, set, go!",
    ),
]
_OFFEN_NULL = [
    (
        "Alle freien Aufgaben sind vergeben – ihr seid unschlagbar 🏆",
        "All the free chores are taken - you're unbeatable 🏆",
    ),
    (
        "Keine freie Aufgabe mehr da. Zeit für eine kleine Pause!",
        "No free chores left. Time for a little break!",
    ),
]
_MORGEN_EINE = [
    ("Morgen wartet „{titel}“ auf einen Helden 🦸", "Tomorrow, “{titel}” is waiting for a hero 🦸"),
    (
        "Morgen steht „{titel}“ im Wochenplan – wer meldet sich?",
        "Tomorrow “{titel}” is on the weekly plan - who volunteers?",
    ),
    ("Kleine Vorschau: Morgen ist „{titel}“ dran", "Little preview: tomorrow it's “{titel}” time"),
]
_MORGEN_VIELE = [
    (
        "Morgen stehen {n} Aufgaben im Wochenplan, zum Beispiel „{titel}“",
        "Tomorrow there are {n} chores on the weekly plan, for example “{titel}”",
    ),
    (
        "Für morgen sind {n} feste Aufgaben geplant. Los geht’s mit „{titel}“?",
        "{n} regular chores are planned for tomorrow. Starting with “{titel}”?",
    ),
]
_WOCHENENDE_BALD = [
    (
        "Noch {n} {einheit} bis zum Wochenende – ihr habt es gleich geschafft!",
        "{n} {einheit} until the weekend - you're almost there!",
    ),
    (
        "Das Wochenende ist in {n} {einheit} da. Durchhalten!",
        "The weekend arrives in {n} {einheit}. Hang in there!",
    ),
]
_WOCHENENDE_MORGEN = [
    ("Nur noch einmal schlafen, dann ist Wochenende!", "Just one more sleep until the weekend!"),
    (
        "Morgen beginnt das Wochenende – Pfannkuchen-Alarm voraus 🥞",
        "The weekend starts tomorrow - pancake alert ahead 🥞",
    ),
]
_WOCHENENDE_DA = [
    (
        "Wochenende! Heute darf die Familie ein bisschen langsamer machen",
        "It's the weekend! The family may take it a little slower today",
    ),
    (
        "Das Wochenende ist da – Pyjama-Pläne sind erlaubt",
        "The weekend is here - pyjama plans are allowed",
    ),
]
_SONNTAG_ABEND = [
    (
        "Morgen geht die Woche wieder los – heute noch Kraft tanken",
        "The week starts again tomorrow - recharge today",
    ),
]


def _wahl(varianten, lang, **werte):
    return [(de if lang == "de" else en).format(**werte) for de, en in varianten]


def _info_lernen(jetzt_lokal, lang):
    from apps.lernen import selectors as lernen

    minuten = lernen.lernminuten_heute(jetzt_lokal.date())
    if minuten >= 1:
        einheit = _einheit(minuten, ("Minute", "Minuten"), ("minute", "minutes"), lang)
        return _wahl(_LERNEN, lang, n=minuten, einheit=einheit)
    if jetzt_lokal.hour >= 14:  # morgens wäre „noch nichts“ unfair
        return _wahl(_LERNEN_NULL, lang)
    return []


def _info_familienziel(jetzt_lokal, lang):
    from apps.familienziel import selectors as familienziel

    ansicht = familienziel.ansicht()
    if ansicht.erreicht:
        return _wahl(_ZIEL_ERREICHT, lang)
    if ansicht.fehlt <= 0:
        return []
    einheit = _einheit(ansicht.fehlt, ("Punkt", "Punkte"), ("point", "points"), lang)
    if ansicht.belohnung is not None and str(ansicht.belohnung).strip():
        varianten = _ZIEL_OFFEN
    else:
        varianten = _ZIEL_OFFEN[2:]
    return _wahl(varianten, lang, n=ansicht.fehlt, einheit=einheit, titel=str(ansicht.belohnung))


def _info_erledigt(jetzt_lokal, lang):
    n = aufgaben_services.heute_erledigt(jetzt_lokal).count()
    if n >= 1:
        einheit = _einheit(n, ("Aufgabe", "Aufgaben"), ("chore", "chores"), lang)
        return _wahl(_ERLEDIGT, lang, n=n, einheit=einheit)
    if 12 <= jetzt_lokal.hour < 18:
        return _wahl(_ERLEDIGT_NULL, lang)
    return []


def _info_offen(jetzt_lokal, lang):
    n = len(aufgaben.start_offene(jetzt=jetzt_lokal))
    if n == 0:
        return _wahl(_OFFEN_NULL, lang)
    return _wahl(_OFFEN_EINS if n == 1 else _OFFEN_VIELE, lang, n=n)


def _info_morgen(jetzt_lokal, lang):
    tage = aufgaben.start_woche(heute=jetzt_lokal.date())
    morgen = next((t for t in tage if t["datum"] > jetzt_lokal.date()), None)
    if morgen is None:
        return []
    # Die Anmeldeseite nennt nur freie Aufgaben; zugeteilte würden ein Kind verraten.
    titel = [sprache.uebersetzt(a.titel) for a in morgen["aufgaben"] if a.zugewiesen_an_id is None]
    if not titel:
        return []
    n = len(titel)
    if n == 1:
        return _wahl(_MORGEN_EINE, lang, titel=titel[0])
    return _wahl(_MORGEN_VIELE, lang, n=n, titel=titel[0]) + _wahl(
        _MORGEN_EINE[:1], lang, titel=titel[1]
    )


def _info_wochenende(jetzt_lokal, lang):
    tag = jetzt_lokal.weekday()  # 0 = Montag
    if tag >= 5:
        if tag == 6 and jetzt_lokal.hour >= 17:
            return _wahl(_SONNTAG_ABEND, lang)
        return _wahl(_WOCHENENDE_DA, lang)
    bis = 5 - tag
    if bis == 1:
        return _wahl(_WOCHENENDE_MORGEN, lang)
    einheit = _einheit(bis, ("Tag", "Tage"), ("day", "days"), lang)
    return _wahl(_WOCHENENDE_BALD, lang, n=bis, einheit=einheit)


INFOS = (
    ("lernen", _info_lernen),
    ("familienziel", _info_familienziel),
    ("erledigt", _info_erledigt),
    ("offen", _info_offen),
    ("morgen", _info_morgen),
    ("wochenende", _info_wochenende),
)


def familien_infos(jetzt=None, lang=None):
    """Alle gerade sinnvollen Familien-/Tages-Infos: ``{schluessel: [Variante, ...]}``.
    Anonym; eine fehlerhafte Info fehlt einfach."""
    jetzt = jetzt or zeit.jetzt()
    lang = lang or _sprache()
    lokal = _lokal(jetzt)
    ergebnis = {}
    for schluessel, funktion in INFOS:
        try:
            texte = funktion(lokal, lang)
        except Exception:
            logger.exception(
                "Info %s für den Wechseltext konnte nicht berechnet werden", schluessel
            )
            continue
        if texte:
            ergebnis[schluessel] = texte
    return ergebnis


# --- Feste Texte und Mischung ---------------------------------------------------------------


def passende_eintraege(jetzt=None, art=None):
    """Alle Einträge aus ``sprueche``, die zu Tageszeit, Wochentag und Jahreszeit passen."""
    lokal = _lokal(jetzt or zeit.jetzt())
    tz = sprueche.tageszeit(lokal.hour)
    jz = sprueche.jahreszeit(lokal.month)
    return [
        e
        for e in sprueche.EINTRAEGE
        if (art is None or e["art"] == art)
        and sprueche.passend(e, tageszeit_=tz, wochentag=lokal.weekday(), jahreszeit_=jz)
    ]


def eigene_sprueche():
    """Eigene Sprüche der Eltern (Einstellung); fehlt sie, gibt es keine."""
    try:
        zeilen = einstellungen.wert(EIGENE_SCHLUESSEL)
    except einstellungen.EinstellungFehlt:
        return []
    except Exception:
        logger.exception("Eigene Sprüche konnten nicht gelesen werden")
        return []
    return [z.strip() for z in zeilen if z and z.strip()]


def _text(eintrag, lang):
    return eintrag["de"] if lang == "de" else eintrag["en"]


def wechseltexte(jetzt=None, *, anzahl=ANZAHL, zufall=None, lang=None):
    """Gemischte Textliste für die Startseite (Strings). Der erste Text ist der Tageszeit-Gruß."""
    jetzt = jetzt or zeit.jetzt()
    zufall = zufall or random.Random()
    lang = lang or _sprache()

    erster = f"{begruessung.gruss(jetzt)}!"
    gesehen = {erster}

    infos = []
    for varianten in familien_infos(jetzt, lang).values():
        infos.extend(zufall.sample(varianten, min(INFO_VARIANTEN, len(varianten))))
    ziel_infos = round((anzahl - 1) * INFO_ANTEIL)
    if len(infos) > ziel_infos:
        infos = zufall.sample(infos, ziel_infos)

    eigene = eigene_sprueche()
    eigene = zufall.sample(eigene, min(EIGENE_MAX, len(eigene)))

    rest = max(anzahl - 1 - len(infos) - len(eigene), 0)
    fest = []
    gruesse_ = [_text(e, lang) for e in passende_eintraege(jetzt, "gruss")]
    for art, gewicht in GEWICHT.items():
        pool = [_text(e, lang) for e in passende_eintraege(jetzt, art)]
        fest.extend(zufall.sample(pool, min(len(pool), round(rest * gewicht))))
    # ein bis zwei weitere Grüße der Tageszeit, wenn Platz ist
    fest.extend(zufall.sample(gruesse_, min(2, len(gruesse_))))

    # Infos und eigene Sprüche haben Vorrang; gekürzt wird nur der feste Vorrat,
    # sonst könnte das Abschneiden auf ``anzahl`` gerade die eigenen Sprüche treffen.
    vorrang = []
    for text in infos + eigene:
        if text not in gesehen:
            gesehen.add(text)
            vorrang.append(text)
    zufall.shuffle(fest)
    rest_fest = []
    for text in fest:
        if len(vorrang) + len(rest_fest) >= anzahl - 1:
            break
        if text not in gesehen:
            gesehen.add(text)
            rest_fest.append(text)
    mix = vorrang[: anzahl - 1] + rest_fest
    zufall.shuffle(mix)
    return [erster, *mix]
