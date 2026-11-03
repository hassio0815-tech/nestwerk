"""KI-Anbieter, Zuordnung und Aufruf (SPEC 21.6, Etappe 3).

- Standard: nichts konfiguriert, KI ist aus. Eine Aufgabe ohne Zuordnung nutzt keine KI.
- Cloud-Anbieter (Anthropic, OpenAI, jede nicht lokale Adresse) brauchen vor der Aktivierung die
  ausdrückliche Einwilligung der Eltern (Zeitpunkt und Person werden gespeichert).
- **Kein stiller Fallback** auf einen anderen Anbieter (Fallback kommt später, nur mit Erlaubnis).
- Der API-Schlüssel wird verschlüsselt gespeichert und nie angezeigt, geloggt oder protokolliert;
  Audit und Log enthalten nur Metadaten (Aufgabe, Anbieter, Dauer, Erfolg, Token-Zahl).
"""

import logging
import time
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.benachrichtigung import crypto
from apps.kern import audit
from apps.kern.einstellungen import wert

from . import ki, ki_selectors
from .ki import (
    KiAnfrage,
    KiEinwilligungFehlt,
    KiFehler,
    KiKonfigurationsFehler,
    KiNichtVerfuegbar,
    transport,
)
from .models import KiAnbieter, KiAufgabe, KiTyp, KiZuordnung

log = logging.getLogger("nestwerk.lernen.ki")

# Typen, die ohne Schlüssel nicht funktionieren
_SCHLUESSEL_PFLICHT = {KiTyp.ANTHROPIC, KiTyp.OPENAI}
_TEST_NACHRICHT = "Reply with the single word: OK"


@dataclass(frozen=True)
class TestErgebnis:
    ok: bool
    art: str  # Fehlercode, leer bei Erfolg
    dauer_ms: int


# --- Anbieter -------------------------------------------------------------------------------------


def anbieter_speichern(
    *, anbieter=None, name, typ, basis_url="", modell, api_key="", akteur=audit.AKTUELL
):
    """Legt einen Anbieter an (immer inaktiv) oder ändert ihn. Leerer ``api_key`` behält den
    gespeicherten Schlüssel. Ändert sich Typ oder Adresse, erlischt die Einwilligung und ein
    Cloud-Anbieter wird deaktiviert (die Eltern entscheiden neu)."""
    name, modell, basis_url = (
        (name or "").strip(),
        (modell or "").strip(),
        (basis_url or "").strip(),
    )
    api_key = (api_key or "").strip()
    if typ not in KiTyp.values:
        raise ValidationError(_("Unbekannter Anbieter-Typ."))
    if not name:
        raise ValidationError(_("Bitte einen Namen eintragen."))
    if not modell:
        raise ValidationError(_("Bitte den Modellnamen eintragen."))
    if typ == KiTyp.OPENAI_KOMPATIBEL and not basis_url:
        raise ValidationError(_("Bitte die Adresse des KI-Servers eintragen."))
    if basis_url:
        try:
            basis_url = transport.url_pruefen(basis_url)
        except KiKonfigurationsFehler:
            raise ValidationError(
                _("Die Adresse ist ungültig (http:// oder https://, ohne Benutzer und Passwort).")
            ) from None
    vorhandener_schluessel = anbieter.schluessel_verschluesselt if anbieter else ""
    if typ in _SCHLUESSEL_PFLICHT and not (api_key or vorhandener_schluessel):
        raise ValidationError(_("Für diesen Anbieter ist ein API-Schlüssel nötig."))
    if KiAnbieter.objects.exclude(pk=getattr(anbieter, "pk", None)).filter(name=name).exists():
        raise ValidationError(_("Diesen Namen gibt es schon."))

    cloud = ki.ist_cloud(typ, basis_url)
    with transaction.atomic():
        neu = anbieter is None
        if neu:
            anbieter = KiAnbieter()
        ziel_geaendert = not neu and (anbieter.typ, anbieter.basis_url) != (typ, basis_url)
        anbieter.name, anbieter.typ, anbieter.basis_url, anbieter.modell = (
            name,
            typ,
            basis_url,
            modell,
        )
        anbieter.ist_cloud = cloud
        if api_key:
            anbieter.schluessel_verschluesselt = crypto.verschluesseln(api_key)
        if ziel_geaendert:
            anbieter.einwilligung_am = None
            anbieter.einwilligung_von = None
            if cloud:
                anbieter.aktiv = False
        # eine Änderung der Zugangsdaten macht den letzten Test ungültig
        anbieter.letzter_test_am = None
        anbieter.letzter_test_ok = None
        anbieter.save()
        audit.protokollieren(
            "lernen.ki_anbieter_angelegt" if neu else "lernen.ki_anbieter_geaendert",
            akteur=akteur,
            objekt=anbieter,
            details={
                "name": name,
                "typ": typ,
                "cloud": cloud,
                "modell": modell,
                "schluessel_gesetzt": anbieter.hat_schluessel,
                "schluessel_neu": bool(api_key),
                "einwilligung_zurueckgesetzt": ziel_geaendert,
            },
        )
    return anbieter


def anbieter_aktivieren(anbieter, *, einwilligung=False, akteur=audit.AKTUELL):
    """Schaltet einen Anbieter ein. Cloud: nur mit Einwilligung (jetzt gegeben oder früher
    gespeichert), sonst ``KiEinwilligungFehlt``."""
    if anbieter.ist_cloud and anbieter.einwilligung_am is None and not einwilligung:
        raise KiEinwilligungFehlt()
    with transaction.atomic():
        if anbieter.ist_cloud and anbieter.einwilligung_am is None:
            anbieter.einwilligung_am = timezone.now()
            anbieter.einwilligung_von = _eltern_person(akteur)
            audit.protokollieren(
                "lernen.ki_einwilligung",
                akteur=akteur,
                objekt=anbieter,
                details={"name": anbieter.name, "typ": anbieter.typ},
            )
        anbieter.aktiv = True
        anbieter.save(update_fields=["aktiv", "einwilligung_am", "einwilligung_von"])
        audit.protokollieren(
            "lernen.ki_anbieter_aktiviert",
            akteur=akteur,
            objekt=anbieter,
            details={"name": anbieter.name, "cloud": anbieter.ist_cloud},
        )
    return anbieter


def anbieter_deaktivieren(anbieter, *, akteur=audit.AKTUELL):
    with transaction.atomic():
        anbieter.aktiv = False
        anbieter.save(update_fields=["aktiv"])
        audit.protokollieren(
            "lernen.ki_anbieter_deaktiviert",
            akteur=akteur,
            objekt=anbieter,
            details={"name": anbieter.name},
        )
    return anbieter


def _eltern_person(akteur):
    if akteur is audit.AKTUELL:
        akteur = audit.aktueller_akteur()
    return akteur if getattr(akteur, "pk", None) else None


# --- Zuordnung ------------------------------------------------------------------------------------


def zuordnung_setzen(aufgabe, anbieter, *, akteur=audit.AKTUELL):
    """Ordnet eine Aufgabe einem Anbieter zu; ``anbieter=None`` schaltet die KI für die Aufgabe
    aus. Familienweit, nicht pro Kind."""
    if aufgabe not in KiAufgabe.values:
        raise ValidationError(_("Unbekannte Aufgabe."))
    with transaction.atomic():
        if anbieter is None:
            KiZuordnung.objects.filter(aufgabe=aufgabe).delete()
        else:
            KiZuordnung.objects.update_or_create(aufgabe=aufgabe, defaults={"anbieter": anbieter})
        audit.protokollieren(
            "lernen.ki_zuordnung_gesetzt",
            akteur=akteur,
            objekt_typ="lernen.kizuordnung",
            objekt_id=aufgabe,
            details={"aufgabe": aufgabe, "anbieter": anbieter.name if anbieter else ""},
        )


# --- Aufruf ---------------------------------------------------------------------------------------


def _adapter_bauen(anbieter):
    try:
        schluessel = (
            crypto.entschluesseln(anbieter.schluessel_verschluesselt)
            if anbieter.schluessel_verschluesselt
            else ""
        )
    except crypto.SchluesselFehler:
        raise KiKonfigurationsFehler() from None
    return ki.adapter_erzeugen(
        anbieter.typ, basis_url=anbieter.basis_url, modell=anbieter.modell, api_key=schluessel
    )


def _ausfuehren(anbieter, anfrage, *, aufgabe, kind=None):
    """Ruft den Adapter und protokolliert Metadaten (nie Inhalte oder Schlüssel)."""
    start = time.monotonic()
    antwort, fehler_art = None, ""
    try:
        antwort = _adapter_bauen(anbieter).chat(anfrage)
        return antwort
    except KiFehler as exc:
        fehler_art = exc.art
        raise
    except Exception:
        fehler_art = "intern"
        raise
    finally:
        dauer_ms = int((time.monotonic() - start) * 1000)
        _protokollieren(anbieter, aufgabe, dauer_ms, antwort, fehler_art, kind)


def _protokollieren(anbieter, aufgabe, dauer_ms, antwort, fehler_art, kind):
    details = {
        "aufgabe": aufgabe,
        "anbieter": anbieter.pk,
        "typ": anbieter.typ,
        "cloud": anbieter.ist_cloud,
        "dauer_ms": dauer_ms,
        "erfolg": not fehler_art,
    }
    if antwort is not None:
        details["tokens_ein"] = antwort.tokens_ein
        details["tokens_aus"] = antwort.tokens_aus
    if fehler_art:
        details["fehler"] = fehler_art
    log.info("ki_aufruf %s", details)
    audit.protokollieren(
        "lernen.ki_aufruf", akteur=None, kind=kind, objekt=anbieter, details=details
    )


def ki_aufruf(
    aufgabe,
    *,
    system="",
    nachricht,
    bilder=(),
    json_ausgabe=False,
    schema=None,
    max_tokens=1024,
    timeout=None,
    kind=None,
):
    """Führt eine KI-Aufgabe über den zugeordneten Anbieter aus und gibt die ``KiAntwort``
    zurück. Keine Zuordnung, inaktiver Anbieter oder fehlende Cloud-Einwilligung:
    ``KiNichtVerfuegbar`` (KI aus). Fehler des Anbieters werden weitergereicht; es gibt keinen
    Fallback auf einen anderen Anbieter."""
    if aufgabe not in KiAufgabe.values:
        raise ValueError(f"Unbekannte KI-Aufgabe '{aufgabe}'")
    anbieter = ki_selectors.zuordnung_fuer(aufgabe)
    status = ki_selectors.status_von(anbieter)
    if status is ki_selectors.KiStatus.EINWILLIGUNG_FEHLT:
        raise KiEinwilligungFehlt()
    if status is not ki_selectors.KiStatus.BEREIT:
        raise KiNichtVerfuegbar()
    anfrage = KiAnfrage(
        system=system,
        nachricht=nachricht,
        bilder=tuple(bilder),
        json_ausgabe=json_ausgabe,
        schema=schema,
        max_tokens=max_tokens,
        timeout=timeout or wert("lernen.ki_timeout_sekunden"),
    )
    return _ausfuehren(anbieter, anfrage, aufgabe=aufgabe, kind=kind)


def verbindung_testen(anbieter):
    """Harmloser Testaufruf ("antworte mit OK"); es werden keine Kinderdaten gesendet. Das
    Ergebnis enthält nur Erfolg, Fehlercode und Dauer."""
    anfrage = KiAnfrage(
        system="",
        nachricht=_TEST_NACHRICHT,
        max_tokens=64,
        timeout=wert("lernen.ki_timeout_sekunden"),
    )
    start = time.monotonic()
    art = ""
    try:
        _ausfuehren(anbieter, anfrage, aufgabe="test")
    except KiFehler as exc:
        art = exc.art
    except Exception:  # pragma: no cover - Absicherung, der Test soll die Seite nie sprengen
        art = "intern"
    ergebnis = TestErgebnis(not art, art, int((time.monotonic() - start) * 1000))
    anbieter.letzter_test_am = timezone.now()
    anbieter.letzter_test_ok = ergebnis.ok
    anbieter.save(update_fields=["letzter_test_am", "letzter_test_ok"])
    return ergebnis
