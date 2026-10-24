"""Texte der Benachrichtigungen je Ereignistyp (deutsch) und Deep-Links.

Module registrieren ihre Texte in ``AppConfig.ready()``:

    texte.text_registrieren(
        "aufgabe.gemeldet",
        titel="{kind} hat eine Aufgabe gemeldet",
        text="„{aufgabe}“ wartet auf deine Bestätigung.",
    )

Platzhalter ``{name}`` kommen aus ``Ereignis.daten`` sowie ``{kind}`` und ``{akteur}``
(Anzeigenamen).
Fehlt für einen Platzhalter ein Wert, greift der Rückfall: Titel = Bezeichnung des Ereignistyps,
Text = ``daten["text"]`` (falls vorhanden). Für die Typen des Ereigniskatalogs (ARCHITECTURE 5.2)
gibt es Standardtexte, die ein Modul mit ``text_registrieren`` überschreiben kann.
"""

import string
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured

TITEL_MAX = 120
TEXT_MAX = 400
LINK_MAX = 200


@dataclass(frozen=True)
class TypText:
    titel: str
    text: str = ""


_registriert = {}

_STANDARD = {
    "system.backup_fehler": TypText(
        "Datensicherung fehlgeschlagen", "Bitte Job-Läufe und Backup-Ordner prüfen (Runbook)."
    ),
    "aufgabe.interesse": TypText("{kind} möchte eine Aufgabe machen", "„{aufgabe}“"),
    "aufgabe.konflikt": TypText(
        "Mehrere möchten dieselbe Aufgabe", "„{aufgabe}“ braucht eine Zuteilung."
    ),
    "aufgabe.gemeldet": TypText(
        "{kind} hat eine Aufgabe gemeldet", "„{aufgabe}“ wartet auf Bestätigung."
    ),
    "aufgabe.bestaetigt": TypText("Aufgabe bestätigt!", "„{aufgabe}“ ist geschafft. Gut gemacht!"),
    "aufgabe.abgelehnt": TypText("Aufgabe nicht angenommen", "„{aufgabe}“ wurde abgelehnt."),
    "aufgabe.rueckfrage": TypText(
        "Rückfrage zur Aufgabe", "Zu „{aufgabe}“ gibt es eine Rückfrage."
    ),
    "reservierung.erinnerung": TypText("Deine Aufgabe wartet", "„{aufgabe}“ läuft bald ab."),
    "reservierung.abgelaufen": TypText(
        "Reservierung abgelaufen", "{kind} hat „{aufgabe}“ nicht gemacht."
    ),
    "aufgabe.verfall_vorwarnung": TypText(
        "Aufgabe läuft bald ab", "„{aufgabe}“ wurde noch nicht übernommen."
    ),
    "aufgabe.nicht_uebernommen": TypText(
        "Aufgabe nicht übernommen", "„{aufgabe}“ hat niemand übernommen."
    ),
    "belohnung.antrag": TypText(
        "{kind} möchte eine Belohnung", "„{belohnung}“ wartet auf Entscheidung."
    ),
    "belohnung.entschieden": TypText(
        "Entscheidung zu deiner Belohnung", "„{belohnung}“: {ergebnis}"
    ),
    "avatar.mod_fertig": TypText("Dein Mod ist fertig!", "„{mod}“ kann jetzt eingebaut werden."),
    "serie.gestiegen": TypText(
        "Serie: {wochenserie} Wochen!", "Woche {woche} geschafft. Weiter so!"
    ),
    "serie.gerissen": TypText(
        "Neue Woche, neue Serie",
        "Letzte Woche gab es keine Aufgabe. Schon eine Aufgabe startet deine Serie neu.",
    ),
    "pause.gestartet": TypText(
        "Pause – deine Serie ist sicher", "Pause {zeitraum}. Aufgaben zählen trotzdem."
    ),
    "pause.beendet": TypText("Pause vorbei", "{hinweis}"),
    "serienbonus.gebucht": TypText(
        "Serienbonus +{prozent} %", "+{punkte} Punkte für {serie} Wochen in Folge."
    ),
    "rang.aufgestiegen": TypText("Neuer Rang: {rang}!", "{kind} ist aufgestiegen."),
    "abzeichen.verliehen": TypText("Neues Abzeichen: {abzeichen}", "{kind}: {beschreibung}"),
    "spielregeln.rang_aufstieg": TypText("Neuer Rang: {rang}!", "{kind} ist aufgestiegen."),
    "spielregeln.abzeichen": TypText(
        "Neues Abzeichen: {abzeichen}", "{kind} hat ein Abzeichen verdient."
    ),
    "spielregeln.held": TypText(
        "{kind} ist Held der Woche", "{xp} Punkte, deutlich mehr als sonst ({prozent} % darüber)."
    ),
    "spielregeln.held_kind": TypText(
        "Du bist Held der Woche!", "{xp} Punkte: mehr als sonst. Stark gemacht!"
    ),
    "sondertag.freigeschaltet": TypText(
        "Sondertag freigeschaltet", "Du darfst dir etwas wünschen!"
    ),
    "sondertag.wunsch": TypText("Sondertag-Wunsch von {kind}", "{wunsch}"),
    "sondertag.angenommen": TypText("Dein Wunsch wurde angenommen", "{wunsch}"),
    "familienziel.erreicht": TypText(
        "{belohnung} freigeschaltet!", "Die Familie hat {ziel} Punkte geschafft."
    ),
    "familienziel.erreicht_kind": TypText(
        "Geschafft! {belohnung}", "Ihr habt das Familienziel erreicht. Super gemacht!"
    ),
    "familienziel.abstimmung_offen": TypText(
        "Abstimmung läuft", "Wähle jetzt die Belohnung für nächste Woche."
    ),
    "familienziel.abstimmung_gleichstand": TypText("Familienziel: Eltern entscheiden", "{hinweis}"),
    "familienziel.grossziel": TypText(
        "Großes Ziel freigeschaltet: {grossziel}!", "Mehrere Wochenziele in Folge geschafft."
    ),
    "familienziel.grossziel_kind": TypText(
        "Großes Ziel: {grossziel}!", "Ihr habt mehrere Wochenziele in Folge geschafft!"
    ),
}


def text_registrieren(typ_slug, *, titel, text=""):
    """Setzt Titel und Text eines Ereignistyps. Doppelte Registrierung ist ein Fehler."""
    if typ_slug in _registriert:
        raise ImproperlyConfigured(f"Text für '{typ_slug}' ist doppelt registriert")
    if not titel:
        raise ImproperlyConfigured(f"Text für '{typ_slug}': Titel fehlt")
    _registriert[typ_slug] = TypText(titel=titel, text=text)


def text_fuer(typ_slug):
    return _registriert.get(typ_slug) or _STANDARD.get(typ_slug)


def isoliert():
    """Für Tests: registrierte Texte werden danach zurückgesetzt."""
    from contextlib import contextmanager

    @contextmanager
    def kontext():
        stand = dict(_registriert)
        try:
            yield
        finally:
            _registriert.clear()
            _registriert.update(stand)

    return kontext()


def _felder(vorlage):
    return {name for _, name, _, _ in string.Formatter().parse(vorlage) if name}


def _fuellen(vorlage, werte):
    """Füllt Platzhalter; ``None`` wenn ein Wert fehlt."""
    if not _felder(vorlage) <= werte.keys():
        return None
    try:
        return vorlage.format_map(werte)
    except (KeyError, IndexError, ValueError, AttributeError):
        return None


def werte_aus(ereignis):
    werte = {k: v for k, v in (ereignis.daten or {}).items() if isinstance(v, str | int | float)}
    if ereignis.kind_id:
        werte["kind"] = ereignis.kind.anzeigename
    if ereignis.akteur_id:
        werte["akteur"] = ereignis.akteur.anzeigename
    return werte


def rendern(ereignis, typ_bezeichnung):
    """(titel, text) für ein Ereignis, auf die Spaltenlängen gekürzt."""
    werte = werte_aus(ereignis)
    vorlage = text_fuer(ereignis.typ_id)
    titel = text = None
    if vorlage is not None:
        titel = _fuellen(vorlage.titel, werte)
        text = _fuellen(vorlage.text, werte) if titel is not None else None
    if titel is None or text is None:
        titel = typ_bezeichnung
        rueckfall = werte.get("text")
        text = str(rueckfall) if rueckfall else (werte.get("kind") or "")
    return _kuerzen(titel, TITEL_MAX), _kuerzen(text, TEXT_MAX)


def link_fuer(ereignis, muster):
    """Deep-Link aus dem Muster des Ereignistyps (z. B. ``/eltern/meldung/{instanz}/``);
    fehlt ein Platzhalter, gibt es keinen Link."""
    if not muster:
        return ""
    werte = werte_aus(ereignis)
    if ereignis.kind_id:
        werte["kind_id"] = str(ereignis.kind_id)
    link = _fuellen(muster, werte)
    if not link or len(link) > LINK_MAX or not ist_interner_pfad(link):
        return ""
    return link


def ist_interner_pfad(link):
    """Nur Pfade der eigenen Origin: beginnt mit ``/``, aber nicht ``//`` oder ``/\\``
    (Browser behandeln beides als fremden Host). Kein Steuerzeichen (Review AP19, B-12)."""
    return (
        isinstance(link, str)
        and link.startswith("/")
        and not link.startswith(("//", "/\\"))
        and "\\" not in link
        and not any(ord(z) < 32 for z in link)
    )


def _kuerzen(text, grenze):
    text = str(text)
    return text if len(text) <= grenze else text[: grenze - 1] + "…"
