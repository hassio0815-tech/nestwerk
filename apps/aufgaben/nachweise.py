"""Nachweis-Fotos (AP13, ARCHITECTURE 9): Validierung, Neu-Kodierung, private Ablage, Löschung.

Ablage: ``NACHWEIS_DIR/<meldung_id>/<32 Hex>.jpg``. Es gibt bewusst kein eigenes Modell: Der
Ordnername verweist auf die Meldung, der Nachweis-Text liegt in ``Meldung.text``. Dateien sind
nie öffentlich (Auslieferung nur über die View in ``views_nachweis``), nie im Backup und werden
bei Bestätigung/Ablehnung sofort gelöscht (``on_commit``); ``aufraeumen`` ist das Sicherheitsnetz.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import time
import uuid
import warnings
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.kern import audit, einstellungen

from .models import MELDUNG_LAUFEND, Meldung
from .zustand import AblaufFehler

log = logging.getLogger(__name__)

MAX_PIXEL = 40_000_000
JPEG_QUALITAET = 85
WAISEN_KARENZ_SEKUNDEN = 3600  # laufende Transaktionen nicht stören
ERLAUBTE_FORMATE = {"JPEG", "PNG", "WEBP", "HEIF"}
NAME_MUSTER = re.compile(r"[0-9a-f]{32}\.jpg")

try:  # HEIC (iPhone) ist optional; ohne pillow-heif gibt es einen klaren Hinweis
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_MOEGLICH = True
except ImportError:  # pragma: no cover - pillow-heif ist Abhängigkeit
    HEIC_MOEGLICH = False

MELDUNG_KEIN_BILD = "Das ist kein Foto, das wir verwenden können. Bitte nimm ein neues Foto auf."


def wurzel() -> Path:
    return Path(settings.NACHWEIS_DIR)


def max_bytes() -> int:
    """Höchstgröße eines Uploads (Einstellung ``aufgaben.nachweis_max_upload_mb``)."""
    return einstellungen.wert("aufgaben.nachweis_max_upload_mb") * 1024 * 1024


def max_fotos() -> int:
    """Höchstzahl Fotos je Meldung (Einstellung ``aufgaben.nachweis_max_anzahl``)."""
    return einstellungen.wert("aufgaben.nachweis_max_anzahl")


def max_kante() -> int:
    """Längste Kante des gespeicherten Fotos (Einstellung ``aufgaben.nachweis_max_kante_px``)."""
    return einstellungen.wert("aufgaben.nachweis_max_kante_px")


def anfrage_zu_gross(content_length) -> bool:
    """Vorabprüfung des ``Content-Length`` einer Meldung, **bevor** Django die Dateien liest:
    sonst landet ein beliebig großer Upload erst komplett auf der Platte (Review AP19, B-07).
    Puffer 1 MB für Formularfelder und Multipart-Overhead."""
    try:
        laenge = int(content_length or 0)
    except (TypeError, ValueError):
        return True
    return laenge > max_fotos() * max_bytes() + 1024 * 1024


def ordner(meldung_id) -> Path:
    return wurzel() / str(int(meldung_id))


def dateinamen(meldung_id) -> list[str]:
    pfad = ordner(meldung_id)
    if not pfad.is_dir():
        return []
    return sorted(p.name for p in pfad.iterdir() if NAME_MUSTER.fullmatch(p.name))


def datei_pfad(meldung_id, name) -> Path | None:
    """Sicherer Pfad einer vorhandenen Nachweis-Datei, sonst ``None`` (kein Pfad-Trick)."""
    if not NAME_MUSTER.fullmatch(str(name)):
        return None
    pfad = ordner(meldung_id) / name
    return pfad if pfad.is_file() and not pfad.is_symlink() else None


# --- Bild prüfen und neu kodieren -------------------------------------------------------------


def bild_verarbeiten(datei) -> bytes:
    """Prüft einen Upload als echtes Bild und liefert neu kodierte JPEG-Bytes ohne Metadaten.

    Dateiendung und Client-MIME zählen nicht; nur was Pillow als Bild erkennt, kommt durch.
    Neu-Kodierung entfernt EXIF (inkl. GPS), ICC, Kommentare und angehängte Fremdinhalte.
    """
    from PIL import Image, ImageOps  # noqa: PLC0415 - Pillow nur bei Upload laden

    if getattr(datei, "size", 0) > max_bytes():
        raise AblaufFehler(f"Das Foto ist zu groß (höchstens {max_bytes() // (1024 * 1024)} MB).")
    try:
        datei.seek(0)
        daten = datei.read(max_bytes() + 1)
    except (OSError, ValueError):
        raise AblaufFehler(MELDUNG_KEIN_BILD) from None
    if len(daten) > max_bytes():
        raise AblaufFehler(f"Das Foto ist zu groß (höchstens {max_bytes() // (1024 * 1024)} MB).")
    if not daten:
        raise AblaufFehler(MELDUNG_KEIN_BILD)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(daten)) as probe:
                format_ = probe.format
                breite, hoehe = probe.size
                if format_ not in ERLAUBTE_FORMATE:
                    raise AblaufFehler(
                        "Bitte ein Foto als JPEG, PNG, WebP oder HEIC senden."
                        if HEIC_MOEGLICH
                        else "Bitte ein Foto als JPEG, PNG oder WebP senden."
                    )
                if breite * hoehe > MAX_PIXEL:
                    raise AblaufFehler("Das Foto hat zu viele Pixel. Bitte ein kleineres nehmen.")
                probe.verify()
            with Image.open(io.BytesIO(daten)) as bild:
                bild.load()
                bild = ImageOps.exif_transpose(bild)  # Drehung anwenden, bevor EXIF fällt
                if bild.mode in ("RGBA", "LA", "P"):
                    bild = bild.convert("RGBA")
                    grund = Image.new("RGB", bild.size, (255, 255, 255))
                    grund.paste(bild, mask=bild.getchannel("A"))
                    bild = grund
                else:
                    bild = bild.convert("RGB")
                kante = max_kante()
                bild.thumbnail((kante, kante), Image.Resampling.LANCZOS)
                ziel = io.BytesIO()
                bild.save(ziel, "JPEG", quality=JPEG_QUALITAET, optimize=True)  # ohne exif=
    except AblaufFehler:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AblaufFehler("Das Foto hat zu viele Pixel. Bitte ein kleineres nehmen.") from None
    except Exception:  # alles, was Pillow nicht als Bild akzeptiert (kaputt, Fremdformat)
        raise AblaufFehler(MELDUNG_KEIN_BILD) from None
    return ziel.getvalue()


# --- Speichern und Löschen (Schnittstelle zu ablauf) ------------------------------------------


def _ordner_anlegen(pfad: Path) -> None:
    for teil in (pfad.parent, pfad):
        teil.mkdir(mode=0o700, exist_ok=True)
        os.chmod(teil, 0o700)


def speichern(meldung, fotos, *, neu=False) -> None:
    """Speichert Uploads zur Meldung (alles oder nichts; höchstens ``max_fotos()`` je Meldung).

    ``neu``: die Meldung entsteht gerade. Ein schon vorhandener Ordner mit ihrer ID stammt dann
    aus einer zurückgerollten Transaktion (SQLite vergibt die ID danach erneut) und gehört
    womöglich einem anderen Kind: er wird zuerst entfernt (Review AP19, B-04).
    """
    if neu:
        _ordner_entfernen(meldung.pk)
    fotos = [f for f in fotos if f]
    if not fotos:
        return
    grenze = max_fotos()
    if len(dateinamen(meldung.pk)) + len(fotos) > grenze:
        raise AblaufFehler(f"Höchstens {grenze} Fotos je Meldung.")
    bilder = [bild_verarbeiten(f) for f in fotos]  # erst alles prüfen, dann schreiben
    pfad = ordner(meldung.pk)
    _ordner_anlegen(pfad)
    geschrieben = []
    try:
        for inhalt in bilder:
            datei = pfad / f"{uuid.uuid4().hex}.jpg"
            fd = os.open(datei, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            geschrieben.append(datei)
            with os.fdopen(fd, "wb") as ausgabe:
                ausgabe.write(inhalt)
    except OSError:
        for datei in geschrieben:
            datei.unlink(missing_ok=True)
        raise AblaufFehler("Das Foto konnte nicht gespeichert werden.") from None


def _ordner_entfernen(meldung_id) -> int:
    pfad = ordner(meldung_id)
    if not pfad.is_dir():
        return 0
    anzahl = len(dateinamen(meldung_id))
    shutil.rmtree(pfad, ignore_errors=True)
    return anzahl


def loeschen(meldung) -> None:
    """Löscht die Fotos einer Meldung nach dem Commit (Rollback behält sie)."""
    meldung_id = meldung.pk
    transaction.on_commit(lambda: _ordner_entfernen(meldung_id))


def registrieren() -> None:
    from . import ablauf

    ablauf.nachweis_speicher_registrieren(speichern)
    ablauf.nachweis_loescher_registrieren(loeschen)


# --- Sicherheitsnetz (Job nachweise_aufraeumen) -----------------------------------------------


def aufraeumen(jetzt: float | None = None) -> dict:
    """Entfernt Fotos abgeschlossener Meldungen, verwaiste Ordner/Dateien und Reste von Texten.

    Idempotent. Frische Ordner (jünger als ``WAISEN_KARENZ_SEKUNDEN``) ohne Meldung bleiben
    stehen, weil ihre Transaktion noch laufen kann.
    """
    jetzt = time.time() if jetzt is None else jetzt
    ergebnis = {"abgeschlossen": 0, "verwaist": 0, "dateien": 0, "texte": 0}
    basis = wurzel()
    if basis.is_dir():
        for eintrag in sorted(basis.iterdir()):
            alt = jetzt - eintrag.stat().st_mtime > WAISEN_KARENZ_SEKUNDEN
            if not eintrag.is_dir() or eintrag.is_symlink() or not eintrag.name.isdigit():
                if alt:
                    _fremdes_entfernen(eintrag)
                    ergebnis["verwaist"] += 1
                continue
            meldung = Meldung.objects.filter(pk=int(eintrag.name)).first()
            if meldung is None:
                if alt:
                    ergebnis["dateien"] += _ordner_entfernen(eintrag.name)
                    shutil.rmtree(eintrag, ignore_errors=True)
                    ergebnis["verwaist"] += 1
            elif meldung.status not in MELDUNG_LAUFEND:
                with transaction.atomic():
                    ergebnis["dateien"] += _ordner_entfernen(meldung.pk)
                    shutil.rmtree(eintrag, ignore_errors=True)
                    audit.protokollieren(
                        "aufgabe.nachweis_geloescht",
                        akteur=None,
                        objekt=meldung,
                        kind=meldung.kind,
                        details={"quelle": "aufraeumen"},
                    )
                ergebnis["abgeschlossen"] += 1
            else:
                _unbekannte_dateien_entfernen(eintrag, jetzt)

    abgeschlossen = Meldung.objects.exclude(status__in=MELDUNG_LAUFEND).exclude(
        text="", antwort_text="", rueckfrage_text=""
    )
    for meldung in abgeschlossen:
        Meldung.objects.filter(pk=meldung.pk).update(text="", antwort_text="", rueckfrage_text="")
        ergebnis["texte"] += 1
    return ergebnis


def _fremdes_entfernen(pfad: Path) -> None:
    if pfad.is_dir() and not pfad.is_symlink():
        shutil.rmtree(pfad, ignore_errors=True)
    else:
        pfad.unlink(missing_ok=True)


def _unbekannte_dateien_entfernen(pfad: Path, jetzt: float) -> None:
    for datei in pfad.iterdir():
        if not NAME_MUSTER.fullmatch(datei.name) and jetzt - datei.stat().st_mtime > (
            WAISEN_KARENZ_SEKUNDEN
        ):
            _fremdes_entfernen(datei)
