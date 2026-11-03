"""Material-Pipeline der Lernmappe (SPEC 21.5): aufnehmen, einreihen, freigeben, löschen.

Weg eines Materials: Upload oder Datei im Ordner ``inbox`` -> ``Material`` (Datei bleibt in
``inbox``) -> KI-Auftrag ``auslesen`` (Text, Fach, Thema) -> KI-Auftrag ``fragen_erzeugen`` ->
Original wandert ins ``archiv`` -> Fragen warten auf die Eltern oder sind sofort nutzbar.
Die Fachlogik der KI-Schritte steht in ``material_ki``; hier liegen Zustand und Dateien.

- Ohne einsatzbereite KI wartet ein Material mit dem Status ``wartet_ki``; es geht nichts verloren
  und nichts stürzt ab. ``wartende_einreihen`` (Job und Upload) holt es nach.
- Originale bleiben im Archiv, bis die Eltern das Material löschen (Datei, Text und Fragen).
- Geschwister sehen nie Material der anderen: alle Lesezugriffe filtern nach dem Kind.
"""

import hashlib
import logging
import time
import uuid
from collections import Counter

from django.db import transaction
from django.utils.translation import gettext as _

from apps.kern import audit
from apps.kern.einstellungen import wert

from . import ki_selectors, ki_warteschlange, material_dateien, services
from .material_dateien import UploadFehler
from .models import (
    Frage,
    Freigabe,
    KiAufgabe,
    KiAuftrag,
    KiAuftragStatus,
    Material,
    MaterialEingang,
    MaterialStatus,
    Quelle,
)
from .speicher import Speicher, SpeicherFehler, SpeicherVoll

log = logging.getLogger("nestwerk.lernen.material")

VERWEIS = "lernen.material:"
# Fehlerarten der Warteschlange, bei denen nur die KI-Einrichtung fehlt (kein echter Fehler)
_KI_AUS = {"aus", "einwilligung"}
_IN_ARBEIT = (MaterialStatus.WARTET, MaterialStatus.LIEST, MaterialStatus.FRAGEN)


class MaterialFehler(ValueError):
    """Fachlicher Fehler; ``str(fehler)`` ist ein freundlicher Hinweis."""


FEHLERTEXTE = {
    "leer": _("Im Material ist kein Text zu erkennen."),
    "kein_text": _("In diesem PDF ist kein Text und kein Bild zu erkennen."),
    "datei": _("Die Datei fehlt oder ist nicht lesbar."),
    "zu_gross": _("Die Datei ist zu groß."),
    "typ": _("Diese Datei können wir nicht nehmen."),
    "doppelt": _("Dieses Material ist schon in der Mappe."),
    "voll": _("Der Speicher ist voll."),
    "keine_fragen": _("Aus diesem Material konnten keine Fragen gemacht werden."),
    "abgelehnt": _("Die Eltern haben dieses Material abgelehnt."),
    "ausgabe": _("Die Antwort der KI war nicht brauchbar."),
    "intern": _("Unerwarteter Fehler."),
}


def fehlertext(material):
    """Anzeigetext zum Fehlercode eines Materials (KI-Fehler: Text aus ``ki_texte``)."""
    from .ki_texte import FEHLERTEXTE as KI_TEXTE

    code = material.fehler
    if not code:
        return ""
    return str(FEHLERTEXTE.get(code) or KI_TEXTE.get(code) or FEHLERTEXTE["intern"])


def kind_pruefen(kind):
    if getattr(kind, "rolle", None) != "kind":
        raise MaterialFehler(_("Material gibt es nur für Kinder."))


def _speicher(speicher):
    return speicher or Speicher()


# --- Aufnehmen -------------------------------------------------------------------------------


def aufnehmen(kind, name, daten, *, eingang=MaterialEingang.UPLOAD, hinweis_fach="", speicher=None):
    """Prüft eine Datei und legt sie in die ``inbox`` des Kindes. Wirft ``UploadFehler``
    (Typ, Größe), ``MaterialFehler`` (Doppelt) oder ``SpeicherVoll``. Stellt die
    KI-Verarbeitung in die Warteschlange, sobald eine KI bereit ist."""
    kind_pruefen(kind)
    speicher = _speicher(speicher)
    max_bytes = wert("lernen.upload_max_mb") * 1024 * 1024
    geprueft = material_dateien.pruefen(name, daten, max_bytes)
    inhalt_hash = hashlib.sha256(daten).hexdigest()
    if Material.objects.filter(kind=kind, inhalt_hash=inhalt_hash).exists():
        raise MaterialFehler(_("Das hast du schon hochgeladen."))
    services.lernmappe_sicherstellen(kind, speicher)
    ablage = f"{uuid.uuid4().hex}.{geprueft.ext}"
    speicher.speichern(
        kind.pk, "inbox", ablage, geprueft.daten, limit_bytes=services.speicher_limit_bytes()
    )
    try:
        with transaction.atomic():
            material = Material.objects.create(
                kind=kind,
                name=ablage,
                anzeigename=geprueft.anzeigename,
                art=geprueft.art,
                mime=geprueft.mime,
                groesse=len(geprueft.daten),
                inhalt_hash=inhalt_hash,
                eingang=eingang,
                hinweis_fach=hinweis_fach[:40],
            )
            audit.protokollieren(
                "lernen.material_aufgenommen",
                akteur=None if eingang == MaterialEingang.INBOX else audit.AKTUELL,
                kind=kind,
                objekt=material,
                details={"art": geprueft.art, "groesse": len(geprueft.daten), "eingang": eingang},
            )
    except Exception:
        speicher.loeschen(kind.pk, "inbox", ablage)
        raise
    einreihen(material)
    material.refresh_from_db()
    return material


# --- Warteschlange ---------------------------------------------------------------------------


def auftrag_schluessel(aufgabe, material):
    return f"lernen.material.{aufgabe}:{material.pk}:{material.durchgang}"


def _ki_bereit(aufgabe):
    anbieter = ki_selectors.zuordnung_fuer(aufgabe)
    return ki_selectors.status_von(anbieter) is ki_selectors.KiStatus.BEREIT


def einreihen(material):
    """Nächster KI-Schritt des Materials. Ohne bereite KI: ``wartet_ki`` (kein Auftrag)."""
    if material.status == MaterialStatus.FRAGEN or (material.text and material.fach_id):
        aufgabe, ziel = KiAufgabe.FRAGEN_ERZEUGEN, MaterialStatus.FRAGEN
    else:
        aufgabe, ziel = KiAufgabe.AUSLESEN, MaterialStatus.WARTET
    if not _ki_bereit(aufgabe):
        Material.objects.filter(pk=material.pk).update(status=MaterialStatus.WARTET_KI, fehler="")
        return False
    Material.objects.filter(pk=material.pk).update(status=ziel, fehler="")
    ki_warteschlange.auftrag_einreihen(
        aufgabe,
        auftrag_schluessel(aufgabe, material),
        kind=material.kind,
        eingabe_verweis=f"{VERWEIS}{material.pk}",
    )
    return True


def neu_starten(material):
    """Eltern: neuer Versuch nach einem Fehler (neuer Durchgang = neuer Auftrag)."""
    if material.status not in (MaterialStatus.FEHLER, MaterialStatus.WARTET_KI):
        raise MaterialFehler(_("Dieses Material braucht keinen neuen Versuch."))
    if material.status == MaterialStatus.FEHLER and material.fehler in ("zu_gross", "typ", "datei"):
        raise MaterialFehler(_("Diese Datei lässt sich nicht verarbeiten. Bitte löschen."))
    Material.objects.filter(pk=material.pk).update(durchgang=material.durchgang + 1)
    material.refresh_from_db()
    return einreihen(material)


def wartende_einreihen():
    """Gleicht Material und Warteschlange ab (Job, alle paar Minuten). Gibt Zähler zurück.

    - ``wartet_ki`` und KI jetzt bereit: einreihen.
    - Auftrag endgültig gescheitert: bei fehlender KI zurück auf ``wartet_ki`` (neuer
      Durchgang), sonst Status ``fehler`` mit Fehlerart.
    """
    zaehler = Counter()
    for material in Material.objects.filter(
        status__in=(*_IN_ARBEIT, MaterialStatus.WARTET_KI)
    ).select_related("kind"):
        if material.status == MaterialStatus.WARTET_KI:
            if einreihen(material):
                zaehler["eingereiht"] += 1
            continue
        aufgabe = (
            KiAufgabe.FRAGEN_ERZEUGEN
            if material.status == MaterialStatus.FRAGEN
            else KiAufgabe.AUSLESEN
        )
        auftrag = KiAuftrag.objects.filter(schluessel=auftrag_schluessel(aufgabe, material)).first()
        if auftrag is None:  # kein Auftrag (z. B. Absturz nach dem Statuswechsel)
            einreihen(material)
            zaehler["nachgereicht"] += 1
        elif auftrag.status == KiAuftragStatus.FEHLER:
            if auftrag.fehler_art in _KI_AUS:
                Material.objects.filter(pk=material.pk).update(
                    status=MaterialStatus.WARTET_KI, durchgang=material.durchgang + 1
                )
                zaehler["zurueck_auf_ki"] += 1
            else:
                fehler_setzen(material, auftrag.fehler_art or "intern")
                zaehler["fehler"] += 1
    return dict(zaehler)


def fehler_setzen(material, art):
    Material.objects.filter(pk=material.pk).update(status=MaterialStatus.FEHLER, fehler=art[:30])


# --- Inbox-Scan (zweiter Eingang) ------------------------------------------------------------


def inbox_scannen(*, speicher=None, jetzt=None, pause=1.0, ruhe=None, maximal=None):
    """Übernimmt neue Dateien aus dem Ordner ``inbox`` aller Kinder (z. B. vom NAS).

    Eine Datei gilt als stabil, wenn sie ``lernen.scan_ruhe_sekunden`` unverändert ist und ihre
    Größe sich während ``pause`` Sekunden nicht ändert. Dateien, zu denen es schon ein Material
    gibt (Uploads, die noch warten), werden übersprungen; das macht den Lauf wiederholbar.
    Fehlerhafte Dateien (Typ, Größe, doppelt) wandern mit einem Fehler-Material ins Archiv,
    damit sie nicht jeden Lauf neu auftauchen. Gibt Zähler zurück."""
    from apps.konten import selectors as konten

    speicher = _speicher(speicher)
    ruhe = wert("lernen.scan_ruhe_sekunden") if ruhe is None else ruhe
    maximal = wert("lernen.scan_dateien_pro_lauf") if maximal is None else maximal
    jetzt_ts = jetzt if jetzt is not None else time.time()
    zaehler = Counter()
    kandidaten = []
    for kind in konten.aktive_kinder():
        bekannt = set(Material.objects.filter(kind=kind).values_list("name", flat=True))
        try:
            dateien = speicher.inbox_dateien(kind.pk)
        except SpeicherFehler:  # pragma: no cover - Kind-ID ist immer gültig
            continue
        for datei in dateien:
            if not datei.hinweis and datei.name in bekannt:
                continue  # Upload oder schon übernommen
            if jetzt_ts - datei.geaendert < ruhe:
                zaehler["noch_nicht_ruhig"] += 1
                continue
            kandidaten.append((kind, datei))
    if kandidaten and pause:
        time.sleep(pause)
    for kind, datei in kandidaten[:maximal]:
        try:
            if datei.pfad.stat().st_size != datei.groesse:
                zaehler["noch_nicht_ruhig"] += 1
                continue
        except OSError:
            continue
        _scan_datei(kind, datei, speicher, zaehler)
    zaehler["uebrig"] = max(0, len(kandidaten) - maximal)
    return {k: v for k, v in zaehler.items() if v}


def _scan_datei(kind, datei, speicher, zaehler):
    hinweis = datei.hinweis if _fach_schluessel(datei.hinweis) else ""
    try:
        if datei.groesse > wert("lernen.upload_max_mb") * 1024 * 1024:
            raise UploadFehler("zu_gross")
        daten = datei.pfad.read_bytes()
        material = aufnehmen(
            kind,
            datei.name,
            daten,
            eingang=MaterialEingang.INBOX,
            hinweis_fach=hinweis,
            speicher=speicher,
        )
    except SpeicherVoll:
        zaehler["speicher_voll"] += 1  # bleibt liegen, Eltern räumen auf
        return
    except (UploadFehler, MaterialFehler, OSError) as exc:
        _abgelehnt(kind, datei, speicher, _fehlercode(exc))
        zaehler["abgelehnt"] += 1
        return
    try:
        datei.pfad.unlink()
    except OSError:  # pragma: no cover - Original lässt sich nicht löschen
        log.warning("inbox_original_bleibt kind=%s", kind.pk)
    zaehler["uebernommen"] += 1
    return material


def _fehlercode(exc):
    if isinstance(exc, MaterialFehler):
        return "doppelt"
    if isinstance(exc, OSError):
        return "datei"
    return "zu_gross" if str(exc) == "zu_gross" else "typ"


def _abgelehnt(kind, datei, speicher, code):
    """Datei ins Archiv, Fehler-Material für die Eltern (Inhalt wird nie gelesen oder gezeigt)."""
    ext = material_dateien.endung(datei.name)
    ext = ext if ext in material_dateien.ENDUNGEN else "bin"
    ablage = f"{uuid.uuid4().hex}.{ext}"
    try:
        speicher.uebernehmen(kind.pk, datei.pfad, "archiv", ablage)
    except (OSError, SpeicherFehler):
        return
    Material.objects.create(
        kind=kind,
        name=ablage,
        anzeigename=material_dateien.anzeigename_bereinigen(datei.name),
        art="dokument",
        mime="application/octet-stream",
        groesse=datei.groesse,
        inhalt_hash=uuid.uuid4().hex * 2,  # kein echter Hash: die Datei wurde nicht geprüft
        bereich="archiv",
        eingang=MaterialEingang.INBOX,
        status=MaterialStatus.FEHLER,
        fehler=code,
    )


def _fach_schluessel(hinweis):
    from .models import Fach

    return bool(hinweis) and Fach.objects.filter(schluessel=hinweis, aktiv=True).exists()


# --- Freigabe --------------------------------------------------------------------------------


sofort_nutzbar = services.fragen_sofort_nutzbar


def sofort_nutzbar_setzen(kind, an):
    mappe = services.lernmappe_sicherstellen(kind)
    mappe.fragen_sofort_nutzbar = bool(an)
    mappe.save(update_fields=["fragen_sofort_nutzbar"])
    audit.protokollieren(
        "lernen.material_freigabe_regel",
        kind=kind,
        objekt=mappe,
        details={"sofort": bool(an)},
    )
    return mappe


def status_abgleichen(material):
    """Setzt wartet_eltern, bereit oder fehler nach dem Stand der Fragen (nur im Endbereich)."""
    endbereich = material.status in (
        MaterialStatus.FRAGEN,
        MaterialStatus.WARTET_ELTERN,
        MaterialStatus.BEREIT,
    ) or (material.status == MaterialStatus.FEHLER and material.fehler == "abgelehnt")
    if not endbereich:
        return material.status
    stand = set(material.fragen.values_list("freigabe", flat=True))
    fehler = ""
    if Freigabe.OFFEN in stand:
        neu = MaterialStatus.WARTET_ELTERN
    elif Freigabe.FREIGEGEBEN in stand:
        neu = MaterialStatus.BEREIT
    else:  # alles abgelehnt oder gar keine Fragen
        neu = MaterialStatus.FEHLER
        fehler = "abgelehnt" if stand else "keine_fragen"
    Material.objects.filter(pk=material.pk).update(status=neu, fehler=fehler)
    material.status, material.fehler = neu, fehler
    return neu


def _frage_im_material(material, frage_pk):
    frage = Frage.objects.filter(pk=frage_pk, material=material, kind=material.kind).first()
    if frage is None:
        raise MaterialFehler(_("Diese Frage gibt es nicht."))
    return frage


@transaction.atomic
def freigeben(material, frage_ids=None):
    """Eltern: gibt wartende Fragen frei (``None`` = alle wartenden des Materials)."""
    if frage_ids is None:
        qs = material.fragen.filter(freigabe=Freigabe.OFFEN)
    else:  # ausdrücklich gewählte Fragen dürfen auch nachträglich freigegeben werden
        qs = material.fragen.filter(pk__in=list(frage_ids)).exclude(freigabe=Freigabe.FREIGEGEBEN)
    anzahl = qs.update(freigabe=Freigabe.FREIGEGEBEN)
    status_abgleichen(material)
    audit.protokollieren(
        "lernen.material_freigegeben", kind=material.kind, objekt=material, details={"n": anzahl}
    )
    return anzahl


@transaction.atomic
def ablehnen(material, frage_ids=None):
    """Eltern: lehnt wartende Fragen ab (``None`` = alle wartenden des Materials)."""
    qs = material.fragen.filter(freigabe=Freigabe.OFFEN)
    if frage_ids is not None:
        qs = qs.filter(pk__in=list(frage_ids))
    anzahl = qs.update(freigabe=Freigabe.ABGELEHNT)
    status_abgleichen(material)
    audit.protokollieren(
        "lernen.material_abgelehnt", kind=material.kind, objekt=material, details={"n": anzahl}
    )
    return anzahl


def frage_bearbeiten(material, frage_pk, frage_text, antwort_text):
    """Eltern: ändert Frage und Antwort. Die Texte werden wie KI-Ausgaben streng geprüft."""
    from .material_ki import text_pruefen

    frage = _frage_im_material(material, frage_pk)
    neu_frage = text_pruefen(frage_text, 300)
    neu_antwort = text_pruefen(antwort_text, 300)
    if not neu_frage or not neu_antwort:
        raise MaterialFehler(_("Bitte Frage und Antwort ausfüllen (ohne Links und ohne HTML)."))
    frage.frage, frage.antwort = neu_frage, neu_antwort
    frage.save(update_fields=["frage", "antwort"])
    return frage


def fach_aendern(material, fach, thema_name=""):
    """Eltern: Fach (und Thema) zuordnen, z. B. bei ``braucht Rückfrage``. Verschiebt schon
    erzeugte Fragen ins neue Thema; sonst geht es mit der Fragen-Erzeugung weiter."""
    from .material_ki import text_pruefen, thema_holen

    if not fach.aktiv:
        raise MaterialFehler(_("Dieses Fach ist nicht aktiv."))
    name = text_pruefen(thema_name, 80) or material.thema_name or ""
    with transaction.atomic():
        material.fach = fach
        material.thema_name = name[:80]
        material.konfidenz = 1.0
        material.save(update_fields=["fach", "thema_name", "konfidenz"])
        if material.fragen.exists():
            thema = thema_holen(material.kind, fach, material.thema_name)
            material.fragen.update(thema=thema)
        audit.protokollieren(
            "lernen.material_fach", kind=material.kind, objekt=material, details={"fach": fach.pk}
        )
    if material.status == MaterialStatus.RUECKFRAGE:
        Material.objects.filter(pk=material.pk).update(
            status=MaterialStatus.FRAGEN, durchgang=material.durchgang + 1
        )
        material.refresh_from_db()
        einreihen(material)
    return material


def manuelle_frage(material, typ, frage_text, antwort_text):
    """Eltern: Frage von Hand aus dem Text anlegen (sofort freigegeben)."""
    from .material_ki import text_pruefen, thema_holen
    from .models import FrageTyp

    if material.fach_id is None:
        raise MaterialFehler(_("Bitte zuerst ein Fach wählen."))
    if typ not in FrageTyp.values:
        typ = FrageTyp.FRAGE
    f, a = text_pruefen(frage_text, 300), text_pruefen(antwort_text, 300)
    if not f or not a:
        raise MaterialFehler(_("Bitte Frage und Antwort ausfüllen (ohne Links und ohne HTML)."))
    thema = thema_holen(material.kind, material.fach, material.thema_name)
    neu = services.frage_anlegen(thema, typ, f, a, quelle=Quelle.ELTERN, kind=material.kind)
    neu.material = material
    neu.save(update_fields=["material"])
    if material.status in (MaterialStatus.WARTET_ELTERN, MaterialStatus.BEREIT) or (
        material.status == MaterialStatus.FEHLER
        and material.fehler in ("abgelehnt", "keine_fragen")
    ):
        Material.objects.filter(pk=material.pk).update(status=MaterialStatus.FRAGEN)
        material.status = MaterialStatus.FRAGEN
        status_abgleichen(material)
    return neu


# --- Löschen ---------------------------------------------------------------------------------


def loeschen(material, *, speicher=None):
    """Eltern: löscht Datei, ausgelesenen Text und Fragen (Fragen gehen mit dem Material).
    Zugehörige Warteschlangen-Einträge werden entfernt, laufende KI-Arbeit findet kein Material
    mehr und tut nichts."""
    speicher = _speicher(speicher)
    kind, name, bereich, pk = material.kind, material.name, material.bereich, material.pk
    with transaction.atomic():
        KiAuftrag.objects.filter(eingabe_verweis=f"{VERWEIS}{pk}").delete()
        audit.protokollieren(
            "lernen.material_geloescht",
            kind=kind,
            objekt=material,
            details={"art": material.art, "groesse": material.groesse},
        )
        material.delete()
    for ort in {bereich, "inbox", "archiv"}:
        try:
            speicher.loeschen(kind.pk, ort, name)
        except SpeicherFehler:  # pragma: no cover - Name stammt von uns
            pass


# --- Lesen für Seiten ------------------------------------------------------------------------


def verbrauch(kind, speicher=None):
    """(belegt_bytes, limit_bytes) der Lernmappe."""
    return _speicher(speicher).belegt_bytes(kind.pk), services.speicher_limit_bytes()


def datei_oeffnen(material, speicher=None):
    """Pfad der Datei (inbox oder archiv) oder ``None``."""
    speicher = _speicher(speicher)
    for bereich in (material.bereich, "inbox", "archiv"):
        try:
            pfad = speicher.pfad(material.kind_id, bereich, material.name)
        except SpeicherFehler:  # pragma: no cover
            return None
        if pfad.is_file():
            return pfad
    return None
