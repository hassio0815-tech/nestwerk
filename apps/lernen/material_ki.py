"""KI-Schritte der Material-Pipeline (SPEC 21.5/21.6): Handler für ``auslesen`` und
``fragen_erzeugen`` und die strenge Prüfung ihrer Ausgabe.

Sicherheitsmodell (Prompt-Injection): Das Material ist unvertrauenswürdig. Es steht nur in der
Nutzer-Nachricht zwischen Begrenzern (``material_prompts``). Was die KI antwortet, gilt als
**Daten**:
Es wird gegen ein festes Schema geprüft (Typ, Länge, keine Links, kein HTML, keine Kontaktdaten),
ungültige Antworten sind ein Fehlversuch (``KiAusgabeFehler``) und werden **nicht** gespeichert.
Gespeicherte Texte werden bei der Anzeige immer escaped (Django-Templates).

Die Handler laufen im Job ``ki_auftraege_verarbeiten``; sie melden Fehler als ``KiFehler``
(Wiederholung mit Wartezeit durch die Warteschlange) oder setzen das Material selbst auf
``fehler``, wenn ein neuer Versuch nichts ändern würde.
"""

import logging
import re
from dataclasses import dataclass

from django.db import transaction

from apps.kern import audit
from apps.kern.einstellungen import wert

from . import (
    ki_services,
    ki_warteschlange,
    material_dateien,
    material_prompts,
    material_services,
    selectors,
    services,
)
from .ki import KiAusgabeFehler, KiBild
from .models import (
    Frage,
    FrageTyp,
    KiAufgabe,
    Material,
    MaterialStatus,
    Quelle,
    Thema,
)
from .speicher import Speicher, SpeicherFehler

log = logging.getLogger("nestwerk.lernen.material")

KLASSENSTUFEN = range(1, 14)
_HTML = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>|&lt;|&gt;|&#|javascript:|data:text", re.IGNORECASE)
_URL = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|www\.|\b[\w-]+\.(?:com|de|org|net|io|info|biz|xyz|ru|cn|tk)\b)",
    re.IGNORECASE,
)
_MAIL = re.compile(r"\S+@\S+\.\S+")
_TELEFON = re.compile(r"(?<!\d)\+?\d[\d /().-]{7,}\d(?!\d)")


# --- Prüfung der KI-Ausgabe ------------------------------------------------------------------


def text_pruefen(wert_, max_laenge):
    """Ein kurzer Text aus KI oder Formular: bereinigt oder ``""`` (abgelehnt). Abgelehnt wird,
    was kein Text ist, zu lang ist, nach HTML, Link, E-Mail-Adresse oder Telefonnummer aussieht."""
    if not isinstance(wert_, str):
        return ""
    text = " ".join(material_dateien.text_bereinigen(wert_).split())
    if not text or len(text) > max_laenge:
        return ""
    if _HTML.search(text) or _URL.search(text) or _MAIL.search(text) or _TELEFON.search(text):
        return ""
    return text


@dataclass(frozen=True)
class Auslesen:
    text: str
    fach: object  # Fach oder None
    thema: str
    klassenstufe: int | None
    konfidenz: float


def _zahl(x):
    return isinstance(x, int | float) and not isinstance(x, bool)


def auslesen_pruefen(daten, faecher):
    """Prüft die JSON-Antwort der Aufgabe ``auslesen``. ``faecher``: ``{schluessel: Fach}``.
    Ungültig: ``KiAusgabeFehler``."""
    if not isinstance(daten, dict):
        raise KiAusgabeFehler()
    text = daten.get("text", "")
    konfidenz = daten.get("konfidenz")
    if not isinstance(text, str) or not _zahl(konfidenz) or not 0 <= konfidenz <= 1:
        raise KiAusgabeFehler()
    fach = daten.get("fach")
    fach = faecher.get(fach.strip().lower()) if isinstance(fach, str) else None
    stufe = daten.get("klassenstufe")
    stufe = stufe if isinstance(stufe, int) and not isinstance(stufe, bool) else None
    return Auslesen(
        text=material_dateien.text_bereinigen(text),
        fach=fach,
        thema=text_pruefen(daten.get("thema"), 80),
        klassenstufe=stufe if stufe in KLASSENSTUFEN else None,
        konfidenz=float(konfidenz) if fach is not None else 0.0,
    )


def fragen_pruefen(daten, maximal):
    """Prüft die JSON-Antwort der Aufgabe ``fragen_erzeugen`` und gibt gültige, einmalige
    ``(typ, frage, antwort)`` zurück (höchstens ``maximal``). Einzelne ungültige Einträge entfallen;
    ist die Form falsch oder fällt mehr als die Hälfte weg, ist das ein Fehlversuch. Eine leere
    Liste ist erlaubt (das Material gibt nichts her)."""
    if not isinstance(daten, dict) or not isinstance(daten.get("fragen"), list):
        raise KiAusgabeFehler()
    roh = daten["fragen"]
    gueltig, gesehen = [], set()
    for eintrag in roh:
        if not isinstance(eintrag, dict) or eintrag.get("typ") not in FrageTyp.values:
            continue
        frage = text_pruefen(eintrag.get("frage"), 300)
        antwort = text_pruefen(eintrag.get("antwort"), 300)
        schluessel = (frage.lower(), antwort.lower())
        if not frage or not antwort or schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        gueltig.append((eintrag["typ"], frage, antwort))
    if roh and len(gueltig) * 2 < len(roh):
        raise KiAusgabeFehler()
    return gueltig[:maximal]


# --- Hilfen ----------------------------------------------------------------------------------


def thema_holen(kind, fach, name):
    """Thema für Material-Fragen: Name wie vorgeschlagen, Klassenstufe des Kindes im Fach (oder
    stufenlos), damit das Kind es im Üben auch sieht. Vorhandene Themen werden wiederverwendet."""
    name = text_pruefen(name, 80) or "Material"
    stufe = selectors.klassenstufe(kind, fach)
    vorhanden = Thema.objects.filter(fach=fach, klassenstufe=stufe, name__iexact=name).first()
    if vorhanden is not None:
        return vorhanden
    return Thema.objects.create(fach=fach, klassenstufe=stufe, name=name)


def _material_zu(auftrag, aufgabe, erlaubt):
    """Das Material zum Auftrag, wenn der Auftrag noch aktuell ist, sonst ``None``."""
    verweis = auftrag.eingabe_verweis
    if not verweis.startswith(material_services.VERWEIS):
        return None
    nr = verweis[len(material_services.VERWEIS) :]
    if not nr.isdigit():
        return None
    material = Material.objects.select_related("kind", "fach").filter(pk=int(nr)).first()
    if material is None or material.status not in erlaubt:
        return None
    if auftrag.schluessel != material_services.auftrag_schluessel(aufgabe, material):
        return None  # Material wurde neu gestartet: dieser Auftrag ist veraltet
    return material


def _lesen(material, speicher):
    for bereich in dict.fromkeys((material.bereich, "inbox", "archiv")):
        try:
            return speicher.lesen(material.kind_id, bereich, material.name)
        except (FileNotFoundError, SpeicherFehler):
            continue
    return None


def _faecher():
    return {f.schluessel: f for f in selectors.faecher()}


# --- Handler: auslesen -----------------------------------------------------------------------


def auslesen_handler(auftrag):
    material = _material_zu(
        auftrag, KiAufgabe.AUSLESEN, (MaterialStatus.WARTET, MaterialStatus.LIEST)
    )
    if material is None:
        return
    Material.objects.filter(pk=material.pk).update(status=MaterialStatus.LIEST)
    speicher = Speicher()
    daten = _lesen(material, speicher)
    if daten is None:
        material_services.fehler_setzen(material, "datei")
        return
    ext = material_dateien.endung(material.name)
    text = material_dateien.text_aus_datei(ext, daten)  # Text-PDF und txt: ohne KI
    bilder = ()
    if not text:
        if ext == "jpg":
            bilder = (KiBild("image/jpeg", daten),)
        elif ext == "pdf":
            bilder = tuple(KiBild("image/jpeg", b) for b in material_dateien.pdf_bilder(daten))
        if not bilder:
            material_services.fehler_setzen(material, "kein_text" if ext == "pdf" else "leer")
            return
    faecher = _faecher()
    hinweis = material.hinweis_fach if material.hinweis_fach in faecher else ""
    liste = [(f.schluessel, f.name) for f in faecher.values()]
    antwort = ki_services.ki_aufruf(
        KiAufgabe.AUSLESEN,
        system=material_prompts.SYSTEM_AUSLESEN_TEXT
        if text
        else material_prompts.SYSTEM_AUSLESEN_BILD,
        nachricht=material_prompts.nachricht_auslesen(
            liste, hinweis=hinweis, text=text or None, bild_hinweis=bool(bilder)
        ),
        bilder=bilder,
        json_ausgabe=True,
        schema=material_prompts.SCHEMA_AUSLESEN,
        max_tokens=4096,
        kind=material.kind,
    )
    ergebnis = auslesen_pruefen(antwort.json, faecher)
    gesamt = text or ergebnis.text
    if not gesamt.strip():
        material_services.fehler_setzen(material, "leer")
        return
    fach, konfidenz = ergebnis.fach, ergebnis.konfidenz
    if hinweis:  # Fach-Unterordner ist ein bewusster Hinweis des Kindes oder der Eltern
        fach, konfidenz = faecher[hinweis], 1.0
    elif material.fach_id and material.konfidenz == 1.0:  # Eltern haben schon gewählt
        fach, konfidenz = material.fach, 1.0
    sicher = fach is not None and konfidenz >= wert("lernen.auslesen_min_konfidenz") / 100
    _archivieren(material, speicher)
    Material.objects.filter(pk=material.pk).update(
        text=gesamt,
        fach=fach,
        thema_name=ergebnis.thema or material.thema_name,
        klassenstufe=ergebnis.klassenstufe,
        konfidenz=konfidenz,
        fehler="",
        status=MaterialStatus.FRAGEN if sicher else MaterialStatus.RUECKFRAGE,
    )
    log.info("material %s ausgelesen prompt=%s", material.pk, material_prompts.AUSLESEN_VERSION)
    if sicher:
        material.refresh_from_db()
        material_services.einreihen(material)


def _archivieren(material, speicher):
    """Original ins ``archiv`` (nach erfolgreichem Auslesen). Schon dort: nichts zu tun."""
    if material.bereich == "archiv":
        return
    try:
        speicher.verschieben(material.kind_id, material.name, "inbox", "archiv")
    except FileNotFoundError:  # schon verschoben (früherer Versuch)
        pass
    Material.objects.filter(pk=material.pk).update(bereich="archiv")
    material.bereich = "archiv"


# --- Handler: fragen_erzeugen ----------------------------------------------------------------


def fragen_handler(auftrag):
    material = _material_zu(auftrag, KiAufgabe.FRAGEN_ERZEUGEN, (MaterialStatus.FRAGEN,))
    if material is None:
        return
    if not material.text.strip() or material.fach_id is None:
        material_services.fehler_setzen(material, "leer")
        return
    kind, fach = material.kind, material.fach
    maximal = wert("lernen.fragen_je_material_max")
    antwort = ki_services.ki_aufruf(
        KiAufgabe.FRAGEN_ERZEUGEN,
        system=material_prompts.system_fragen(maximal, selectors.sprachstufe(kind, fach)),
        nachricht=material_prompts.nachricht_fragen(fach.name, material.thema_name, material.text),
        json_ausgabe=True,
        schema=material_prompts.SCHEMA_FRAGEN,
        max_tokens=4096,
        kind=kind,
    )
    paare = fragen_pruefen(antwort.json, maximal)  # ungültig: Fehlversuch, nichts gespeichert
    if not paare:
        material_services.fehler_setzen(material, "keine_fragen")
        return
    with transaction.atomic():
        thema = thema_holen(kind, fach, material.thema_name)
        vorhanden = {
            (f.frage.lower(), f.antwort.lower())
            for f in Frage.objects.filter(thema=thema, kind=kind)
        }
        neu = 0
        for typ, frage, antw in paare:
            if (frage.lower(), antw.lower()) in vorhanden:
                continue
            services.frage_anlegen(
                thema, typ, frage, antw, quelle=Quelle.KI, kind=kind, material=material
            )
            neu += 1
        if neu:
            audit.protokollieren(
                "lernen.material_fragen",
                akteur=None,
                kind=kind,
                objekt=material,
                details={"n": neu, "prompt": material_prompts.FRAGEN_VERSION},
            )
    if Frage.objects.filter(material=material).exists():
        material_services.status_abgleichen(material)
    else:  # alle schon vorhanden (z. B. dasselbe Blatt noch einmal): nichts Neues
        material_services.fehler_setzen(material, "keine_fragen")


def registrieren():
    ki_warteschlange.handler_registrieren(KiAufgabe.AUSLESEN, auslesen_handler)
    ki_warteschlange.handler_registrieren(KiAufgabe.FRAGEN_ERZEUGEN, fragen_handler)
