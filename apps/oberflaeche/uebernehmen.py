"""Aufgabe aus der Wochenvorschau übernehmen: Absicht merken, nach der Anmeldung einlösen.

Ablauf: Popup der Anmeldeseite -> ``vormerken`` (Sitzungs-Schlüssel, nur ganze Zahl + ISO-Datum,
gegen die Wochenvorschau geprüft) -> die normale Kind-Anmeldung (PIN) -> ``user_logged_in``
löst die Absicht ein (``aufgaben`` wählt über ``interesse_zeigen``) und legt das Ergebnis als
einmalige Meldung für die Kinder-Startseite ab. Eltern verwerfen die Absicht nur. Jede Anmeldung
verbraucht die Absicht; sie verfällt außerdem nach ``GUELTIG_SEKUNDEN``.
"""

import logging
from datetime import date

from apps.aufgaben import selectors as aufgaben_selectors
from apps.aufgaben import services as aufgaben_services
from apps.kern import zeit
from apps.konten.models import Rolle

logger = logging.getLogger(__name__)

SCHLUESSEL = "nach_login_uebernehmen"
HINWEIS = "kind_hinweis"
GUELTIG_SEKUNDEN = 600


def vormerken(request, aufgabe_id, datum) -> bool:
    """Merkt die Absicht, wenn die Aufgabe laut Wochenvorschau an dem Tag ansteht."""
    verwerfen(request)
    aufgabe_id, datum = _pruefen(aufgabe_id, datum)
    if aufgabe_id is None or aufgaben_selectors.start_woche_aufgabe(aufgabe_id, datum) is None:
        return False
    request.session[SCHLUESSEL] = {
        "a": aufgabe_id,
        "d": datum.isoformat(),
        "t": zeit.jetzt().timestamp(),
    }
    return True


def verwerfen(request) -> None:
    request.session.pop(SCHLUESSEL, None)


def gemerkt(request):
    """``(aufgabe_id, datum)`` der gültigen Absicht oder ``None`` (Ungültiges wird gelöscht)."""
    roh = request.session.get(SCHLUESSEL)
    absicht = _lesen(roh)
    if absicht is None:
        if roh is not None:
            verwerfen(request)
        return None
    return absicht


def _lesen(roh):
    try:
        alt = zeit.jetzt().timestamp() - float(roh["t"])
        if not 0 <= alt <= GUELTIG_SEKUNDEN:
            return None
        aufgabe_id, datum = _pruefen(roh["a"], roh["d"])
    except (KeyError, TypeError, ValueError):
        return None
    return None if aufgabe_id is None else (aufgabe_id, datum)


def _pruefen(aufgabe_id, datum):
    """Ganzzahl-ID (positiv, ASCII-Ziffern) und ISO-Datum ``JJJJ-MM-TT`` oder ``(None, None)``."""
    text = str(aufgabe_id)
    if isinstance(aufgabe_id, bool) or not (text.isascii() and text.isdigit()) or int(text) <= 0:
        return None, None
    datum = str(datum)
    try:
        tag = date.fromisoformat(datum) if len(datum) == 10 else None
    except ValueError:
        tag = None
    return (int(text), tag) if tag else (None, None)


def nach_anmeldung(sender, request, user, **kwargs):
    """``user_logged_in``: Absicht verbrauchen; Kinder übernehmen, alle anderen verwerfen sie."""
    session = getattr(request, "session", None)
    if session is None:
        return
    roh = session.pop(SCHLUESSEL, None)
    if roh is None or getattr(user, "rolle", None) != Rolle.KIND:
        return
    absicht = _lesen(roh)
    if absicht is None:
        return
    try:
        ergebnis = aufgaben_services.aus_woche_uebernehmen(user, *absicht)
    except Exception:  # die Anmeldung darf nie an der Übernahme scheitern
        logger.exception("Übernahme aus der Wochenvorschau fehlgeschlagen")
        return
    session[HINWEIS] = {"text": ergebnis.text, "art": ergebnis.art}


def hinweis_entnehmen(request):
    """Die einmalige Meldung für die Kinder-Startseite als ``(text, art)`` oder ``("", "")``."""
    eintrag = request.session.pop(HINWEIS, None)
    if not isinstance(eintrag, dict):
        return "", ""
    return str(eintrag.get("text", "")), str(eintrag.get("art", "info"))
