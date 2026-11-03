"""Erfundene Testdateien für die Material-Pipeline (keine echten Fotos, keine echten Inhalte)."""

import io
import json

from PIL import Image


def jpeg(farbe=(200, 30, 30), groesse=(64, 48), format_="JPEG"):
    ziel = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(ziel, format_)
    return ziel.getvalue()


def png(farbe=(10, 200, 10)):
    return jpeg(farbe, format_="PNG")


def pdf_mit_text(text="Hund heißt dog und Katze heißt cat. " * 3):
    inhalt = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1", "replace")
    teile = [
        b"%PDF-1.4\n",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 600 200]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
        b"4 0 obj<</Length %d>>stream\n" % len(inhalt) + inhalt + b"\nendstream endobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    return _pdf_abschliessen(teile)


def pdf_mit_bild(bild=None):
    """Ein Scan: eine Seite ohne Text, nur ein eingebettetes JPEG."""
    bild = bild or jpeg()
    inhalt = b"q 200 0 0 150 0 0 cm /Im0 Do Q"
    teile = [
        b"%PDF-1.4\n",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 150]/Contents 4 0 R"
        b"/Resources<</XObject<</Im0 5 0 R>>>>>>endobj\n",
        b"4 0 obj<</Length %d>>stream\n" % len(inhalt) + inhalt + b"\nendstream endobj\n",
        b"5 0 obj<</Type/XObject/Subtype/Image/Width 64/Height 48/ColorSpace/DeviceRGB"
        b"/BitsPerComponent 8/Filter/DCTDecode/Length %d>>stream\n"
        % len(bild)
        + bild
        + b"\nendstream endobj\n",
    ]
    return _pdf_abschliessen(teile)


def _pdf_abschliessen(teile):
    koerper = b"".join(teile)
    offsets, pos = [], 0
    for teil in teile[1:]:
        pos_vorher = len(teile[0]) + sum(len(t) for t in teile[1 : 1 + len(offsets)])
        offsets.append(pos_vorher)
        pos += len(teil)
    xref_pos = len(koerper)
    tabelle = b"xref\n0 %d\n0000000000 65535 f \n" % (len(offsets) + 1)
    tabelle += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    ende = b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(offsets) + 1,
        xref_pos,
    )
    return koerper + tabelle + ende


def antwort_openai(inhalt):
    """Antwort im Format des OpenAI-kompatiblen Adapters (Fake-Transport)."""
    text = inhalt if isinstance(inhalt, str) else json.dumps(inhalt)
    return 200, {"choices": [{"message": {"content": text}}], "usage": {}}


def auslesen_json(fach="testsprache", thema="Tiere", klasse=5, konfidenz=0.9, text="Hund dog"):
    return {
        "text": text,
        "fach": fach,
        "thema": thema,
        "klassenstufe": klasse,
        "konfidenz": konfidenz,
    }


def fragen_json(*paare, typ="vokabel"):
    return {"fragen": [{"typ": typ, "frage": f, "antwort": a} for f, a in paare]}
