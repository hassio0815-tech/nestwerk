"""Seiten der Lernmappe: Upload, Isolation der Geschwister, Eltern-Freigabe, Auslieferung."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.kern import einstellungen
from apps.konten.tests.conftest import angemeldet
from apps.lernen import material_ki, selectors, services
from apps.lernen import material_services as ms
from apps.lernen.models import Fach, Frage, Material, MaterialStatus, Quelle
from apps.lernen.speicher import Speicher

from . import material_hilfen as h

HOCH = "/kind/lernen/material/hochladen/"


def datei(name, inhalt, typ="application/octet-stream"):
    return SimpleUploadedFile(name, inhalt, content_type=typ)


@pytest.fixture
def kind_b_client(kind_b):
    return angemeldet(Client(), kind_b)


@pytest.fixture
def mit_fragen(kind_a, fach):
    m = ms.aufnehmen(kind_a, "heft.jpg", h.jpeg())
    Material.objects.filter(pk=m.pk).update(
        status=MaterialStatus.FRAGEN, fach=fach, text="Hund dog", thema_name="Waldwoerter"
    )
    m.refresh_from_db()
    thema = material_ki.thema_holen(kind_a, fach, "Waldwoerter")
    for f, a in (("Hund", "dog"), ("Katze", "cat")):
        services.frage_anlegen(thema, "vokabel", f, a, quelle=Quelle.KI, kind=kind_a, material=m)
    ms.status_abgleichen(m)
    return m


# --- Kind ------------------------------------------------------------------------------------


def test_mappe_zeigt_hinweis_ohne_ki(kind_client):
    r = kind_client.get("/kind/lernen/material/")
    assert r.status_code == 200
    assert "KI eingerichtet" in r.content.decode()
    assert 'enctype="multipart/form-data"' in r.content.decode()


def test_upload_und_status_sichtbar(kind_client, kind_a):
    r = kind_client.post(HOCH, {"datei": datei("mein heft.jpg", h.jpeg())})
    assert r.status_code == 302 and r["Location"].endswith("?neu=1")
    seite = kind_client.get(r["Location"]).content.decode()
    assert "mein heft.jpg" in seite and "wartet auf die KI-Einrichtung" in seite
    assert "angekommen" in seite
    assert Material.objects.get().kind == kind_a


def test_upload_mehrere_dateien(kind_client):
    r = kind_client.post(
        HOCH,
        {"datei": [datei("a.jpg", h.jpeg((1, 1, 1))), datei("b.txt", b"Hallo Welt")]},
    )
    assert r["Location"].endswith("?neu=2")
    assert Material.objects.count() == 2


def test_upload_zu_viele_dateien_auf_einmal(kind_client):
    dateien = [datei(f"d{i}.txt", f"Text {i}".encode()) for i in range(7)]
    r = kind_client.post(HOCH, {"datei": dateien})
    assert r.status_code == 400 and "höchstens 5" in r.content.decode()
    assert Material.objects.count() == 5


def test_upload_fehlermeldungen(kind_client):
    r = kind_client.post(HOCH, {})
    assert r.status_code == 400 and "wähle zuerst" in r.content.decode()
    r = kind_client.post(HOCH, {"datei": datei("virus.exe", b"MZ\x00")})
    assert r.status_code == 400 and "nicht nehmen" in r.content.decode()
    r = kind_client.post(HOCH, {"datei": datei("foto.jpg", b"kein bild")})
    assert r.status_code == 400
    einstellungen.setzen("lernen.upload_max_mb", 1, akteur=None)
    r = kind_client.post(HOCH, {"datei": datei("gross.txt", b"a" * (1024 * 1024 + 1))})
    assert r.status_code == 400 and "zu groß" in r.content.decode()
    assert not Material.objects.exists()


def test_upload_doppelt_und_gemischt(kind_client):
    kind_client.post(HOCH, {"datei": datei("a.txt", b"Hallo Welt")})
    r = kind_client.post(
        HOCH, {"datei": [datei("b.txt", b"Hallo Welt"), datei("c.txt", b"Anderer Text")]}
    )
    assert r.status_code == 400 and "schon hochgeladen" in r.content.decode()
    assert Material.objects.count() == 2  # die neue Datei kam an, die doppelte nicht


def test_upload_speicher_voll(kind_client, kind_a):
    einstellungen.setzen("lernen.speicher_limit_mb", 10, akteur=None)
    Speicher().speichern(kind_a.pk, "archiv", "alt.bin", b"x" * (10 * 1024 * 1024 - 5))
    r = kind_client.post(HOCH, {"datei": datei("neu.txt", b"viel zu viel Text")})
    assert r.status_code == 400 and "voll" in r.content.decode()


def test_upload_nur_per_post(kind_client):
    assert kind_client.get(HOCH).status_code == 405


def test_nur_kinder_und_eltern_getrennt(eltern_client, kind_client):
    assert eltern_client.post(HOCH, {"datei": datei("a.txt", b"Hallo")}).status_code != 200
    assert eltern_client.get("/kind/lernen/material/").status_code != 200
    assert kind_client.get("/eltern/lernen/material/").status_code != 200
    assert (
        kind_client.post("/eltern/lernen/material/sammel/", {"aktion": "freigeben"}).status_code
        != 302
    )
    assert not Material.objects.exists()


def test_ohne_anmeldung_umleitung():
    c = Client()
    assert c.get("/kind/lernen/material/").status_code == 302
    r = c.get("/lernen/material/1/datei/")
    assert r.status_code == 302


# --- Isolation -------------------------------------------------------------------------------


def test_geschwister_sehen_nie_material_der_anderen(kind_client, kind_b_client, kind_a):
    kind_client.post(HOCH, {"datei": datei("geheim-a.jpg", h.jpeg())})
    m = Material.objects.get()
    seite_b = kind_b_client.get("/kind/lernen/material/").content.decode()
    assert "geheim-a" not in seite_b and "Noch nichts" in seite_b
    assert kind_b_client.get(f"/kind/lernen/material/{m.pk}/").status_code == 404
    assert kind_b_client.get(f"/lernen/material/{m.pk}/datei/").status_code == 404
    assert kind_client.get(f"/kind/lernen/material/{m.pk}/").status_code == 200
    assert kind_client.get(f"/lernen/material/{m.pk}/datei/").status_code == 200


def test_geschwister_sehen_keine_fragen_der_anderen(kind_a, kind_b, mit_fragen, kind_b_client):
    ms.freigeben(mit_fragen)
    thema = mit_fragen.fragen.first().thema
    assert selectors.nutzbare_fragen(thema, kind_a).count() == 2
    assert selectors.nutzbare_fragen(thema, kind_b).count() == 0
    # auch nicht in der Auswahl auf der Übenseite
    assert "Waldwoerter" not in kind_b_client.get("/kind/lernen/").content.decode()


def test_kind_kann_nicht_loeschen_oder_freigeben(kind_client, mit_fragen):
    for pfad in ("freigeben", "loeschen", "neu", "fach", "frage_neu"):
        r = kind_client.post(f"/eltern/lernen/material/{mit_fragen.pk}/{pfad}/")
        assert r.status_code != 302 or "eltern" not in r["Location"]
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.WARTET_ELTERN
    assert mit_fragen.fragen.filter(freigabe="offen").count() == 2


# --- Auslieferung ----------------------------------------------------------------------------


def test_bild_wird_inline_und_sicher_ausgeliefert(kind_client, eltern_client):
    kind_client.post(HOCH, {"datei": datei("a.png", h.png())})
    m = Material.objects.get()
    for c in (kind_client, eltern_client):
        r = c.get(f"/lernen/material/{m.pk}/datei/")
        assert r["Content-Type"] == "image/jpeg"
        assert r["Content-Disposition"].startswith("inline")
        assert r["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in r["Cache-Control"]
        assert "sandbox" in r["Content-Security-Policy"]
        assert b"".join(r.streaming_content)[:2] == b"\xff\xd8"


def test_pdf_und_text_nur_als_download(kind_client, eltern_client):
    kind_client.post(
        HOCH, {"datei": [datei("a.pdf", h.pdf_mit_text()), datei("b.txt", b"<b>x</b> Text")]}
    )
    for m in Material.objects.all():
        r = eltern_client.get(f"/lernen/material/{m.pk}/datei/")
        assert r["Content-Disposition"].startswith("attachment")
        assert r["Content-Type"].split(";")[0] in ("application/pdf", "text/plain")
        assert 'filename="material-' in r["Content-Disposition"]  # nie der Name des Uploads
    assert "nosniff" == r["X-Content-Type-Options"]


def test_datei_fehlt_oder_unbekannter_typ(kind_client, eltern_client, kind_a):
    kind_client.post(HOCH, {"datei": datei("a.txt", b"Hallo Welt")})
    m = Material.objects.get()
    Speicher().loeschen(kind_a.pk, "inbox", m.name)
    assert eltern_client.get(f"/lernen/material/{m.pk}/datei/").status_code == 404
    assert eltern_client.get("/lernen/material/99999/datei/").status_code == 404


def test_datei_nicht_fuer_dritte_rollen(db):

    c = Client()
    assert c.get("/lernen/material/1/datei/").status_code == 302


# --- Eltern ----------------------------------------------------------------------------------


def test_eltern_liste_und_detail(eltern_client, mit_fragen):
    seite = eltern_client.get("/eltern/lernen/material/").content.decode()
    assert "Wartet auf euch" in seite and "heft.jpg" in seite and "Testkind A" in seite
    detail = eltern_client.get(f"/eltern/lernen/material/{mit_fragen.pk}/").content.decode()
    assert "Hund" in detail and "Original" in detail and "Frage von Hand anlegen" in detail
    assert eltern_client.get("/eltern/lernen/material/99999/").status_code == 404


def test_eltern_freigeben_ablehnen_gesammelt(eltern_client, mit_fragen):
    a = f"/eltern/lernen/material/{mit_fragen.pk}"
    ids = list(mit_fragen.fragen.values_list("pk", flat=True))
    r = eltern_client.post(f"{a}/freigeben/", {"frage": [ids[0]]})
    assert r.status_code == 302
    assert list(mit_fragen.fragen.filter(freigabe="freigegeben")) == [
        mit_fragen.fragen.get(pk=ids[0])
    ]
    eltern_client.post(f"{a}/ablehnen/", {"frage": [ids[1]]})
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.BEREIT
    assert eltern_client.post(f"{a}/unsinn/").status_code == 404


def test_eltern_sammel_freigabe(eltern_client, kind_a, kind_b, mit_fragen, fach):
    zweites = ms.aufnehmen(kind_b, "b.jpg", h.jpeg((5, 5, 5)))
    Material.objects.filter(pk=zweites.pk).update(
        status=MaterialStatus.FRAGEN, fach=fach, text="x", thema_name="Farben"
    )
    zweites.refresh_from_db()
    services.frage_anlegen(
        material_ki.thema_holen(kind_b, fach, "Farben"),
        "vokabel",
        "rot",
        "red",
        quelle=Quelle.KI,
        kind=kind_b,
        material=zweites,
    )
    r = eltern_client.post(
        "/eltern/lernen/material/sammel/",
        {"aktion": "freigeben", "material": [mit_fragen.pk, zweites.pk, "x"]},
    )
    assert r.status_code == 302
    assert not Frage.objects.filter(material__isnull=False, freigabe="offen").exists()
    assert eltern_client.post("/eltern/lernen/material/sammel/", {"aktion": "x"}).status_code == 404
    eltern_client.post(
        "/eltern/lernen/material/sammel/", {"aktion": "ablehnen", "material": [mit_fragen.pk]}
    )


def test_eltern_bearbeiten_und_fach(eltern_client, mit_fragen, fach):
    frage = mit_fragen.fragen.first()
    r = eltern_client.post(
        f"/eltern/lernen/material/{mit_fragen.pk}/frage/{frage.pk}/",
        {"frage": "Hund (Tier)", "antwort": "dog"},
    )
    assert r.status_code == 302
    frage.refresh_from_db()
    assert frage.frage == "Hund (Tier)"
    r = eltern_client.post(
        f"/eltern/lernen/material/{mit_fragen.pk}/frage/{frage.pk}/",
        {"frage": "<b>x</b>", "antwort": "dog"},
    )
    assert r.status_code == 400 and "ohne Links" in r.content.decode()
    zweit = Fach.objects.create(schluessel="zweitfach", name="Zweitfach")
    r = eltern_client.post(
        f"/eltern/lernen/material/{mit_fragen.pk}/fach/", {"fach": zweit.pk, "thema": "Neu"}
    )
    assert r.status_code == 302
    mit_fragen.refresh_from_db()
    assert (mit_fragen.fach, mit_fragen.thema_name) == (zweit, "Neu")
    assert (
        eltern_client.post(
            f"/eltern/lernen/material/{mit_fragen.pk}/fach/", {"fach": "x"}
        ).status_code
        == 404
    )


def test_eltern_manuelle_frage_und_fehler(eltern_client, mit_fragen):
    a = f"/eltern/lernen/material/{mit_fragen.pk}/frage_neu/"
    r = eltern_client.post(a, {"typ": "frage", "frage": "Was bellt?", "antwort": "Hund"})
    assert r.status_code == 302
    assert mit_fragen.fragen.filter(quelle="eltern", freigabe="freigegeben").count() == 1
    r = eltern_client.post(a, {"typ": "frage", "frage": "", "antwort": "Hund"})
    assert r.status_code == 400


def test_eltern_neu_versuchen(eltern_client, kind_a):
    m = ms.aufnehmen(kind_a, "a.txt", b"Hallo Welt")
    ms.fehler_setzen(m, "ausgabe")
    r = eltern_client.post(f"/eltern/lernen/material/{m.pk}/neu/")
    assert r.status_code == 302
    m.refresh_from_db()
    assert m.status == MaterialStatus.WARTET_KI and m.durchgang == 2
    r = eltern_client.post(f"/eltern/lernen/material/{m.pk}/neu/")  # wartet ja nur auf die KI
    assert r.status_code == 302
    ms.fehler_setzen(m, "typ")
    r = eltern_client.post(f"/eltern/lernen/material/{m.pk}/neu/")
    assert r.status_code == 400


def test_eltern_loeschen(eltern_client, mit_fragen, kind_a):
    name = mit_fragen.name
    r = eltern_client.post(f"/eltern/lernen/material/{mit_fragen.pk}/loeschen/")
    assert r.status_code == 302 and r["Location"].endswith("/eltern/lernen/material/")
    assert not Material.objects.exists() and not Frage.objects.filter(kind=kind_a).exists()
    assert not (Speicher().ordner(kind_a.pk, "inbox") / name).exists()
    # Löschen nur per POST
    assert (
        eltern_client.get(f"/eltern/lernen/material/{mit_fragen.pk}/loeschen/").status_code == 405
    )


def test_eltern_regel_je_kind(eltern_client, kind_a, kind_b):
    r = eltern_client.post("/eltern/lernen/material/regel/", {"kind": kind_a.pk, "sofort": "1"})
    assert r.status_code == 302
    assert ms.sofort_nutzbar(kind_a) and not ms.sofort_nutzbar(kind_b)
    seite = eltern_client.get("/eltern/lernen/material/").content.decode()
    assert "sofort nutzbar" in seite and "Speicher:" in seite
    assert (
        eltern_client.post("/eltern/lernen/material/regel/", {"kind": "kein-uuid"}).status_code
        == 404
    )


# --- Üben mit freigegebenen Fragen -----------------------------------------------------------


def test_nur_freigegebene_fragen_erscheinen_im_ueben(
    kind_client, eltern_client, kind_a, mit_fragen
):
    start = kind_client.get("/kind/lernen/").content.decode()
    assert "Waldwoerter" not in start  # noch nichts freigegeben
    eltern_client.post(f"/eltern/lernen/material/{mit_fragen.pk}/freigeben/")
    start = kind_client.get("/kind/lernen/").content.decode()
    assert "Waldwoerter" in start


def test_frage_typ_frage_wird_geprueft(kind_a, fach):
    thema = material_ki.thema_holen(kind_a, fach, "Allgemein")
    services.frage_anlegen(
        thema, "frage", "Hauptstadt von Frankreich?", "Paris", quelle=Quelle.ELTERN, kind=kind_a
    )
    sitzung = services.sitzung_starten(kind_a, fach, thema=thema)
    aufgabe = services.frage_stellen(sitzung)
    assert aufgabe is not None
    rueck = services.antworten(sitzung, "paris")
    assert rueck.ergebnis == "richtig"
