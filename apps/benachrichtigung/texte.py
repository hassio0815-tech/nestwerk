"""Texte der Benachrichtigungen je Ereignistyp (deutsch, Msgids) und Deep-Links.

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
from django.utils.translation import gettext, gettext_noop, ngettext

from apps.kern import sprache

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
        gettext_noop("Datensicherung fehlgeschlagen"),
        gettext_noop("Bitte Job-Läufe und Backup-Ordner prüfen (Runbook)."),
    ),
    "aufgabe.interesse": TypText(
        gettext_noop("{kind} möchte eine Aufgabe machen"), gettext_noop("„{aufgabe}“")
    ),
    "aufgabe.konflikt": TypText(
        gettext_noop("Mehrere möchten dieselbe Aufgabe"),
        gettext_noop("„{aufgabe}“ braucht eine Zuteilung."),
    ),
    "aufgabe.gemeldet": TypText(
        gettext_noop("{kind} hat eine Aufgabe gemeldet"),
        gettext_noop("„{aufgabe}“ wartet auf Bestätigung."),
    ),
    "aufgabe.bestaetigt": TypText(
        gettext_noop("Aufgabe bestätigt!"), gettext_noop("„{aufgabe}“ ist geschafft. Gut gemacht!")
    ),
    "aufgabe.abgelehnt": TypText(
        gettext_noop("Aufgabe nicht angenommen"), gettext_noop("„{aufgabe}“ wurde abgelehnt.")
    ),
    "aufgabe.rueckfrage": TypText(
        gettext_noop("Rückfrage zur Aufgabe"),
        gettext_noop("Zu „{aufgabe}“ gibt es eine Rückfrage."),
    ),
    "reservierung.erinnerung": TypText(
        gettext_noop("Deine Aufgabe wartet"), gettext_noop("„{aufgabe}“ läuft bald ab.")
    ),
    "reservierung.abgelaufen": TypText(
        gettext_noop("Reservierung abgelaufen"),
        gettext_noop("{kind} hat „{aufgabe}“ nicht gemacht."),
    ),
    "aufgabe.verfall_vorwarnung": TypText(
        gettext_noop("Aufgabe läuft bald ab"),
        gettext_noop("„{aufgabe}“ wurde noch nicht übernommen."),
    ),
    "aufgabe.nicht_uebernommen": TypText(
        gettext_noop("Aufgabe nicht übernommen"),
        gettext_noop("„{aufgabe}“ hat niemand übernommen."),
    ),
    "belohnung.antrag": TypText(
        gettext_noop("{kind} möchte eine Belohnung"),
        gettext_noop("„{belohnung}“ wartet auf Entscheidung."),
    ),
    "belohnung.entschieden": TypText(
        gettext_noop("Entscheidung zu deiner Belohnung"), gettext_noop("„{belohnung}“: {ergebnis}")
    ),
    "avatar.mod_fertig": TypText(
        gettext_noop("Dein Mod ist fertig!"), gettext_noop("„{mod}“ kann jetzt eingebaut werden.")
    ),
    "serie.gestiegen": TypText(
        gettext_noop("Serie: {wochenserie} Wochen!"),
        gettext_noop("Woche {woche} geschafft. Weiter so!"),
    ),
    "serie.gerissen": TypText(
        gettext_noop("Neue Woche, neue Serie"),
        gettext_noop(
            "Letzte Woche gab es keine Aufgabe. Schon eine Aufgabe startet deine Serie neu."
        ),
    ),
    "pause.gestartet": TypText(
        gettext_noop("Pause – deine Serie ist sicher"),
        gettext_noop("Pause {zeitraum}. Aufgaben zählen trotzdem."),
    ),
    "pause.beendet": TypText(gettext_noop("Pause vorbei"), gettext_noop("{hinweis}")),
    "serienbonus.gebucht": TypText(
        gettext_noop("Serienbonus +{prozent} %"),
        gettext_noop("+{punkte} Punkte für {serie} Wochen in Folge."),
    ),
    "rang.aufgestiegen": TypText(
        gettext_noop("Neuer Rang: {rang}!"), gettext_noop("{kind} ist aufgestiegen.")
    ),
    "abzeichen.verliehen": TypText(
        gettext_noop("Neues Abzeichen: {abzeichen}"), gettext_noop("{kind}: {beschreibung}")
    ),
    "spielregeln.rang_aufstieg": TypText(
        gettext_noop("Neuer Rang: {rang}!"), gettext_noop("{kind} ist aufgestiegen.")
    ),
    "spielregeln.abzeichen": TypText(
        gettext_noop("Neues Abzeichen: {abzeichen}"),
        gettext_noop("{kind} hat ein Abzeichen verdient."),
    ),
    "spielregeln.held": TypText(
        gettext_noop("{kind} ist Held der Woche"),
        # xgettext:no-python-format
        gettext_noop("{xp} Punkte, deutlich mehr als sonst ({prozent} % darüber)."),
    ),
    "spielregeln.held_kind": TypText(
        gettext_noop("Du bist Held der Woche!"),
        gettext_noop("{xp} Punkte: mehr als sonst. Stark gemacht!"),
    ),
    "sondertag.freigeschaltet": TypText(
        gettext_noop("Sondertag freigeschaltet"), gettext_noop("Du darfst dir etwas wünschen!")
    ),
    "sondertag.wunsch": TypText(
        gettext_noop("Sondertag-Wunsch von {kind}"), gettext_noop("{wunsch}")
    ),
    "sondertag.angenommen": TypText(
        gettext_noop("Dein Wunsch wurde angenommen"), gettext_noop("{wunsch}")
    ),
    "familienziel.erreicht": TypText(
        gettext_noop("{belohnung} freigeschaltet!"),
        gettext_noop("Die Familie hat {ziel} Punkte geschafft."),
    ),
    "familienziel.erreicht_kind": TypText(
        gettext_noop("Geschafft! {belohnung}"),
        gettext_noop("Ihr habt das Familienziel erreicht. Super gemacht!"),
    ),
    "familienziel.abstimmung_offen": TypText(
        gettext_noop("Abstimmung läuft"),
        gettext_noop("Wähle jetzt die Belohnung für nächste Woche."),
    ),
    "familienziel.abstimmung_gleichstand": TypText(
        gettext_noop("Familienziel: Eltern entscheiden"), gettext_noop("{hinweis}")
    ),
    "familienziel.grossziel": TypText(
        gettext_noop("Großes Ziel freigeschaltet: {grossziel}!"),
        gettext_noop("Mehrere Wochenziele in Folge geschafft."),
    ),
    "familienziel.grossziel_kind": TypText(
        gettext_noop("Großes Ziel: {grossziel}!"),
        gettext_noop("Ihr habt mehrere Wochenziele in Folge geschafft!"),
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
    """Platzhalter-Werte in der aktiven Sprache (docs/i18n.md, „Texte in Ereignissen“).

    - Texte sind gespeicherte deutsche Start-Inhalte (Mod-, Rang-, Abzeichen-Namen) und werden
      per msgid übersetzt; Unbekanntes (Eingaben der Familie) bleibt unverändert.
    - ``<feld>_msgid`` + optional ``<feld>_parameter`` (dict) bilden ``<feld>`` neu; mit
      ``<feld>_msgid_plural`` wird nach ``parameter["n"]`` die Mehrzahl gewählt.
    """
    daten = ereignis.daten or {}
    werte = {
        k: sprache.uebersetzt(v) if isinstance(v, str) else v
        for k, v in daten.items()
        if isinstance(v, str | int | float)
    }
    for schluessel, msgid in daten.items():
        if not schluessel.endswith("_msgid") or not msgid:
            continue
        feld = schluessel.removesuffix("_msgid")
        parameter = daten.get(f"{feld}_parameter")
        parameter = dict(parameter) if isinstance(parameter, dict) else {}
        if feld == "hinweis" and "titel" not in parameter:
            parameter["titel"] = daten.get("hinweis_titel", "")  # ältere Ereignisse (Gleichstand)
        parameter = {
            k: sprache.uebersetzt(v) if isinstance(v, str) else v for k, v in parameter.items()
        }
        plural = daten.get(f"{feld}_msgid_plural")
        try:
            if plural:
                werte[feld] = (
                    ngettext(str(msgid), str(plural), int(parameter.get("n", 0))) % parameter
                )
            else:
                werte[feld] = gettext(str(msgid)) % parameter
        except (KeyError, TypeError, ValueError):
            werte[feld] = gettext(str(msgid))
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
        # Vorlagen sind deutsche Msgids; übersetzt wird in der aktiven Sprache (Router:
        # Sprache des Empfängers). Fremde Module markieren ihre Texte mit gettext_noop.
        titel = _fuellen(gettext(str(vorlage.titel)), werte)
        text = (
            _fuellen(gettext(str(vorlage.text)) if vorlage.text else "", werte)
            if titel is not None
            else None
        )
    if titel is None or text is None:
        titel = gettext(typ_bezeichnung)
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
