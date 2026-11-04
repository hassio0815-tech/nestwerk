"""Optionale KI für die Mathe-Hilfe (SPEC 21.13, Etappe 10b): Einkleidung und "Erkläre es anders".

Immer Opt-in der Eltern, nie nötig, nie für Lösungen:

- **Einkleidung** (Einstellung ``lernen.mathe_einkleidung_ki``, Standard aus): Nur wenn sie an ist
  UND für die Aufgabe ``fragen_erzeugen`` ein aktiver Anbieter zugeordnet ist (bei Cloud mit
  Einwilligung), formuliert die KI aus der Rechnung eine Sachaufgabe. Das läuft in der
  Warteschlange, nie im Request. Zahlen und Lösung kommen vom Generator; die Ausgabe wird vor der
  Anzeige streng geprüft (``einkleidung_pruefen``), sonst bleibt die lokale Fassung. Kein stiller
  Fallback auf einen anderen Anbieter.
- **"Erkläre es anders"**: erklärt die Erklärkarte und das analoge Beispiel in anderen Worten
  (nur wenn der Tutor an ist), zählt in die Tutor-Limits und läuft durch die Leak-Prüfung des
  Tutors plus eine Prüfung gegen die Lösung der echten Aufgabe; sonst steht ein fester Hinweis da.

Grenzen (ehrlich): Die Prüfung ist eine Heuristik. Eine Sachaufgabe kann sprachlich schief sein,
auch wenn alle Zahlen stimmen; die Lösung bleibt aber immer die des Generators.
"""

import logging
import re

from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _

from apps.kern import zeit
from apps.kern.einstellungen import wert

from . import (
    ki_selectors,
    ki_services,
    ki_warteschlange,
    selectors,
    tutor_pruefung,
    tutor_selectors,
    tutor_services,
    tutor_texte,
)
from .ki import KiAusgabeFehler, KiFehler, KiNichtVerfuegbar
from .mathe import hilfe as mathe_hilfe
from .mathe import registry, textaufgaben
from .mathe.hilfe.bau import leckt, zahlen_in
from .mathe_prompts import (
    EINKLEIDUNG_VERSION,
    SCHEMA_EINKLEIDUNG,
    nachricht_einkleidung,
    nachricht_erklaerung,
    system_einkleidung,
    system_erklaerung,
)
from .models import (
    Frage,
    GespraechStatus,
    KiAufgabe,
    Lernsitzung,
    Markierung,
    NachrichtArt,
    NachrichtRolle,
    TutorGespraech,
    Versuch,
)

log = logging.getLogger("nestwerk.lernen.mathe_ki")

VERWEIS = "mathe:"
MIN_LAENGE, MAX_LAENGE = 25, 320
ERKLAERUNG_STUFE = (
    3  # Hilfestufe in Sitzung und Protokoll (unter der "hohen" Hilfe des Wochenbilds)
)

_HTML = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>|&lt;|&gt;|&#|javascript:|data:text", re.IGNORECASE)
_URL = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|www\.|\b[\w-]+\.(?:com|de|org|net|io|info|biz|xyz|ru|cn|tk)\b)",
    re.IGNORECASE,
)
_MAIL = re.compile(r"\S+@\S+\.\S+")
_TELEFON = re.compile(r"(?<!\d)\+?\d[\d /().-]{7,}\d(?!\d)")
_PERSOENLICH = re.compile(
    r"\b(?:wie\s+hei(?:ß|ss)t\s+du|dein(?:e|en|em)?\s+(?:name|adresse|telefon|schule|passwort|"
    r"e-?mail|handynummer)|wo\s+wohnst|geburtstag|passwort|kennwort|telefonnummer|handynummer|"
    r"e-?mail|adresse|what\s+is\s+your\s+name|your\s+(?:name|address|password|phone))\b",
    re.IGNORECASE,
)


# --- Einkleidung: Zugang -------------------------------------------------------------------------


def einkleidung_bereit():
    """Einstellung an UND aktiver Anbieter (mit Einwilligung bei Cloud) für ``fragen_erzeugen``."""
    return bool(wert("lernen.mathe_einkleidung_ki")) and ki_selectors.ki_verfuegbar(
        KiAufgabe.FRAGEN_ERZEUGEN
    )


def auftrag_schluessel(frage):
    return f"mathe-einkleidung:{frage.pk}"


def einreihen(frage, aufgabe):
    """Reiht die Einkleidung für eine neue Aufgabe in die Warteschlange ein (nicht im Request
    ausgeführt). Nichts passiert ohne Opt-in und Anbieter. Der Aufrufer (``mathe_aufgaben``)
    wählt vorher, welche Aufgaben als Textaufgabe kommen und eine Vorlage haben."""
    if not einkleidung_bereit() or not textaufgaben.hat_vorlage(aufgabe):
        return None
    verweis = f"{VERWEIS}{frage.pk}:{translation.get_language() or 'de'}"
    auftrag, _neu = ki_warteschlange.auftrag_einreihen(
        KiAufgabe.FRAGEN_ERZEUGEN, auftrag_schluessel(frage), eingabe_verweis=verweis
    )
    return auftrag


# --- Einkleidung: Prüfung der KI-Ausgabe ---------------------------------------------------------


def einkleidung_pruefen(text, aufgabe):
    """Prüft die Textfassung der KI und gibt den bereinigten Text zurück, sonst ``KiAusgabeFehler``.

    Alle Zahlen der Aufgabe kommen vor, keine anderen Zahlen (auch keine Zahlwörter), Länge,
    kein HTML, keine Links, Adressen, Telefonnummern, keine Frage nach persönlichen Daten, mit
    Fragezeichen, und die Lösung der Aufgabe steht nicht darin."""
    text = " ".join(str(text or "").split())
    if not MIN_LAENGE <= len(text) <= MAX_LAENGE:
        raise KiAusgabeFehler()
    if _HTML.search(text) or _URL.search(text) or _MAIL.search(text) or _TELEFON.search(text):
        raise KiAusgabeFehler()
    if _PERSOENLICH.search(text) or "?" not in text:
        raise KiAusgabeFehler()
    erlaubt = zahlen_in(aufgabe.text)
    vorhanden = zahlen_in(text)
    if not erlaubt <= vorhanden or vorhanden - erlaubt:
        raise KiAusgabeFehler()
    if leckt(text, aufgabe):
        raise KiAusgabeFehler()
    return text


# --- Einkleidung: Handler (Warteschlange) -------------------------------------------------------


def _frage_zum_auftrag(auftrag):
    verweis = auftrag.eingabe_verweis
    if not verweis.startswith(VERWEIS):
        return None, "de"
    rest = verweis[len(VERWEIS) :].split(":")
    if not rest[0].isdigit():
        return None, "de"
    frage = Frage.objects.filter(pk=int(rest[0]), generiert=True).first()
    if frage is None or auftrag.schluessel != auftrag_schluessel(frage):
        return None, "de"
    return frage, (rest[1] if len(rest) > 1 else "de")


def einkleidung_handler(auftrag):
    """Handler für Aufträge ``mathe:<frage>:<sprache>`` (Aufgabe ``fragen_erzeugen``)."""
    frage, sprache = _frage_zum_auftrag(auftrag)
    if frage is None or not wert("lernen.mathe_einkleidung_ki"):
        return  # veraltet oder inzwischen abgeschaltet: nichts tun (und nichts senden)
    aufgabe = _urspruengliche_aufgabe(frage)
    if aufgabe is None or not textaufgaben.hat_vorlage(aufgabe):
        return
    if (frage.gen_daten.get("einkleidung") or {}).get("quelle") == "ki":
        return
    from .texte import stufe_fuer

    antwort = ki_services.ki_aufruf(
        KiAufgabe.FRAGEN_ERZEUGEN,
        system=system_einkleidung(stufe_fuer(aufgabe.klassenstufe)),
        nachricht=nachricht_einkleidung(_rechnung(aufgabe)),
        json_ausgabe=True,
        schema=SCHEMA_EINKLEIDUNG,
        max_tokens=400,
    )
    daten = antwort.json
    text = daten.get("text") if isinstance(daten, dict) else None
    ok = einkleidung_pruefen(text, aufgabe)  # KiAusgabeFehler: Auftrag schlägt fehl, Text bleibt
    _uebernehmen(frage, aufgabe, ok)
    log.info("mathe_einkleidung frage=%s sprache=%s ok", frage.pk, sprache)


def _urspruengliche_aufgabe(frage):
    """Die Aufgabe mit dem reinen Rechentext des Generators (die Frage zeigt evtl. schon die lokale
    Textfassung). Aus Generator, Stufe und Seed neu erzeugt, also immer dieselben Zahlen."""
    daten = frage.gen_daten or {}
    try:
        return registry.erzeugen(
            daten["generator"],
            daten["schwierigkeit"],
            daten["seed"],
            registry.Kontext((daten.get("parameter") or {}).get("grenze")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _rechnung(aufgabe):
    """Nur die Rechnung (Zahlen und Rechenzeichen, ggf. Aufgabentext), nie die Lösung."""
    return aufgabe.text


def _uebernehmen(frage, aufgabe, text):
    """Speichert die geprüfte Fassung an der Aufgabe. Der Text ersetzt die Anzeige nur, solange
    niemand die Aufgabe beantwortet hat oder gerade bearbeitet."""
    daten = dict(frage.gen_daten)
    daten["einkleidung"] = {"quelle": "ki", "text": text, "version": EINKLEIDUNG_VERSION}
    frage.gen_daten = daten
    felder = ["gen_daten"]
    offen = Lernsitzung.objects.filter(aktuell_frage=frage).exists()
    if not offen and not Versuch.objects.filter(frage=frage).exists():
        frage.frage = text[:300]
        felder.append("frage")
    frage.save(update_fields=felder)


# --- "Erkläre es anders" ------------------------------------------------------------------------


def erklaerung_bereit():
    """Tutor an und ein aktiver Anbieter für ``tutor`` zugeordnet."""
    return tutor_selectors.status() is tutor_selectors.TutorStatus.BEREIT


def _limit_pruefen(kind, fach, jetzt):
    if tutor_selectors.kind_nachrichten_heute(kind, jetzt=jetzt) >= wert(
        "lernen.tutor_nachrichten_pro_tag"
    ):
        raise tutor_services.TutorFehler("limit", tutor_services._ton("limit_tag", kind, fach))


def _kontext(aufgabe, sprachstufe):
    """Karte und analoges Beispiel der Aufgabe als Text; nie die echte Aufgabe oder ihre Lösung."""
    karte = mathe_hilfe.karte_fuer(aufgabe.generator)
    beispiel = mathe_hilfe.stufe_text(aufgabe, 3, sprachstufe)
    if karte is None or beispiel.beispiel is None:
        return None
    text = mathe_hilfe.karte_text(karte, sprachstufe)
    return text, [*beispiel.absaetze[1:], *beispiel.zeilen]


def erklaerung_anders(sitzung, *, jetzt=None):
    """Das Kind bittet bei einer Mathe-Aufgabe um eine andere Erklärung. Gibt den Text zurück.

    Fehler als ``TutorFehler`` (Tutor aus, Limit, keine KI). Die Antwort wird gespeichert (Eltern
    sehen sie im Tutor-Protokoll) und zählt zu den Nachrichten des Tages."""
    tutor_services._pruefen_zugang()
    jetzt = jetzt or zeit.jetzt()
    if sitzung.aktuell_frage_id is None:
        raise tutor_services.TutorFehler("nichts", _("Es ist keine Aufgabe offen."))
    frage = sitzung.aktuell_frage
    aufgabe = mathe_hilfe.aufgabe_aus_frage(frage)
    if aufgabe is None:
        raise tutor_services.TutorFehler("nichts", _("Dazu gibt es keine Erklärkarte."))
    kind, fach = sitzung.kind, sitzung.fach
    _limit_pruefen(kind, fach, jetzt)
    sprachstufe = selectors.sprachstufe(kind, fach)
    kontext = _kontext(aufgabe, sprachstufe)
    if kontext is None:
        raise tutor_services.TutorFehler("nichts", _("Dazu gibt es keine Erklärkarte."))
    karte, zeilen = kontext
    text, markierung = _ki_text(aufgabe, karte, zeilen, kind, sprachstufe)
    with transaction.atomic():
        g = TutorGespraech.objects.create(
            kind=kind,
            thema=frage.thema,
            status=GespraechStatus.BEENDET,
            hilfestufe=ERKLAERUNG_STUFE,
            beginn=jetzt,
            ende=jetzt,
            letzte_aktivitaet=jetzt,
        )
        tutor_services._speichern(
            g,
            NachrichtRolle.KIND,
            NachrichtArt.MEHR_HILFE,
            _("Erkläre es anders."),
            stufe=ERKLAERUNG_STUFE,
            jetzt=jetzt,
        )
        tutor_services._speichern(
            g,
            NachrichtRolle.TUTOR,
            NachrichtArt.ANTWORT,
            text,
            stufe=ERKLAERUNG_STUFE,
            jetzt=jetzt,
            markierung=markierung,
        )
        if sitzung.hilfestufe_max < ERKLAERUNG_STUFE:
            sitzung.hilfestufe_max = ERKLAERUNG_STUFE
            sitzung.save(update_fields=["hilfestufe_max"])
    return text


def _ki_text(aufgabe, karte, zeilen, kind, sprachstufe):
    """``(text, markierung)``: geprüfte Erklärung oder fester Hinweis (Markierung ``leck``)."""
    laenge = wert("lernen.tutor_laenge_antwort")
    nachricht = nachricht_erklaerung(
        titel=karte.titel,
        merksatz=karte.merksatz,
        karten_beispiel=karte.beispiel,
        beispiel_zeilen=zeilen,
    )
    system = system_erklaerung(sprachstufe)
    try:
        antwort = ki_services.ki_aufruf(
            KiAufgabe.TUTOR,
            system=system,
            nachricht=nachricht,
            max_tokens=max(64, laenge // 2),
            kind=kind,
        )
    except KiNichtVerfuegbar:
        raise tutor_services.TutorFehler(
            "keine_ki", _("Der Tutor ist noch nicht eingerichtet.")
        ) from None
    except KiFehler:
        raise tutor_services.TutorFehler("ki", tutor_texte.ton("ki_fehler", sprachstufe)) from None
    text = tutor_pruefung.antwort_kuerzen(antwort.text, laenge)
    if erklaerung_verdaechtig(text, aufgabe):
        return tutor_texte.ton("zurueckgehalten", sprachstufe), Markierung.LECK
    return text, ""


def erklaerung_verdaechtig(text, aufgabe):
    """Verrät die Erklärung die Lösung der echten Aufgabe? Leak-Prüfung des Tutors (ein Beispiel
    mit anderen Zahlen ist erlaubt) und zusätzlich die Prüfung gegen die Lösung der Aufgabe."""
    grund = tutor_pruefung.leck_verdacht(
        text, stufe=3, aufgabe_text=aufgabe.text, bekannte=(), eigene_texte=""
    )
    return bool(grund) or leckt(text, aufgabe)
