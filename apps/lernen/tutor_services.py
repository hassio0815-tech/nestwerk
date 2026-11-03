"""Der Tutor mit Hilfeleiter (SPEC 21.3, 21.4).

Ablauf einer Nachricht des Kindes:

1. Zugang: Einstellung ``lernen.tutor_aktiv`` und ein aktiver Anbieter für die Aufgabe ``tutor``.
2. Grenzen: Länge der Nachricht, Nachrichten pro Tag.
3. Vorprüfung ohne KI: Rollenwechsel-Versuch und Lösungsbitte bekommen einen festen, freundlichen
   Text (Lösungsbitte: zurück auf Hilfestufe 1).
4. KI-Aufruf mit Kontext aus Daten (kein Text des Kindes im System-Prompt, keine Musterlösung).
5. Leak-Prüfung der Antwort; bei Verdacht einmal neu mit schärferer Anweisung, sonst fester Text.
6. Speichern. Die Hilfestufe steigt nur durch ``mehr_hilfe`` (Wunsch des Kindes).

Hilfen kosten keine Punkte und werden nie bestraft. Die genutzte Stufe wird als Maximum in die
offene Lernsitzung geschrieben (``Lernsitzung.hilfestufe_max``).
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils.translation import gettext as _

from apps.kern import audit, einstellungen, zeit
from apps.kern.einstellungen import wert

from . import ki_services, selectors, tutor_prompts, tutor_pruefung, tutor_selectors, tutor_texte
from .ki import KiFehler, KiNichtVerfuegbar
from .models import (
    GespraechStatus,
    KiAufgabe,
    Markierung,
    NachrichtArt,
    NachrichtRolle,
    TutorGespraech,
    TutorNachricht,
)

log = logging.getLogger("nestwerk.lernen.tutor")

HILFESTUFE_MAX = 5
VERLAUF_NACHRICHTEN = 12
MATERIAL_ZEICHEN = 4000
AUFGABE_FAKTOR = 3  # Aufgabentext darf so viel länger sein wie eine Nachricht


class TutorFehler(Exception):
    """Freundlich formulierter Fehler für das Kind. ``code`` ist stabil (für Tests und Seiten)."""

    def __init__(self, code, text):
        self.code = code
        super().__init__(text)


# --- Hilfen -------------------------------------------------------------------------------------


def _ton(schluessel, kind, fach=None):
    return tutor_texte.ton(schluessel, selectors.sprachstufe(kind, fach))


def _fach_von(g):
    if g.material_id and g.material.fach_id:
        return g.material.fach
    if g.thema_id:
        return g.thema.fach
    return None


def _pruefen_zugang(*, bewerten=False):
    status = tutor_selectors.status()
    if status is tutor_selectors.TutorStatus.AUS:
        raise TutorFehler("aus", _("Der Tutor ist gerade nicht eingeschaltet."))
    if status is not tutor_selectors.TutorStatus.BEREIT:
        raise TutorFehler("keine_ki", _("Der Tutor ist noch nicht eingerichtet."))
    if bewerten and not tutor_selectors.bewerten_bereit():
        raise TutorFehler("keine_ki", _("Das Prüfen von Versuchen ist noch nicht eingerichtet."))


def _pruefen_gespraech(g):
    if g.status != GespraechStatus.OFFEN:
        raise TutorFehler("beendet", _("Dieses Gespräch ist beendet."))


def _pruefen_limit(g, jetzt):
    """Nachrichten pro Tag; Überschreitung ist keine Strafe, nur eine Pause."""
    if tutor_selectors.kind_nachrichten_heute(g.kind, jetzt=jetzt) >= wert(
        "lernen.tutor_nachrichten_pro_tag"
    ):
        raise TutorFehler("limit", _ton("limit_tag", g.kind, _fach_von(g)))


def _text_pruefen(text, *, faktor=1):
    text = " ".join(str(text or "").split())
    if not text:
        raise TutorFehler("leer", _("Schreib bitte zuerst etwas."))
    maximum = wert("lernen.tutor_laenge_nachricht") * faktor
    if len(text) > maximum:
        raise TutorFehler(
            "zu_lang",
            _("Das ist ein bisschen lang. Schreib bitte höchstens %(n)s Zeichen.") % {"n": maximum},
        )
    return text


def _speichern(g, rolle, art, text, *, stufe, jetzt, **felder):
    return TutorNachricht.objects.create(
        gespraech=g, rolle=rolle, art=art, text=text, hilfestufe=stufe, zeit=jetzt, **felder
    )


def _sitzung_buchen(g, stufe):
    """Höchste genutzte Hilfestufe in die offene Lernsitzung schreiben (kein Punkte-Effekt)."""
    sitzung = selectors.offene_sitzung(g.kind)
    if sitzung is not None and sitzung.hilfestufe_max < stufe:
        sitzung.hilfestufe_max = stufe
        sitzung.save(update_fields=["hilfestufe_max"])


def _kontext_material(g):
    if g.material_id and g.material.text:
        return g.material.text[:MATERIAL_ZEICHEN]
    return None


def _aufgabe_text(g, aktuell=""):
    """Zahlen und Wörter der Aufgabe für die Leak-Prüfung: Nachrichten des Kindes und Material."""
    teile = tutor_selectors.kind_texte(g) + [aktuell]
    if g.material_id and g.material.text:
        teile.append(g.material.text)
    return "\n".join(t for t in teile if t)


# --- Gespräch -----------------------------------------------------------------------------------


def gespraech_starten(kind, *, material=None, thema=None, jetzt=None):
    """Neues Gespräch (Material oder Thema optional). Material muss dem Kind gehören."""
    _pruefen_zugang()
    if material is not None and material.kind_id != kind.pk:
        raise TutorFehler("fremd", _("Dieses Material gehört nicht in deine Mappe."))
    jetzt = jetzt or zeit.jetzt()
    if tutor_selectors.offene_gespraeche(kind).count() >= wert(
        "lernen.tutor_gespraeche_gleichzeitig"
    ):
        raise TutorFehler(
            "zu_viele",
            _("Du hast schon mehrere offene Gespräche. Beende zuerst eines, dann geht es weiter."),
        )
    with transaction.atomic():
        g = TutorGespraech.objects.create(
            kind=kind, material=material, thema=thema, beginn=jetzt, letzte_aktivitaet=jetzt
        )
        g = tutor_selectors.gespraech(kind, g.pk)
        _speichern(
            g,
            NachrichtRolle.TUTOR,
            NachrichtArt.HINWEIS,
            _ton("begruessung", kind, _fach_von(g)),
            stufe=1,
            jetzt=jetzt,
        )
    return g


def gespraech_beenden(g, *, jetzt=None):
    if g.status == GespraechStatus.OFFEN:
        g.status = GespraechStatus.BEENDET
        g.ende = jetzt or zeit.jetzt()
        g.save(update_fields=["status", "ende"])
    return g


def gespraech_loeschen(g, *, akteur=audit.AKTUELL):
    """Löscht Gespräch und Nachrichten (Eltern). Im Audit steht nur, wer wessen Gespräch löschte."""
    with transaction.atomic():
        audit.protokollieren(
            "lernen.tutor_gespraech_geloescht",
            akteur=akteur,
            kind=g.kind,
            objekt_typ="lernen.tutorgespraech",
            objekt_id=str(g.pk),
            details={"nachrichten": g.nachrichten.count()},
        )
        g.delete()


def aufraeumen(*, jetzt=None):
    """Löscht Gespräche ohne Aktivität seit ``lernen.tutor_aufbewahrung_tage`` Tagen."""
    grenze = (jetzt or zeit.jetzt()) - timedelta(days=wert("lernen.tutor_aufbewahrung_tage"))
    _summe, je_modell = TutorGespraech.objects.filter(letzte_aktivitaet__lt=grenze).delete()
    return {
        "gespraeche": je_modell.get("lernen.TutorGespraech", 0),
        "nachrichten": je_modell.get("lernen.TutorNachricht", 0),
    }


def tutor_umschalten(an, *, akteur=audit.AKTUELL):
    """Tutor für die ganze Familie ein- oder ausschalten (nicht pro Kind)."""
    einstellungen.setzen("lernen.tutor_aktiv", bool(an), akteur=akteur)


# --- Antwort der KI -----------------------------------------------------------------------------


def _verlauf(g):
    return [
        (n.rolle, n.text or _("(bittet um mehr Hilfe)"))
        for n in tutor_selectors.letzte_nachrichten(g, VERLAUF_NACHRICHTEN)
    ]


def _ki_antwort(g, aktuell, stufe, *, aufgabe_text):
    """Antwort des Tutors: ``(text, markierung)``. Prüft auf Leaks, fragt einmal schärfer nach und
    fällt sonst auf den festen Text zurück. KI-Fehler werden zu ``TutorFehler``."""
    kind = g.kind
    fach = _fach_von(g)
    sprachstufe = selectors.sprachstufe(kind, fach)
    vergleich = bool(wert("lernen.tutor_vergleich_nach_versuch"))
    laenge = wert("lernen.tutor_laenge_antwort")
    bekannte = tutor_selectors.bekannte_antworten(g, tutor_selectors.kind_texte(g) + [aktuell])
    eigene = "\n".join(tutor_selectors.kind_texte(g) + [aktuell]) if vergleich else ""
    nachricht = tutor_prompts.nachricht_tutor(
        faecher=[f.name for f in selectors.faecher()],
        fach=fach.name if fach else "",
        thema=g.thema.name if g.thema_id else (g.material.thema_name if g.material_id else ""),
        material_text=_kontext_material(g),
        verlauf=_verlauf(g),
        aktuell=aktuell,
        stufe=stufe,
    )
    for streng in (False, True):
        system = tutor_prompts.system_tutor(stufe, sprachstufe, vergleich=vergleich, streng=streng)
        try:
            antwort = ki_services.ki_aufruf(
                KiAufgabe.TUTOR,
                system=system,
                nachricht=nachricht,
                max_tokens=max(64, laenge // 2),
                kind=kind,
            )
        except KiNichtVerfuegbar:
            raise TutorFehler("keine_ki", _("Der Tutor ist noch nicht eingerichtet.")) from None
        except KiFehler:
            raise TutorFehler("ki", tutor_texte.ton("ki_fehler", sprachstufe)) from None
        text = tutor_pruefung.antwort_kuerzen(antwort.text, laenge)
        grund = tutor_pruefung.leck_verdacht(
            text, stufe=stufe, aufgabe_text=aufgabe_text, bekannte=bekannte, eigene_texte=eigene
        )
        if not grund:
            return text, ""
        log.info("tutor_leck_verdacht grund=%s streng=%s", grund, streng)
    return tutor_texte.ton("zurueckgehalten", sprachstufe), Markierung.LECK


# --- Nachrichten --------------------------------------------------------------------------------


def nachricht_senden(g, text, *, jetzt=None):
    """Nachricht des Kindes verarbeiten. Gibt die Antwort des Tutors (``TutorNachricht``) zurück."""
    _pruefen_zugang()
    _pruefen_gespraech(g)
    jetzt = jetzt or zeit.jetzt()
    text = _text_pruefen(text)
    _pruefen_limit(g, jetzt)
    sprachstufe = selectors.sprachstufe(g.kind, _fach_von(g))

    lokal = None  # (Schlüssel, Markierung) für feste Antworten ohne KI
    if tutor_pruefung.ist_rollenwechsel(text):
        lokal = ("rollenwechsel", Markierung.ROLLENWECHSEL)
    elif tutor_pruefung.ist_loesungsbitte(text):
        lokal = ("umlenkung_loesung", Markierung.LOESUNGSBITTE)

    if lokal is not None:
        antwort_text, markierung = tutor_texte.ton(lokal[0], sprachstufe), lokal[1]
        stufe = 1 if markierung == Markierung.LOESUNGSBITTE else g.hilfestufe
        art = NachrichtArt.HINWEIS
    else:
        stufe = g.hilfestufe
        antwort_text, markierung = _ki_antwort(g, text, stufe, aufgabe_text=_aufgabe_text(g, text))
        art = NachrichtArt.ANTWORT

    with transaction.atomic():
        _speichern(
            g, NachrichtRolle.KIND, NachrichtArt.FRAGE, text, stufe=g.hilfestufe, jetzt=jetzt
        )
        if markierung == Markierung.LOESUNGSBITTE:
            g.hilfestufe = 1
        antwort = _speichern(
            g,
            NachrichtRolle.TUTOR,
            art,
            antwort_text,
            stufe=stufe,
            jetzt=jetzt,
            markierung=markierung,
        )
        g.letzte_aktivitaet = jetzt
        g.save(update_fields=["hilfestufe", "letzte_aktivitaet"])
        if art == NachrichtArt.ANTWORT:
            _sitzung_buchen(g, stufe)
    return antwort


def mehr_hilfe(g, *, jetzt=None):
    """Das Kind wünscht die nächste Hilfestufe. Stufe 5 ist das Ende der Leiter."""
    _pruefen_zugang()
    _pruefen_gespraech(g)
    jetzt = jetzt or zeit.jetzt()
    aufgabe = tutor_selectors.letzte_aufgabe(g)
    sprachstufe = selectors.sprachstufe(g.kind, _fach_von(g))
    if aufgabe is None or tutor_pruefung.ist_rollenwechsel(aufgabe):
        raise TutorFehler("nichts", tutor_texte.ton("nichts_zu_helfen", sprachstufe))
    if g.hilfestufe >= HILFESTUFE_MAX:
        raise TutorFehler("max_stufe", tutor_texte.ton("max_stufe", sprachstufe))
    _pruefen_limit(g, jetzt)
    stufe = g.hilfestufe + 1
    antwort_text, markierung = _ki_antwort(
        g,
        _("Ich brauche mehr Hilfe zu meiner letzten Aufgabe: %(aufgabe)s") % {"aufgabe": aufgabe},
        stufe,
        aufgabe_text=_aufgabe_text(g),
    )
    with transaction.atomic():
        _speichern(g, NachrichtRolle.KIND, NachrichtArt.MEHR_HILFE, "", stufe=stufe, jetzt=jetzt)
        antwort = _speichern(
            g,
            NachrichtRolle.TUTOR,
            NachrichtArt.ANTWORT,
            antwort_text,
            stufe=stufe,
            jetzt=jetzt,
            markierung=markierung,
        )
        g.hilfestufe = stufe
        g.letzte_aktivitaet = jetzt
        g.save(update_fields=["hilfestufe", "letzte_aktivitaet"])
        _sitzung_buchen(g, stufe)
    return antwort


# --- Lösungsversuch prüfen (getrennter Aufruf ``bewerten``) --------------------------------------


def versuch_pruefen(g, versuch, aufgabe="", *, jetzt=None):
    """Prüft einen eigenen Lösungsversuch in einem getrennten Aufruf mit strukturierter Ausgabe.

    Die Struktur wird streng gelesen und nie als Text weitergegeben: Das Kind sieht feste Sätze
    nach Urteil und Sprachstufe, dazu nur bei erlaubtem Vergleich (Einstellung) einen geprüften
    Kurzhinweis. Ungültige Ausgabe ergibt den sicheren Standard "unklar"."""
    _pruefen_zugang(bewerten=True)
    _pruefen_gespraech(g)
    jetzt = jetzt or zeit.jetzt()
    versuch = _text_pruefen(versuch)
    aufgabe = " ".join(str(aufgabe or "").split()) or tutor_selectors.letzte_frage(g) or ""
    if len(aufgabe) > wert("lernen.tutor_laenge_nachricht") * AUFGABE_FAKTOR:
        raise TutorFehler("zu_lang", _("Die Aufgabe ist zu lang für den Tutor."))
    material_text = _kontext_material(g)
    sprachstufe = selectors.sprachstufe(g.kind, _fach_von(g))
    if not aufgabe and not material_text:
        raise TutorFehler("nichts", tutor_texte.ton("nichts_zu_helfen", sprachstufe))
    _pruefen_limit(g, jetzt)

    aufgabe_text = "\n".join(t for t in (aufgabe, material_text) if t)
    bekannte = tutor_selectors.bekannte_antworten(g, [aufgabe, versuch])
    try:
        antwort = ki_services.ki_aufruf(
            KiAufgabe.BEWERTEN,
            system=tutor_prompts.SYSTEM_BEWERTEN,
            nachricht=tutor_prompts.nachricht_bewerten(
                aufgabe=aufgabe, versuch=versuch, material_text=material_text
            ),
            json_ausgabe=True,
            schema=tutor_prompts.SCHEMA_BEWERTEN,
            max_tokens=300,
            kind=g.kind,
        )
        bewertung = tutor_pruefung.bewertung_lesen(
            antwort.json, aufgabe_text=aufgabe_text, versuch=versuch, bekannte=bekannte
        )
    except KiNichtVerfuegbar:
        raise TutorFehler(
            "keine_ki", _("Das Prüfen von Versuchen ist noch nicht eingerichtet.")
        ) from None
    except KiFehler as fehler:
        if fehler.art != "ausgabe":
            raise TutorFehler("ki", tutor_texte.ton("ki_fehler", sprachstufe)) from None
        bewertung = tutor_pruefung.UNKLAR  # keine gültige Struktur: sicherer Standard

    teile = [tutor_texte.ton(f"urteil_{bewertung.urteil}", sprachstufe)]
    if bewertung.hinweis and wert("lernen.tutor_vergleich_nach_versuch"):
        teile.append(f"{tutor_texte.ton('tipp', sprachstufe)} {bewertung.hinweis}")
    if bewertung.urteil != "richtig" and bewertung.empfohlene_stufe > g.hilfestufe:
        teile.append(tutor_texte.ton("mehr_hilfe_angebot", sprachstufe))
    with transaction.atomic():
        _speichern(
            g, NachrichtRolle.KIND, NachrichtArt.VERSUCH, versuch, stufe=g.hilfestufe, jetzt=jetzt
        )
        ergebnis = _speichern(
            g,
            NachrichtRolle.TUTOR,
            NachrichtArt.BEWERTUNG,
            " ".join(teile),
            stufe=g.hilfestufe,
            jetzt=jetzt,
            urteil=bewertung.urteil,
            empfohlene_stufe=bewertung.empfohlene_stufe,
        )
        g.letzte_aktivitaet = jetzt
        g.save(update_fields=["letzte_aktivitaet"])
    return ergebnis
