"""Prüfen und Lesen hochgeladener Dateien (SPEC 21.5). Reine Hilfsfunktionen ohne Datenbank.

- Der Typ wird am **Inhalt** erkannt (Magic Bytes, Pillow, pypdf), die Endung muss zusätzlich
  auf der Liste stehen. Gespeichert wird nie unter dem Namen des Uploads.
- Bilder werden neu zu JPEG kodiert (entfernt EXIF mit GPS und angehängte Fremdinhalte),
  PDFs und Texte bleiben unverändert; ausgeliefert wird nur mit festem Typ und ``nosniff``.
- PDF-Text wird ohne KI gelesen (``pypdf``); nur Scans ohne Text brauchen später die Bilderkennung.
- Alles, was von außen kommt, ist unvertrauenswürdig: Größen, Seitenzahlen und Pixel sind begrenzt,
  Fehler eines Parsers werden zu einer freundlichen Meldung.
"""

import io
import re
import unicodedata
import warnings
from dataclasses import dataclass, field

from django.utils.translation import gettext as _

MAX_PIXEL = 40_000_000
MAX_KANTE = 2000
JPEG_QUALITAET = 85
MAX_SEITEN = 40
MAX_TEXT_ZEICHEN = 20_000
MIN_PDF_TEXT = 40  # weniger Zeichen = vermutlich ein Scan
MAX_PDF_BILDER = 3
ANZEIGENAME_MAX = 60

ENDUNGEN = {
    "jpg": "bild",
    "jpeg": "bild",
    "png": "bild",
    "webp": "bild",
    "heic": "bild",
    "heif": "bild",
    "pdf": "pdf",
    "txt": "text",
}
BILD_FORMATE = {"JPEG", "PNG", "WEBP", "HEIF"}

try:  # HEIC (iPhone) braucht pillow-heif; ohne die Bibliothek bleibt es aus
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_MOEGLICH = True
except ImportError:  # pragma: no cover - pillow-heif ist Abhängigkeit
    HEIC_MOEGLICH = False

_STEUER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NAME_OK = re.compile(r"[^\w .()\-]", re.UNICODE)


class UploadFehler(ValueError):
    """Die Datei wird nicht angenommen; ``str(fehler)`` ist ein kindgerechter Hinweis."""


@dataclass(frozen=True)
class Geprueft:
    art: str  # "bild" oder "dokument"
    ext: str  # Endung der gespeicherten Datei
    mime: str  # fester Typ für die Auslieferung
    daten: bytes = field(repr=False)  # so wird gespeichert (Bilder: neu kodiert)
    anzeigename: str = ""


def anzeigename_bereinigen(name):
    """Reiner Name zur Anzeige: kein Pfad, keine Steuerzeichen, nur harmlose Zeichen."""
    name = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFC", name)
    name = _NAME_OK.sub("", _STEUER.sub("", name)).strip(" .")
    return name[:ANZEIGENAME_MAX] or _("Datei")


def endung(name):
    name = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return name.rpartition(".")[2].lower() if "." in name else ""


def erlaubte_endungen():
    return sorted(e for e in ENDUNGEN if HEIC_MOEGLICH or e not in ("heic", "heif"))


def _kein_typ():
    return UploadFehler(
        _(
            "Diese Datei können wir nicht nehmen. "
            "Erlaubt sind Fotos (JPEG, PNG, WebP), PDF und Text."
        )
    )


def _zu_gross(max_bytes):
    return UploadFehler(
        _("Die Datei ist zu groß (höchstens %(mb)s MB).") % {"mb": max_bytes // (1024 * 1024)}
    )


def pruefen(name, daten, max_bytes):
    """Prüft eine Datei und gibt ``Geprueft`` zurück, sonst ``UploadFehler``."""
    ext = endung(name)
    erwartet = ENDUNGEN.get(ext)
    if erwartet is None or (not HEIC_MOEGLICH and ext in ("heic", "heif")):
        raise _kein_typ()
    if not daten:
        raise UploadFehler(_("Die Datei ist leer."))
    if len(daten) > max_bytes:
        raise _zu_gross(max_bytes)
    anzeige = anzeigename_bereinigen(name)
    if daten.startswith(b"%PDF-"):
        _pdf_pruefen(daten)
        return Geprueft("dokument", "pdf", "application/pdf", daten, anzeige)
    bild = _bild_kodieren(daten)
    if bild is not None:
        return Geprueft("bild", "jpg", "image/jpeg", bild, anzeige)
    text = _text_dekodieren(daten)
    if text is not None:
        if erwartet != "text":
            raise _kein_typ()
        return Geprueft("dokument", "txt", "text/plain", daten, anzeige)
    raise _kein_typ()


# --- Bild ------------------------------------------------------------------------------------


def _bild_kodieren(daten):
    """JPEG-Bytes ohne Metadaten oder ``None``, wenn Pillow die Daten nicht als erlaubtes Bild
    kennt. Zu viele Pixel: ``UploadFehler``."""
    from PIL import Image, ImageOps  # noqa: PLC0415 - Pillow nur bei Bedarf laden

    zu_viele = UploadFehler(_("Das Foto hat zu viele Pixel. Bitte nimm ein kleineres."))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(daten)) as probe:
                if probe.format not in BILD_FORMATE:
                    return None
                if probe.size[0] * probe.size[1] > MAX_PIXEL:
                    raise zu_viele
                probe.verify()
            with Image.open(io.BytesIO(daten)) as bild:
                bild.load()
                bild = ImageOps.exif_transpose(bild)
                if bild.mode in ("RGBA", "LA", "P"):
                    bild = bild.convert("RGBA")
                    grund = Image.new("RGB", bild.size, (255, 255, 255))
                    grund.paste(bild, mask=bild.getchannel("A"))
                    bild = grund
                else:
                    bild = bild.convert("RGB")
                bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.Resampling.LANCZOS)
                ziel = io.BytesIO()
                bild.save(ziel, "JPEG", quality=JPEG_QUALITAET, optimize=True)
    except UploadFehler:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise zu_viele from None
    except Exception:  # kaputt oder kein Bild
        return None
    return ziel.getvalue()


# --- Text ------------------------------------------------------------------------------------


def _text_dekodieren(daten):
    """Text oder ``None``, wenn es offenbar kein Text ist (NUL-Bytes, viele Steuerzeichen)."""
    if b"\x00" in daten:
        return None
    for kodierung in ("utf-8-sig", "cp1252"):
        try:
            text = daten.decode(kodierung)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 kennt nicht jedes Byte; Rest als latin-1
        text = daten.decode("latin-1")
    if not text.strip():
        return None
    if len(_STEUER.findall(text)) > max(2, len(text) // 100):
        return None
    return text


def text_bereinigen(text):
    """Entfernt Steuerzeichen, vereinheitlicht Zeilenenden und kürzt auf ``MAX_TEXT_ZEICHEN``."""
    text = _STEUER.sub("", str(text or "")).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_TEXT_ZEICHEN]


# --- PDF -------------------------------------------------------------------------------------


def _pdf_leser(daten):
    from pypdf import PdfReader  # noqa: PLC0415

    leser = PdfReader(io.BytesIO(daten))
    if leser.is_encrypted:
        raise UploadFehler(_("Dieses PDF ist geschützt. Bitte nimm ein anderes."))
    return leser


def _pdf_pruefen(daten):
    try:
        leser = _pdf_leser(daten)
        seiten = len(leser.pages)
    except UploadFehler:
        raise
    except Exception:
        raise _kein_typ() from None
    if seiten < 1:
        raise _kein_typ()
    if seiten > MAX_SEITEN:
        raise UploadFehler(_("Das PDF hat zu viele Seiten (höchstens %(n)s).") % {"n": MAX_SEITEN})


def pdf_text(daten):
    """Text eines PDFs ohne KI (leer bei Scans oder Fehlern)."""
    teile, laenge = [], 0
    try:
        for seite in _pdf_leser(daten).pages[:MAX_SEITEN]:
            teil = seite.extract_text() or ""
            teile.append(teil)
            laenge += len(teil)
            if laenge >= MAX_TEXT_ZEICHEN:
                break
    except Exception:
        return ""
    return text_bereinigen("\n".join(teile))


def pdf_bilder(daten, maximal=MAX_PDF_BILDER):
    """Eingebettete Bilder (Scans) als geprüfte JPEG-Bytes, höchstens ``maximal`` Stück."""
    ergebnis = []
    try:
        for seite in _pdf_leser(daten).pages[:MAX_SEITEN]:
            for bild in seite.images:
                if len(ergebnis) >= maximal:
                    return ergebnis
                jpeg = _bild_kodieren(bild.data)
                if jpeg:
                    ergebnis.append(jpeg)
    except Exception:
        return ergebnis
    return ergebnis


def text_aus_datei(ext, daten):
    """Lesbarer Text einer ``txt``- oder ``pdf``-Datei, sonst leer (Bilder gehen zur KI)."""
    if ext == "txt":
        return text_bereinigen(_text_dekodieren(daten) or "")
    if ext == "pdf":
        text = pdf_text(daten)
        return text if len(text) >= MIN_PDF_TEXT else ""
    return ""
