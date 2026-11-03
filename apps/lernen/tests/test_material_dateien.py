"""Dateiprüfung: Typ am Inhalt, Größe, Namen, Bilder neu kodiert, PDF-Text (SPEC 21.5)."""

import io

import pytest
from PIL import Image

from apps.lernen import material_dateien as md
from apps.lernen.material_dateien import UploadFehler

from . import material_hilfen as h

MB = 1024 * 1024


def test_jpeg_wird_neu_kodiert_ohne_exif():
    bild = Image.new("RGB", (40, 30), (1, 2, 3))
    exif = Image.Exif()
    exif[0x010F] = "GeheimeKamera"
    ziel = io.BytesIO()
    bild.save(ziel, "JPEG", exif=exif)
    assert b"GeheimeKamera" in ziel.getvalue()
    ergebnis = md.pruefen("foto.JPG", ziel.getvalue(), MB)
    assert (ergebnis.art, ergebnis.ext, ergebnis.mime) == ("bild", "jpg", "image/jpeg")
    assert b"GeheimeKamera" not in ergebnis.daten
    with Image.open(io.BytesIO(ergebnis.daten)) as neu:
        assert neu.format == "JPEG"


def test_png_und_webp_werden_jpeg():
    assert md.pruefen("a.png", h.png(), MB).ext == "jpg"
    assert md.pruefen("a.webp", h.jpeg(format_="WEBP"), MB).ext == "jpg"


def test_transparentes_png_bekommt_weissen_grund():
    ziel = io.BytesIO()
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(ziel, "PNG")
    ergebnis = md.pruefen("a.png", ziel.getvalue(), MB)
    with Image.open(io.BytesIO(ergebnis.daten)) as neu:
        assert neu.getpixel((1, 1))[0] > 240


def test_grosses_bild_wird_verkleinert():
    gross = h.jpeg(groesse=(md.MAX_KANTE + 500, 100))
    ergebnis = md.pruefen("a.jpg", gross, 10 * MB)
    with Image.open(io.BytesIO(ergebnis.daten)) as neu:
        assert max(neu.size) <= md.MAX_KANTE


def test_heic_wenn_bibliothek_da():
    import pillow_heif

    heif = pillow_heif.from_pillow(Image.new("RGB", (16, 16), (9, 9, 9)))
    ziel = io.BytesIO()
    heif.save(ziel, format="HEIF")
    assert md.HEIC_MOEGLICH
    assert "heic" in md.erlaubte_endungen()
    assert md.pruefen("iphone.heic", ziel.getvalue(), MB).ext == "jpg"


def test_pdf_und_text_bleiben_unveraendert():
    pdf = h.pdf_mit_text()
    ergebnis = md.pruefen("blatt.pdf", pdf, MB)
    assert (ergebnis.art, ergebnis.ext, ergebnis.mime, ergebnis.daten) == (
        "dokument",
        "pdf",
        "application/pdf",
        pdf,
    )
    text = b"Hallo Welt\nZweite Zeile"
    ergebnis = md.pruefen("notiz.txt", text, MB)
    assert (ergebnis.ext, ergebnis.mime, ergebnis.daten) == ("txt", "text/plain", text)


def test_text_in_windows_kodierung():
    assert md.pruefen("a.txt", "Größe der Äpfel".encode("cp1252"), MB).ext == "txt"
    assert "Größe" in md.text_aus_datei("txt", "Größe der Äpfel".encode("cp1252"))


@pytest.mark.parametrize(
    "name",
    [
        "virus.exe",
        "skript.sh",
        "seite.html",
        "bild.gif",
        "noname",
        "",
        "x.docx",
        "x.pptx",
        ".htaccess",
    ],
)
def test_falsche_endung_wird_abgelehnt(name):
    with pytest.raises(UploadFehler):
        md.pruefen(name, b"Hallo", MB)


def test_endung_stimmt_aber_inhalt_nicht():
    with pytest.raises(UploadFehler):
        md.pruefen("foto.jpg", b"MZ\x90\x00\x03\x00\x00\x00 programm", MB)
    with pytest.raises(UploadFehler):
        md.pruefen("foto.png", b"das ist nur Text", MB)  # Text, aber als Bild ausgegeben
    with pytest.raises(UploadFehler):
        md.pruefen("blatt.pdf", b"%PDF-1.4 kaputt", MB)
    with pytest.raises(UploadFehler):
        md.pruefen("a.txt", b"\x00\x01\x02\x03 binaer", MB)
    with pytest.raises(UploadFehler):
        md.pruefen("a.txt", b"   \n  ", MB)  # nur Leerraum
    with pytest.raises(UploadFehler):
        md.pruefen("a.txt", b"\x01\x02\x03\x04\x05\x06\x07\x08 Text", MB)  # Steuerzeichen


def test_getarnte_datei_wird_nach_inhalt_erkannt():
    # Ein PNG mit .txt-Endung ist ein gültiges Bild und wird als solches gespeichert
    ergebnis = md.pruefen("tarnung.txt", h.png(), MB)
    assert ergebnis.art == "bild"
    # Eine PDF-Datei mit .jpg-Endung ist ein PDF
    assert md.pruefen("tarnung.jpg", h.pdf_mit_text(), MB).ext == "pdf"


def test_leer_und_zu_gross():
    with pytest.raises(UploadFehler, match="leer"):
        md.pruefen("a.txt", b"", MB)
    with pytest.raises(UploadFehler, match="zu groß"):
        md.pruefen("a.txt", b"x" * (MB + 1), MB)


def test_zu_viele_pixel(monkeypatch):
    monkeypatch.setattr(md, "MAX_PIXEL", 100)
    with pytest.raises(UploadFehler, match="Pixel"):
        md.pruefen("a.png", h.png(), MB)


def test_geschuetztes_und_langes_pdf(monkeypatch):
    from pypdf import PdfReader, PdfWriter

    leser = PdfReader(io.BytesIO(h.pdf_mit_text()))
    schreiber = PdfWriter()
    schreiber.append(leser)
    schreiber.encrypt("geheim")
    ziel = io.BytesIO()
    schreiber.write(ziel)
    with pytest.raises(UploadFehler, match="geschützt"):
        md.pruefen("zu.pdf", ziel.getvalue(), MB)
    monkeypatch.setattr(md, "MAX_SEITEN", 0)
    with pytest.raises(UploadFehler, match="zu viele Seiten"):
        md.pruefen("lang.pdf", h.pdf_mit_text(), MB)


def test_pdf_ohne_seiten_wird_abgelehnt():
    from pypdf import PdfWriter

    ziel = io.BytesIO()
    PdfWriter().write(ziel)
    with pytest.raises(UploadFehler):
        md.pruefen("leer.pdf", ziel.getvalue(), MB)


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Windows\\evil.exe", "evil.exe"),
        ("a/b/c.jpg", "c.jpg"),
        ("na\x00me\n.jpg", "name.jpg"),
        ("<script>alert(1)</script>.jpg", "script.jpg"),
        ("...", "Datei"),
        ("", "Datei"),
        (None, "Datei"),
        ("Übung 3 (neu).pdf", "Übung 3 (neu).pdf"),
    ],
)
def test_anzeigename_wird_neutralisiert(roh, erwartet):
    assert md.anzeigename_bereinigen(roh) == erwartet


def test_anzeigename_wird_gekuerzt():
    assert len(md.anzeigename_bereinigen("a" * 500 + ".jpg")) <= md.ANZEIGENAME_MAX


def test_text_aus_datei():
    assert md.text_aus_datei("jpg", b"egal") == ""
    assert md.text_aus_datei("pdf", h.pdf_mit_text()).startswith("Hund heißt dog")
    assert md.text_aus_datei("pdf", h.pdf_mit_text("kurz")) == ""  # zu wenig: wie ein Scan
    assert md.text_aus_datei("pdf", b"%PDF-kaputt") == ""
    assert md.pdf_bilder(b"%PDF-kaputt") == []
    lang = "wort " * 10_000
    assert len(md.text_bereinigen(lang)) == md.MAX_TEXT_ZEICHEN


def test_pdf_scan_liefert_bilder():
    bilder = md.pdf_bilder(h.pdf_mit_bild())
    assert len(bilder) == 1
    with Image.open(io.BytesIO(bilder[0])) as bild:
        assert bild.format == "JPEG"
    assert md.pdf_bilder(h.pdf_mit_bild(), maximal=0) == []


def test_text_bereinigen_entfernt_steuerzeichen():
    assert md.text_bereinigen("a\x00b\r\nc\r\r\r\r\rd") == "ab\nc\n\nd"
