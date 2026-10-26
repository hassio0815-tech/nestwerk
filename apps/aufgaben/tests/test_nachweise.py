"""Nachweis-Fotos (AP13): Validierung, EXIF, Löschung, Auslieferung, Aufräum-Job."""

import io
import os
import stat

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.aufgaben import ablauf, nachweise, services, wiederholung
from apps.aufgaben.models import (
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    Meldung,
    MeldungStatus,
)
from apps.kern.models import AuditEintrag
from apps.konten.tests.conftest import angemeldet


@pytest.fixture(autouse=True)
def nachweis_dir(settings, tmp_path):
    settings.NACHWEIS_DIR = tmp_path / "nachweise"
    return settings.NACHWEIS_DIR


def jpeg(groesse=(3200, 2400), gps=True, format_="JPEG"):
    bild = Image.new("RGB", groesse, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "Kamerahersteller"
    if gps:
        ifd = exif.get_ifd(0x8825)
        ifd[1] = "N"
        ifd[2] = (48.0, 8.0, 0.0)
        ifd[3] = "E"
        ifd[4] = (11.0, 34.0, 0.0)
    puffer = io.BytesIO()
    if format_ == "JPEG":
        bild.save(puffer, "JPEG", exif=exif)
    else:
        bild.save(puffer, format_)
    return puffer.getvalue()


def upload(inhalt, name="foto.jpg", typ="image/jpeg"):
    return SimpleUploadedFile(name, inhalt, content_type=typ)


@pytest.fixture
def instanz(mama):
    aufgabe = Aufgabe.objects.create(
        titel="Zimmer",
        punkte=10,
        erstellt_von=mama,
        freigabeart="nachweis",
        wiederholungsart=wiederholung.EINMALIG,
    )
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        titel_snapshot="Zimmer",
        punkte_snapshot=10,
        freigabeart_snapshot="nachweis",
    )


@pytest.fixture
def gemeldet(instanz, anna):
    services.interesse_zeigen(instanz, anna)
    services.erledigt_melden(instanz, anna, text="fertig", fotos=[upload(jpeg())])
    return Meldung.objects.get(instanz=instanz)


def test_bild_ohne_exif_und_max_1600():
    quelle = jpeg()
    assert Image.open(io.BytesIO(quelle)).getexif().get_ifd(0x8825)  # Testbild hat GPS
    daten = nachweise.bild_verarbeiten(upload(quelle))
    ergebnis = Image.open(io.BytesIO(daten))
    assert ergebnis.format == "JPEG"
    assert max(ergebnis.size) == 1600
    assert not dict(ergebnis.getexif())
    assert not ergebnis.getexif().get_ifd(0x8825)
    assert b"Exif" not in daten and b"Kamerahersteller" not in daten


@pytest.mark.parametrize("format_", ["PNG", "WEBP"])
def test_png_und_webp_erlaubt(format_):
    daten = nachweise.bild_verarbeiten(upload(jpeg((100, 80), gps=False, format_=format_)))
    assert Image.open(io.BytesIO(daten)).format == "JPEG"


def test_heic_erlaubt():
    pillow_heif = pytest.importorskip("pillow_heif")
    puffer = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (64, 64), "blue")).save(puffer, format="HEIF")
    daten = nachweise.bild_verarbeiten(upload(puffer.getvalue(), "x.heic", "image/heic"))
    assert Image.open(io.BytesIO(daten)).size == (64, 64)


def test_umbenannte_pdf_und_polyglot_abgewiesen():
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    with pytest.raises(services.AblaufFehler):
        nachweise.bild_verarbeiten(upload(pdf, "foto.jpg", "image/jpeg"))
    with pytest.raises(services.AblaufFehler):
        nachweise.bild_verarbeiten(upload(b"GIF89a" + b"\x00" * 20, "x.jpg"))
    with pytest.raises(services.AblaufFehler):
        nachweise.bild_verarbeiten(upload(b"", "leer.jpg"))
    # JPEG mit angehängtem Skript: wird neu kodiert, der Anhang ist weg
    daten = nachweise.bild_verarbeiten(upload(jpeg((50, 50)) + b"<script>alert(1)</script>"))
    assert b"<script>" not in daten


def test_zu_gross_abgewiesen(monkeypatch):
    monkeypatch.setattr(nachweise, "max_bytes", lambda: 1000)
    with pytest.raises(services.AblaufFehler, match="zu groß"):
        nachweise.bild_verarbeiten(upload(jpeg((400, 400), gps=False)))


@pytest.mark.django_db
def test_groesse_und_anzahl_sind_familienwerte():
    """Regression B-09: vorher Django-Setting bzw. Konstante (nicht im Dashboard änderbar)."""
    from apps.kern import einstellungen

    assert nachweise.max_bytes() == 15 * 1024 * 1024 and nachweise.max_fotos() == 3
    einstellungen.setzen("aufgaben.nachweis_max_upload_mb", 2, akteur=None)
    einstellungen.setzen("aufgaben.nachweis_max_anzahl", 1, akteur=None)
    assert nachweise.max_bytes() == 2 * 1024 * 1024 and nachweise.max_fotos() == 1
    assert not nachweise.anfrage_zu_gross(str(3 * 1024 * 1024 - 1))
    assert nachweise.anfrage_zu_gross(str(3 * 1024 * 1024 + 1))
    assert nachweise.anfrage_zu_gross("kaputt")
    assert not nachweise.anfrage_zu_gross("")


def test_zu_viele_pixel_abgewiesen(monkeypatch):
    monkeypatch.setattr(nachweise, "MAX_PIXEL", 1000)
    with pytest.raises(services.AblaufFehler, match="Pixel"):
        nachweise.bild_verarbeiten(upload(jpeg((100, 100), gps=False)))


def test_speichern_privat_und_zufaelliger_name(gemeldet, nachweis_dir):
    namen = nachweise.dateinamen(gemeldet.pk)
    assert len(namen) == 1 and nachweise.NAME_MUSTER.fullmatch(namen[0])
    pfad = nachweis_dir / str(gemeldet.pk) / namen[0]
    assert stat.S_IMODE(pfad.stat().st_mode) == 0o600
    assert stat.S_IMODE(pfad.parent.stat().st_mode) == 0o700


def test_max_drei_fotos(instanz, anna):
    services.interesse_zeigen(instanz, anna)
    with pytest.raises(services.AblaufFehler, match="Höchstens"):
        services.erledigt_melden(instanz, anna, fotos=[upload(jpeg((50, 50))) for _ in range(4)])


def test_fehler_beim_zweiten_foto_speichert_nichts(instanz, anna, nachweis_dir):
    services.interesse_zeigen(instanz, anna)
    with pytest.raises(services.AblaufFehler):
        services.erledigt_melden(
            instanz, anna, fotos=[upload(jpeg((50, 50))), upload(b"kein bild")]
        )
    assert not any(nachweis_dir.glob("*/*")) if nachweis_dir.exists() else True


def test_bestaetigen_loescht_datei_sofort_und_audit_ohne_inhalt(
    gemeldet, mama, django_capture_on_commit_callbacks
):
    instanz = gemeldet.instanz
    assert nachweise.dateinamen(gemeldet.pk)
    with django_capture_on_commit_callbacks(execute=True):
        services.bestaetigen(instanz, von=mama)
    assert nachweise.dateinamen(gemeldet.pk) == []
    assert not nachweise.ordner(gemeldet.pk).exists()
    gemeldet.refresh_from_db()
    assert gemeldet.text == "" and gemeldet.nachweis_geloescht_am is not None
    eintrag = AuditEintrag.objects.filter(aktion="aufgabe.nachweis_geloescht").get()
    assert "fertig" not in str(eintrag.details) and ".jpg" not in str(eintrag.details)


def test_rueckfrage_behaelt_nachweis_ablehnen_loescht(
    gemeldet, mama, django_capture_on_commit_callbacks
):
    instanz = gemeldet.instanz
    with django_capture_on_commit_callbacks(execute=True):
        services.rueckfrage_stellen(instanz, von=mama, text="Was genau?")
    assert len(nachweise.dateinamen(gemeldet.pk)) == 1
    with django_capture_on_commit_callbacks(execute=True):
        services.ablehnen(instanz, von=mama, begruendung="nein")
    assert nachweise.dateinamen(gemeldet.pk) == []


def test_rollback_behaelt_datei_nicht_nach_loeschen(gemeldet, django_capture_on_commit_callbacks):
    from django.db import transaction

    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                nachweise.loeschen(gemeldet)
                raise RuntimeError
        except RuntimeError:
            pass
    assert len(nachweise.dateinamen(gemeldet.pk)) == 1


def test_auslieferung_rechte(gemeldet, anna, ben, mama, nachweis_dir):
    name = nachweise.dateinamen(gemeldet.pk)[0]
    url = reverse("aufgaben:nachweis_bild", args=[gemeldet.pk, name])

    anonym = Client().get(url)
    assert anonym.status_code == 302

    fremd = Client()
    angemeldet(fremd, ben)
    assert fremd.get(url).status_code == 403

    eigen = Client()
    angemeldet(eigen, anna)
    antwort = eigen.get(url)
    assert antwort.status_code == 200
    assert "no-store" in antwort["Cache-Control"]
    assert antwort["Content-Type"] == "image/jpeg"
    b"".join(antwort.streaming_content)  # wie der Client: Datei schließen, DB offen lassen

    eltern = Client()
    angemeldet(eltern, mama)
    antwort = eltern.get(url)
    assert antwort.status_code == 200 and "no-store" in antwort["Cache-Control"]
    b"".join(antwort.streaming_content)  # wie der Client: Datei schließen, DB offen lassen
    for schlecht in ("..%2Fx.jpg", "x.jpg", "a" * 32 + ".jpg"):
        assert eltern.get(url.rsplit("/", 2)[0] + f"/{schlecht}/").status_code == 404


def test_kind_sieht_nach_abschluss_nichts(gemeldet, anna, mama):
    name = nachweise.dateinamen(gemeldet.pk)[0]
    url = reverse("aufgaben:nachweis_bild", args=[gemeldet.pk, name])
    Meldung.objects.filter(pk=gemeldet.pk).update(status=MeldungStatus.BESTAETIGT)
    kind = Client()
    angemeldet(kind, anna)
    assert kind.get(url).status_code == 403


def test_upload_per_view_und_eltern_sehen_foto(instanz, anna, mama):
    services.interesse_zeigen(instanz, anna)
    kind = Client()
    angemeldet(kind, anna)
    antwort = kind.post(
        reverse("aufgaben:kind_melden", args=[instanz.pk]),
        {"text": "fertig", "foto": upload(jpeg((800, 600)))},
    )
    assert antwort.status_code == 200
    instanz.refresh_from_db()
    assert instanz.status == InstanzStatus.GEMELDET
    meldung = Meldung.objects.get(instanz=instanz)
    assert len(nachweise.dateinamen(meldung.pk)) == 1
    eltern = Client()
    angemeldet(eltern, mama)
    seite = eltern.get(reverse("aufgaben:entscheidungen")).content.decode()
    assert nachweise.dateinamen(meldung.pk)[0] in seite


def test_upload_nicht_bild_per_view_hinweis(instanz, anna):
    services.interesse_zeigen(instanz, anna)
    kind = Client()
    angemeldet(kind, anna)
    antwort = kind.post(
        reverse("aufgaben:kind_melden", args=[instanz.pk]),
        {"text": "x", "foto": upload(b"%PDF-1.4 hallo", "x.jpg")},
    )
    assert "kein Foto" in antwort.content.decode()
    instanz.refresh_from_db()
    assert instanz.status == InstanzStatus.RESERVIERT


def test_aufraeumen_idempotent(gemeldet, mama, nachweis_dir):
    jetzt = 4_000_000_000.0  # weit in der Zukunft: Karenz abgelaufen
    # Waise (Meldung existiert nicht) und Fremddatei
    waise = nachweis_dir / "999999"
    waise.mkdir()
    (waise / ("a" * 32 + ".jpg")).write_bytes(b"x")
    (nachweis_dir / "stray.txt").write_text("x")
    # abgeschlossene Meldung, Datei noch da (Sicherheitsnetz)
    Meldung.objects.filter(pk=gemeldet.pk).update(status=MeldungStatus.BESTAETIGT)
    erstes = nachweise.aufraeumen(jetzt)
    assert erstes["abgeschlossen"] == 1 and erstes["verwaist"] == 2 and erstes["texte"] == 1
    assert list(nachweis_dir.iterdir()) == []
    gemeldet.refresh_from_db()
    assert gemeldet.text == ""
    zweites = nachweise.aufraeumen(jetzt)
    assert zweites == {"abgeschlossen": 0, "verwaist": 0, "dateien": 0, "texte": 0}


def test_aufraeumen_schont_frische_waisen_und_offene(gemeldet, nachweis_dir):
    frisch = nachweis_dir / "999999"
    frisch.mkdir()
    ergebnis = nachweise.aufraeumen()
    assert frisch.exists() and ergebnis["verwaist"] == 0
    assert len(nachweise.dateinamen(gemeldet.pk)) == 1


def test_job_command(gemeldet, db):
    from django.core.management import call_command

    call_command("nachweise_aufraeumen")
    from apps.kern.models import JobLauf

    assert JobLauf.objects.filter(name="nachweise_aufraeumen", status="ok").exists()


def test_backup_erfasst_keine_nachweise():
    from pathlib import Path

    from apps.kern import backup

    wurzel = Path(backup.__file__).resolve().parents[2]
    for pfad in [Path(backup.__file__), *(wurzel / "deploy").glob("*")]:
        if pfad.is_file() and pfad.name != "entrypoint.sh":  # legt nur Verzeichnisse an
            text = pfad.read_text().lower()
            for verboten in ("nachweis_dir", "media_root", "/media", 'data_dir/"media'):
                assert verboten not in text, (pfad, verboten)


def test_registrierung_aktiv():
    assert nachweise.speichern in ablauf._nachweis_speicher
    assert nachweise.loeschen in ablauf._nachweis_loescher


def test_umask_unabhaengig(gemeldet, nachweis_dir):
    alt = os.umask(0)
    try:
        assert stat.S_IMODE(nachweis_dir.stat().st_mode) == 0o700
    finally:
        os.umask(alt)


# --- Review AP19 ------------------------------------------------------------------------------


def _zweite_instanz(instanz):
    aufgabe = Aufgabe.objects.create(
        titel="Zimmer 2",
        punkte=10,
        erstellt_von=instanz.aufgabe.erstellt_von,
        freigabeart="nachweis",
        wiederholungsart=wiederholung.EINMALIG,
    )
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        titel_snapshot="Zimmer 2",
        punkte_snapshot=10,
        freigabeart_snapshot="nachweis",
    )


def test_fotos_einer_zurueckgerollten_meldung_landen_nie_bei_einer_neuen(instanz, anna, ben):
    """Regression B-04: SQLite vergibt die ID einer zurückgerollten Meldung erneut. Die Fotos
    des ersten Versuchs (Anna) dürfen nicht an der neuen Meldung (Ben) hängen."""
    from django.db import transaction

    zweite = _zweite_instanz(instanz)
    with pytest.raises(RuntimeError), transaction.atomic():
        services.interesse_zeigen(instanz, anna)
        services.erledigt_melden(instanz, anna, text="x", fotos=[upload(jpeg((60, 60)))])
        alte_id = Meldung.objects.get(instanz=instanz).pk
        raise RuntimeError("später scheitert etwas, alles wird zurückgerollt")
    assert nachweise.dateinamen(alte_id)  # Datei ist verwaist zurückgeblieben

    services.interesse_zeigen(zweite, ben)
    services.erledigt_melden(zweite, ben, text="ohne Foto")
    neue = Meldung.objects.get(instanz=zweite)
    assert neue.pk == alte_id  # gleiche ID wie die zurückgerollte
    assert nachweise.dateinamen(neue.pk) == []


def test_fotos_entstehen_erst_wenn_ereignis_und_audit_stehen(instanz, anna, monkeypatch):
    """B-04: Scheitert das Ereignis, wird gar keine Datei geschrieben."""
    from apps.aufgaben import ablauf as ablauf_modul

    services.interesse_zeigen(instanz, anna)

    def kaputt(*args, **kwargs):
        raise RuntimeError("Outbox nicht erreichbar")

    monkeypatch.setattr(ablauf_modul.ereignisse, "veroeffentlichen", kaputt)
    with pytest.raises(RuntimeError):
        services.erledigt_melden(instanz, anna, text="x", fotos=[upload(jpeg((60, 60)))])
    assert not nachweise.wurzel().exists() or not any(nachweise.wurzel().rglob("*.jpg"))


def test_zu_grosse_upload_anfrage_wird_vor_dem_lesen_abgewiesen(instanz, anna, kind_client):
    """Regression B-07: Django liest Uploads sonst komplett auf die Platte (auch die
    CSRF-Prüfung liest den Body); die Grenze greift vorher anhand von Content-Length."""
    services.interesse_zeigen(instanz, anna)
    grenze = nachweise.max_fotos() * nachweise.max_bytes() + 1024 * 1024
    antwort = kind_client.post(
        reverse("aufgaben:kind_melden", args=[instanz.pk]),
        {"text": "x"},
        CONTENT_LENGTH=str(grenze + 1),
    )
    assert antwort.status_code == 413
    instanz.refresh_from_db()
    assert instanz.status == InstanzStatus.RESERVIERT


@pytest.mark.django_db
def test_kantenlaenge_ist_einstellung():
    from apps.kern import einstellungen

    assert nachweise.max_kante() == 1600
    einstellungen.setzen("aufgaben.nachweis_max_kante_px", 800, akteur=None)
    daten = nachweise.bild_verarbeiten(upload(jpeg((2000, 1000), gps=False)))
    assert Image.open(io.BytesIO(daten)).size == (800, 400)
