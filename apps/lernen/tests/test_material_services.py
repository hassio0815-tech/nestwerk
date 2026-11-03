"""Material-Pipeline: Aufnehmen, Inbox-Scan, Warteschlange, Freigabe, Löschen (SPEC 21.5)."""

import os

import pytest

from apps.kern import einstellungen
from apps.lernen import ki_services, material_ki, services
from apps.lernen import material_services as ms
from apps.lernen.material_dateien import UploadFehler
from apps.lernen.models import (
    Fach,
    Frage,
    KiAuftrag,
    KiAuftragStatus,
    Material,
    MaterialStatus,
    Quelle,
)
from apps.lernen.speicher import Speicher, SpeicherVoll

from . import material_hilfen as h


@pytest.fixture
def speicher():
    return Speicher()


@pytest.fixture
def ki_bereit(lokal):
    einstellungen.setzen("lernen.ki_mindestabstand_sekunden", 0, akteur=None)
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("auslesen", lokal)
    ki_services.zuordnung_setzen("fragen_erzeugen", lokal)
    return lokal


def hochladen(kind, name="foto.jpg", daten=None):
    return ms.aufnehmen(kind, name, daten if daten is not None else h.jpeg())


# --- Aufnehmen -------------------------------------------------------------------------------


def test_upload_ohne_ki_wartet_freundlich(kind_a, speicher):
    m = hochladen(kind_a)
    assert m.status == MaterialStatus.WARTET_KI
    assert not KiAuftrag.objects.exists()
    assert (speicher.ordner(kind_a.pk, "inbox") / m.name).is_file()
    assert m.name.endswith(".jpg") and m.name != "foto.jpg"
    assert m.anzeigename == "foto.jpg"
    assert (m.art, m.bereich, m.eingang) == ("bild", "inbox", "upload")


def test_upload_mit_ki_reiht_auslesen_ein(kind_a, ki_bereit):
    m = hochladen(kind_a)
    assert m.status == MaterialStatus.WARTET
    auftrag = KiAuftrag.objects.get()
    assert auftrag.aufgabe == "auslesen"
    assert auftrag.eingabe_verweis == f"lernen.material:{m.pk}"
    assert auftrag.kind_id == kind_a.pk
    assert "foto" not in auftrag.schluessel  # nie Inhalte oder Namen in der Warteschlange


def test_doppelter_upload_wird_abgelehnt(kind_a):
    hochladen(kind_a)
    with pytest.raises(ms.MaterialFehler, match="schon hochgeladen"):
        hochladen(kind_a, "anderer-name.jpg")
    assert Material.objects.count() == 1


def test_gleicher_name_anderer_inhalt_gibt_zwei_dateien(kind_a, speicher):
    a = hochladen(kind_a, "blatt.jpg", h.jpeg((1, 1, 1)))
    b = hochladen(kind_a, "blatt.jpg", h.jpeg((250, 250, 250)))
    assert a.name != b.name
    assert len(list(speicher.ordner(kind_a.pk, "inbox").iterdir())) == 2


def test_gleicher_inhalt_bei_geschwistern_ist_erlaubt(kind_a, kind_b):
    hochladen(kind_a)
    hochladen(kind_b)
    assert Material.objects.count() == 2


@pytest.mark.parametrize(
    "name", ["../../x.jpg", "..\\..\\x.jpg", "/etc/passwd.jpg", "a\x00b.jpg", ".jpg.jpg"]
)
def test_pfadtricks_im_namen_schaden_nicht(kind_a, speicher, tmp_path, name):
    m = hochladen(kind_a, name)
    inbox = speicher.ordner(kind_a.pk, "inbox")
    assert (inbox / m.name).parent == inbox
    assert "/" not in m.name and ".." not in m.name
    alle = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(inbox in p.parents for p in alle)  # nichts außerhalb der inbox


def test_falscher_typ_und_zu_gross_speichern_nichts(kind_a, speicher):
    with pytest.raises(UploadFehler):
        ms.aufnehmen(kind_a, "virus.exe", b"MZ\x00\x01")
    einstellungen.setzen("lernen.upload_max_mb", 1, akteur=None)
    with pytest.raises(UploadFehler, match="zu groß"):
        ms.aufnehmen(kind_a, "gross.txt", b"a" * (1024 * 1024 + 1))
    assert not Material.objects.exists()
    assert speicher.belegt_bytes(kind_a.pk) == 0


def test_speicherlimit_pro_kind(kind_a, kind_b):
    einstellungen.setzen("lernen.speicher_limit_mb", 10, akteur=None)
    Speicher().speichern(kind_a.pk, "archiv", "alt.bin", b"x" * (10 * 1024 * 1024 - 100))
    with pytest.raises(SpeicherVoll):
        ms.aufnehmen(kind_a, "neu.txt", b"y" * 500)
    assert not Material.objects.filter(kind=kind_a).exists()
    hochladen(kind_b)  # das Geschwister hat sein eigenes Limit


def test_nur_kinder_koennen_hochladen(mama):
    with pytest.raises(ms.MaterialFehler):
        ms.aufnehmen(mama, "a.txt", b"hallo")


def test_datenbankfehler_raeumt_die_datei_auf(kind_a, speicher, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("db")

    monkeypatch.setattr(ms.audit, "protokollieren", kaputt)
    with pytest.raises(RuntimeError):
        hochladen(kind_a)
    assert list(speicher.ordner(kind_a.pk, "inbox").iterdir()) == []
    assert not Material.objects.exists()


# --- Inbox-Scan ------------------------------------------------------------------------------


def ablegen(speicher, kind, rel, daten):
    pfad = speicher.ordner(kind.pk, "inbox") / rel
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return pfad


def scan(**kw):
    return ms.inbox_scannen(pause=0, ruhe=0, **kw)


def test_scan_uebernimmt_dateien_und_ist_idempotent(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    ablegen(speicher, kind_a, "scan1.jpg", h.jpeg((1, 2, 3)))
    ablegen(speicher, kind_a, "testsprache/liste.txt", b"Hund dog")
    Fach.objects.create(schluessel="testsprache", name="Testsprache")
    assert scan() == {"uebernommen": 2}
    assert Material.objects.count() == 2
    hinweise = set(Material.objects.values_list("hinweis_fach", flat=True))
    assert hinweise == {"", "testsprache"}
    assert Material.objects.filter(eingang="inbox").count() == 2
    assert scan() == {}  # zweiter Lauf: nichts mehr zu tun
    assert Material.objects.count() == 2
    # die Originale sind weg, die neutralen Kopien liegen in der inbox
    namen = {p.name for p in speicher.ordner(kind_a.pk, "inbox").rglob("*") if p.is_file()}
    assert namen == set(Material.objects.values_list("name", flat=True))


def test_scan_ueberspringt_wartende_uploads(kind_a, speicher):
    hochladen(kind_a)
    assert scan() == {}
    assert Material.objects.count() == 1


def test_scan_unbekannter_unterordner_ist_kein_hinweis(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    ablegen(speicher, kind_a, "gibts-nicht/a.txt", b"Hallo")
    scan()
    assert Material.objects.get().hinweis_fach == ""


def test_scan_ignoriert_symlinks_und_versteckte(kind_a, speicher, tmp_path):
    services.lernmappe_sicherstellen(kind_a)
    geheim = tmp_path / "geheim.txt"
    geheim.write_text("Passwort")
    inbox = speicher.ordner(kind_a.pk, "inbox")
    os.symlink(geheim, inbox / "link.txt")
    fremd = tmp_path / "fremd"
    fremd.mkdir()
    (fremd / "x.txt").write_text("Fremd")
    os.symlink(fremd, inbox / "ordner")
    ablegen(speicher, kind_a, ".versteckt.txt", b"hallo")
    ablegen(speicher, kind_a, "tief/tiefer/a.txt", b"zu tief")
    assert scan() == {}
    assert not Material.objects.exists()
    assert geheim.read_text() == "Passwort"


def test_scan_unzulaessige_datei_wird_archiviert_mit_fehler(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    ablegen(speicher, kind_a, "virus.exe", b"MZ\x00")
    ablegen(speicher, kind_a, "ok.txt", b"Hallo Welt")
    assert scan() == {"uebernommen": 1, "abgelehnt": 1}
    fehler = Material.objects.get(status="fehler")
    assert (fehler.fehler, fehler.bereich) == ("typ", "archiv")
    assert (speicher.ordner(kind_a.pk, "archiv") / fehler.name).is_file()
    assert not (speicher.ordner(kind_a.pk, "inbox") / "virus.exe").exists()
    assert scan() == {}


def test_scan_doppelte_und_zu_grosse_dateien(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    hochladen(kind_a, "a.txt", b"Gleicher Inhalt")
    ablegen(speicher, kind_a, "kopie.txt", b"Gleicher Inhalt")
    einstellungen.setzen("lernen.upload_max_mb", 1, akteur=None)
    ablegen(speicher, kind_a, "riesig.txt", b"a" * (1024 * 1024 + 1))
    assert scan() == {"abgelehnt": 2}
    assert sorted(Material.objects.filter(status="fehler").values_list("fehler", flat=True)) == [
        "doppelt",
        "zu_gross",
    ]


def test_scan_wartet_auf_ruhe_und_stabile_groesse(kind_a, speicher, monkeypatch):
    services.lernmappe_sicherstellen(kind_a)
    pfad = ablegen(speicher, kind_a, "neu.txt", b"Hallo")
    # zu frisch
    assert ms.inbox_scannen(pause=0, ruhe=60) == {"noch_nicht_ruhig": 1}
    assert pfad.exists()

    # Größe ändert sich während der Pause
    class Waechst:
        def __init__(self, echt):
            self.echt = echt

        def __getattr__(self, name):
            return getattr(self.echt, name)

        def stat(self):
            info = self.echt.stat()
            return type("S", (), {"st_size": info.st_size + 1, "st_mtime": info.st_mtime})()

    from apps.lernen import speicher as sp

    originale = sp.Speicher.inbox_dateien

    def inbox_dateien(selbst, kind_id):
        return [
            d.__class__(Waechst(d.pfad), d.hinweis, d.name, d.groesse - 1, d.geaendert)
            for d in originale(selbst, kind_id)
        ]

    monkeypatch.setattr(sp.Speicher, "inbox_dateien", inbox_dateien)
    assert scan() == {"noch_nicht_ruhig": 1}
    assert not Material.objects.exists()


def test_scan_hoechstens_n_dateien_pro_lauf(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    for i in range(3):
        ablegen(speicher, kind_a, f"d{i}.txt", f"Inhalt {i}".encode())
    assert scan(maximal=2) == {"uebernommen": 2, "uebrig": 1}
    assert scan(maximal=2) == {"uebernommen": 1}


def test_scan_speicher_voll_laesst_datei_liegen(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    einstellungen.setzen("lernen.speicher_limit_mb", 10, akteur=None)
    speicher.speichern(kind_a.pk, "archiv", "alt.bin", b"x" * (10 * 1024 * 1024 - 5))
    pfad = ablegen(speicher, kind_a, "neu.txt", b"zu viel Text")
    assert scan() == {"speicher_voll": 1}
    assert pfad.exists()


def test_scan_datei_verschwindet_waehrend_des_laufs(kind_a, speicher):
    services.lernmappe_sicherstellen(kind_a)
    pfad = ablegen(speicher, kind_a, "weg.txt", b"Hallo")
    from apps.lernen.speicher import InboxDatei

    fake = InboxDatei(pfad, "", "weg.txt", 5, 0.0)
    pfad.unlink()
    zaehler = {}
    ms._scan_datei(kind_a, fake, speicher, __import__("collections").Counter(zaehler))
    assert not Material.objects.filter(status="wartet_ki", eingang="inbox").exists()


def test_scan_beachtet_nur_aktive_kinder(kind_a, kind_b, speicher):
    services.lernmappe_sicherstellen(kind_b)
    ablegen(speicher, kind_b, "a.txt", b"Hallo")
    kind_b.aktiv = False
    kind_b.save()
    assert scan() == {}


# --- Warteschlange abgleichen ----------------------------------------------------------------


def test_wartende_werden_eingereiht_sobald_ki_bereit(kind_a, lokal):
    m = hochladen(kind_a)
    assert m.status == MaterialStatus.WARTET_KI
    assert ms.wartende_einreihen() == {}
    einstellungen.setzen("lernen.ki_mindestabstand_sekunden", 0, akteur=None)
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("auslesen", lokal)
    assert ms.wartende_einreihen() == {"eingereiht": 1}
    m.refresh_from_db()
    assert m.status == MaterialStatus.WARTET
    assert ms.wartende_einreihen() == {}  # nichts doppelt
    assert KiAuftrag.objects.count() == 1


def test_gescheiterter_auftrag_ohne_ki_geht_zurueck_auf_warten(kind_a, ki_bereit):
    m = hochladen(kind_a)
    KiAuftrag.objects.update(status=KiAuftragStatus.FEHLER, fehler_art="aus")
    assert ms.wartende_einreihen() == {"zurueck_auf_ki": 1}
    m.refresh_from_db()
    assert (m.status, m.durchgang) == (MaterialStatus.WARTET_KI, 2)
    # KI ist ja bereit: nächster Lauf reiht mit neuem Schlüssel neu ein
    assert ms.wartende_einreihen() == {"eingereiht": 1}
    assert KiAuftrag.objects.count() == 2


def test_gescheiterter_auftrag_mit_echtem_fehler(kind_a, ki_bereit):
    m = hochladen(kind_a)
    KiAuftrag.objects.update(status=KiAuftragStatus.FEHLER, fehler_art="ausgabe")
    assert ms.wartende_einreihen() == {"fehler": 1}
    m.refresh_from_db()
    assert (m.status, m.fehler) == (MaterialStatus.FEHLER, "ausgabe")
    assert "nicht brauchbar" in ms.fehlertext(m)


def test_fehlender_auftrag_wird_nachgereicht(kind_a, ki_bereit):
    m = hochladen(kind_a)
    KiAuftrag.objects.all().delete()
    assert ms.wartende_einreihen() == {"nachgereicht": 1}
    assert KiAuftrag.objects.count() == 1
    m.refresh_from_db()
    assert m.status == MaterialStatus.WARTET


def test_laufender_auftrag_bleibt_unberuehrt(kind_a, ki_bereit):
    hochladen(kind_a)
    KiAuftrag.objects.update(status=KiAuftragStatus.LAEUFT)
    assert ms.wartende_einreihen() == {}


def test_neu_starten(kind_a, ki_bereit):
    m = hochladen(kind_a)
    ms.fehler_setzen(m, "ausgabe")
    m.refresh_from_db()
    assert ms.neu_starten(m) is True
    m.refresh_from_db()
    assert (m.status, m.durchgang, m.fehler) == (MaterialStatus.WARTET, 2, "")
    with pytest.raises(ms.MaterialFehler):
        ms.neu_starten(m)  # läuft schon
    ms.fehler_setzen(m, "typ")
    m.refresh_from_db()
    with pytest.raises(ms.MaterialFehler, match="löschen"):
        ms.neu_starten(m)


def test_fehlertexte():
    class M:
        fehler = ""

    assert ms.fehlertext(M()) == ""
    M.fehler = "verbindung"
    assert "nicht erreichbar" in ms.fehlertext(M())
    M.fehler = "unbekannt!"
    assert ms.fehlertext(M()) == "Unerwarteter Fehler."


# --- Freigabe --------------------------------------------------------------------------------


@pytest.fixture
def mit_fragen(kind_a, fach):
    """Ein Material mit drei wartenden KI-Fragen."""
    m = hochladen(kind_a)
    Material.objects.filter(pk=m.pk).update(
        status=MaterialStatus.FRAGEN, fach=fach, text="Hund dog", thema_name="Tiere"
    )
    m.refresh_from_db()
    thema = material_ki.thema_holen(kind_a, fach, "Tiere")
    for f, a in (("Hund", "dog"), ("Katze", "cat"), ("Maus", "mouse")):
        services.frage_anlegen(thema, "vokabel", f, a, quelle=Quelle.KI, kind=kind_a, material=m)
    ms.status_abgleichen(m)
    return m


def test_standard_ist_freigabe_durch_eltern(kind_a, mit_fragen):
    assert ms.sofort_nutzbar(kind_a) is False
    assert mit_fragen.status == MaterialStatus.WARTET_ELTERN
    assert set(mit_fragen.fragen.values_list("freigabe", flat=True)) == {"offen"}


def test_freigeben_einzeln_und_gesammelt(mit_fragen):
    ids = list(mit_fragen.fragen.values_list("pk", flat=True))
    assert ms.freigeben(mit_fragen, ids[:1]) == 1
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.WARTET_ELTERN  # zwei warten noch
    assert ms.freigeben(mit_fragen) == 2
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.BEREIT


def test_ablehnen_und_nachtraeglich_freigeben(mit_fragen):
    assert ms.ablehnen(mit_fragen) == 3
    mit_fragen.refresh_from_db()
    assert (mit_fragen.status, mit_fragen.fehler) == (MaterialStatus.FEHLER, "abgelehnt")
    assert ms.freigeben(mit_fragen) == 0  # ohne Auswahl nur wartende
    erste = mit_fragen.fragen.first().pk
    assert ms.freigeben(mit_fragen, [erste]) == 1
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.BEREIT


def test_status_bleibt_ausserhalb_des_endbereichs(kind_a):
    m = hochladen(kind_a)
    assert ms.status_abgleichen(m) == MaterialStatus.WARTET_KI


def test_pro_kind_sofort_nutzbar(kind_a, kind_b, fach):
    thema = material_ki.thema_holen(kind_a, fach, "Tiere")
    ms.sofort_nutzbar_setzen(kind_a, True)
    assert ms.sofort_nutzbar(kind_a) is True and ms.sofort_nutzbar(kind_b) is False
    f = services.frage_anlegen(thema, "frage", "A?", "B", quelle=Quelle.KI, kind=kind_a)
    assert f.freigabe == "freigegeben"
    f2 = services.frage_anlegen(thema, "frage", "C?", "D", quelle=Quelle.KI, kind=kind_b)
    assert f2.freigabe == "offen"
    ms.sofort_nutzbar_setzen(kind_a, False)
    assert ms.sofort_nutzbar(kind_a) is False
    # ohne eigene Einstellung gilt die Familien-Einstellung
    einstellungen.setzen("lernen.freigabe_durch_eltern", False, akteur=None)
    assert ms.sofort_nutzbar(kind_b) is True


def test_frage_bearbeiten(mit_fragen):
    frage = mit_fragen.fragen.first()
    ms.frage_bearbeiten(mit_fragen, frage.pk, "  Hund  (Tier) ", "dog")
    frage.refresh_from_db()
    assert (frage.frage, frage.antwort) == ("Hund (Tier)", "dog")
    for schlecht in ("", "<b>fett</b>", "http://boese.example/x", "mail@example.org"):
        with pytest.raises(ms.MaterialFehler):
            ms.frage_bearbeiten(mit_fragen, frage.pk, schlecht, "dog")
    with pytest.raises(ms.MaterialFehler, match="gibt es nicht"):
        ms.frage_bearbeiten(mit_fragen, 999999, "a", "b")


def test_fach_aendern_verschiebt_fragen_und_setzt_rueckfrage_fort(kind_a, mit_fragen, ki_bereit):
    anderes = Fach.objects.create(schluessel="zweitfach", name="Zweitfach")
    ms.fach_aendern(mit_fragen, anderes, "Neues Thema")
    mit_fragen.refresh_from_db()
    assert (mit_fragen.fach, mit_fragen.thema_name, mit_fragen.konfidenz) == (
        anderes,
        "Neues Thema",
        1.0,
    )
    assert {f.thema.fach for f in mit_fragen.fragen.select_related("thema")} == {anderes}
    inaktiv = Fach.objects.create(schluessel="aus", name="Aus", aktiv=False)
    with pytest.raises(ms.MaterialFehler):
        ms.fach_aendern(mit_fragen, inaktiv)


def test_fach_aendern_bei_rueckfrage_macht_weiter(kind_a, fach, ki_bereit):
    m = hochladen(kind_a)
    Material.objects.filter(pk=m.pk).update(status=MaterialStatus.RUECKFRAGE, text="Hund dog")
    m.refresh_from_db()
    ms.fach_aendern(m, fach, "Tiere")
    m.refresh_from_db()
    assert m.status == MaterialStatus.FRAGEN
    assert KiAuftrag.objects.filter(aufgabe="fragen_erzeugen").count() == 1


def test_manuelle_frage(kind_a, fach):
    m = hochladen(kind_a)
    with pytest.raises(ms.MaterialFehler, match="Fach"):
        ms.manuelle_frage(m, "frage", "A?", "B")
    ms.fach_aendern(m, fach, "Tiere")
    m.refresh_from_db()
    frage = ms.manuelle_frage(m, "unsinn", "Was ist 2+2?", "4")
    assert (frage.typ, frage.quelle, frage.freigabe, frage.kind_id) == (
        "frage",
        "eltern",
        "freigegeben",
        kind_a.pk,
    )
    assert frage.material_id == m.pk
    with pytest.raises(ms.MaterialFehler):
        ms.manuelle_frage(m, "frage", "", "4")
    m.refresh_from_db()
    assert m.status == MaterialStatus.WARTET_KI  # noch keine KI: Status bleibt


def test_manuelle_frage_bringt_wartendes_material_auf_bereit(mit_fragen):
    ms.manuelle_frage(mit_fragen, "frage", "Was bellt?", "Hund")
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.WARTET_ELTERN  # drei KI-Fragen warten weiter
    ms.ablehnen(mit_fragen)
    mit_fragen.refresh_from_db()
    assert mit_fragen.status == MaterialStatus.BEREIT


# --- Löschen und Ansicht ---------------------------------------------------------------------


def test_loeschen_entfernt_alles(kind_a, kind_b, mit_fragen, speicher, fach):
    fremd = hochladen(kind_b)
    ms.einreihen(mit_fragen)
    name = mit_fragen.name
    thema_fragen = Frage.objects.count()
    ms.loeschen(mit_fragen)
    assert not Material.objects.filter(pk=mit_fragen.pk).exists()
    assert Frage.objects.count() == thema_fragen - 3
    assert not (speicher.ordner(kind_a.pk, "inbox") / name).exists()
    assert not KiAuftrag.objects.filter(eingabe_verweis=f"lernen.material:{mit_fragen.pk}").exists()
    assert Material.objects.filter(pk=fremd.pk).exists()  # Geschwister unberührt


def test_loeschen_findet_original_im_archiv(kind_a, speicher):
    m = hochladen(kind_a)
    speicher.verschieben(kind_a.pk, m.name, "inbox", "archiv")
    Material.objects.filter(pk=m.pk).update(bereich="archiv")
    m.refresh_from_db()
    assert ms.datei_oeffnen(m) == speicher.pfad(kind_a.pk, "archiv", m.name)
    ms.loeschen(m)
    assert not (speicher.ordner(kind_a.pk, "archiv") / m.name).exists()


def test_datei_oeffnen_ohne_datei(kind_a, speicher):
    m = hochladen(kind_a)
    speicher.loeschen(kind_a.pk, "inbox", m.name)
    assert ms.datei_oeffnen(m) is None


def test_verbrauch(kind_a):
    hochladen(kind_a, "a.txt", b"x" * 100)
    belegt, limit = ms.verbrauch(kind_a)
    assert belegt == 100 and limit == 500 * 1024 * 1024


def test_job_befehl(kind_a, speicher, capsys):
    from django.core.management import call_command

    from apps.kern.models import JobLauf

    services.lernmappe_sicherstellen(kind_a)
    ablegen(speicher, kind_a, "neu.txt", b"Hallo Welt")
    einstellungen.setzen("lernen.scan_ruhe_sekunden", 0, akteur=None)
    hochladen(kind_a, "wartet.txt", b"Anderer Text")
    call_command("lernen_inbox_scannen")
    lauf = JobLauf.objects.get(name="lernen_inbox_scannen")
    assert lauf.status == "ok" and lauf.info["uebernommen"] == 1
    assert Material.objects.count() == 2
