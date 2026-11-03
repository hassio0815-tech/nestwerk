"""Warteschlange und Job: Idempotenz, Backoff, Abbruch, Rate-Limit, Job-Sperre (SPEC 21.6)."""

import logging
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone

from apps.kern import einstellungen, jobs
from apps.kern.models import JobLauf, JobStatus
from apps.lernen import ki_selectors, ki_services
from apps.lernen import ki_warteschlange as q
from apps.lernen.ki import KiAnfrageFehler, KiAuthFehler, KiServerFehler
from apps.lernen.models import KiAuftrag, KiAuftragStatus

JETZT = timezone.now().replace(microsecond=0)


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    for a in ("tutor", "bewerten", "auslesen", "fragen_erzeugen"):
        q.handler_entfernen(a)


@pytest.fixture
def bereit(lokal):
    """Lokaler Anbieter aktiv und für 'tutor' und 'bewerten' zugeordnet, ohne Mindestabstand."""
    einstellungen.setzen("lernen.ki_mindestabstand_sekunden", 0, akteur=None)
    ki_services.anbieter_aktivieren(lokal)
    ki_services.zuordnung_setzen("tutor", lokal)
    ki_services.zuordnung_setzen("bewerten", lokal)
    return lokal


class Zaehler:
    def __init__(self, fehler=()):
        self.fehler = list(fehler)
        self.aufrufe = []

    def __call__(self, auftrag):
        self.aufrufe.append(auftrag.pk)
        if self.fehler:
            f = self.fehler.pop(0)
            if f:
                raise f


def _neu(schluessel="a1", aufgabe="tutor", **kw):
    return q.auftrag_einreihen(aufgabe, schluessel, **kw)[0]


# --- Einreihen -----------------------------------------------------------------------------------


def test_einreihen_ist_idempotent(db, kind_a):
    a1, neu1 = q.auftrag_einreihen(
        "tutor", "k1", kind=kind_a, eingabe_verweis="lernen.frage:" + "9" * 300
    )
    a2, neu2 = q.auftrag_einreihen("tutor", "k1")
    assert neu1 and not neu2 and a1.pk == a2.pk
    assert KiAuftrag.objects.count() == 1
    assert (a1.status, a1.versuche) == ("wartend", 0) and len(a1.eingabe_verweis) == 200


def test_einreihen_validiert(db):
    with pytest.raises(ValueError):
        q.auftrag_einreihen("quatsch", "k")
    for schluessel in ("", "  ", "x" * 121):
        with pytest.raises(ValueError):
            q.auftrag_einreihen("tutor", schluessel)


def test_einreihen_bei_paralleler_anlage(db, monkeypatch):
    vorhanden = _neu("k2")

    def kaputt(**kw):
        raise IntegrityError

    monkeypatch.setattr(KiAuftrag.objects, "get_or_create", kaputt)
    auftrag, neu = q.auftrag_einreihen("tutor", "k2")
    assert auftrag.pk == vorhanden.pk and neu is False


def test_handler_registrieren_validiert(db):
    with pytest.raises(ValueError):
        q.handler_registrieren("quatsch", lambda a: None)


# --- Verarbeiten ---------------------------------------------------------------------------------


def test_erfolg_einmal_verarbeitet(bereit):
    h = Zaehler()
    q.handler_registrieren("tutor", h)
    a = _neu()
    info = q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert (a.status, a.versuche, a.fehler_art) == ("fertig", 1, "")
    assert a.anbieter == bereit and a.gestartet_am and a.beendet_am
    assert info == {"bearbeitet": 1, "fertig": 1}
    assert q.verarbeiten(jetzt=JETZT) == {}  # nichts mehr zu tun
    assert h.aufrufe == [a.pk]


def test_handler_nutzt_ki_aufruf(bereit, transport):
    gesehen = []

    def handler(auftrag):
        gesehen.append(ki_services.ki_aufruf(auftrag.aufgabe, nachricht="x", kind=auftrag.kind))

    q.handler_registrieren("bewerten", handler)
    _neu("b1", "bewerten")
    q.verarbeiten(jetzt=JETZT)
    assert gesehen[0].text == "OK" and len(transport.aufrufe) == 1


def test_ki_aus_fuer_die_aufgabe_ist_endgueltiger_fehler(bereit):
    h = Zaehler()
    q.handler_registrieren("auslesen", h)  # 'auslesen' hat keine Zuordnung
    a = _neu("x", "auslesen")
    info = q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert (a.status, a.fehler_art) == ("fehler", "aus") and h.aufrufe == []
    assert info["fehler"] == 1


def test_cloud_ohne_einwilligung_wird_nicht_aufgerufen(cloud):
    einstellungen.setzen("lernen.ki_mindestabstand_sekunden", 0, akteur=None)
    cloud.aktiv = True
    cloud.save()
    ki_services.zuordnung_setzen("tutor", cloud)
    h = Zaehler()
    q.handler_registrieren("tutor", h)
    a = _neu()
    q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert a.status == "fehler" and h.aufrufe == []


def test_ohne_handler_fehler(bereit):
    a = _neu()
    q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert (a.status, a.fehler_art) == ("fehler", "kein_handler")


def test_backoff_und_abbruch_nach_n_fehlern(bereit):
    h = Zaehler([KiServerFehler(500)] * 3)
    q.handler_registrieren("tutor", h)
    a = _neu()
    q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert (a.status, a.versuche, a.fehler_art) == ("wartend", 1, "server")
    assert a.naechster_versuch_am == JETZT + timedelta(seconds=60)
    # noch nicht fällig
    assert q.verarbeiten(jetzt=JETZT + timedelta(seconds=59)) == {}
    # zweiter Versuch: Wartezeit x4
    t2 = JETZT + timedelta(seconds=60)
    info = q.verarbeiten(jetzt=t2)
    a.refresh_from_db()
    assert (a.status, a.versuche) == ("wartend", 2) and info["wiederholt"] == 1
    assert a.naechster_versuch_am == t2 + timedelta(seconds=240)
    # dritter Fehlversuch = Limit (lernen.ki_max_versuche = 3) -> endgültig
    t3 = t2 + timedelta(seconds=240)
    info = q.verarbeiten(jetzt=t3)
    a.refresh_from_db()
    assert (a.status, a.versuche, a.fehler_art) == ("fehler", 3, "server")
    assert info["fehler"] == 1
    assert q.verarbeiten(jetzt=t3 + timedelta(days=1)) == {}
    assert len(h.aufrufe) == 3


def test_backoff_hat_obergrenze(bereit):
    einstellungen.setzen("lernen.ki_max_versuche", 10, akteur=None)
    assert q._backoff(9) == q.BACKOFF_MAX


def test_erfolg_nach_wiederholung(bereit):
    h = Zaehler([KiServerFehler(503), None])
    q.handler_registrieren("tutor", h)
    a = _neu()
    q.verarbeiten(jetzt=JETZT)
    q.verarbeiten(jetzt=JETZT + timedelta(seconds=61))
    a.refresh_from_db()
    assert (a.status, a.versuche, a.fehler_art) == ("fertig", 2, "")


def test_nicht_wiederholbarer_fehler_sofort_endgueltig(bereit):
    q.handler_registrieren("tutor", Zaehler([KiAnfrageFehler(400)]))
    a = _neu()
    q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert (a.status, a.versuche, a.fehler_art) == ("fehler", 1, "anfrage")


def test_unerwarteter_handlerfehler_loggt_nur_typ(bereit, caplog):
    q.handler_registrieren("tutor", Zaehler([RuntimeError("GEHEIMER-INHALT")]))
    a = _neu()
    with caplog.at_level(logging.WARNING, logger="nestwerk.lernen.ki"):
        q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert (a.status, a.fehler_art) == ("fehler", "intern")
    assert "RuntimeError" in caplog.text and "GEHEIM" not in caplog.text


def test_anbieter_wird_nach_auth_fehler_im_lauf_uebersprungen(bereit):
    h = Zaehler([KiAuthFehler(401), None])
    q.handler_registrieren("tutor", h)
    a1, a2 = _neu("a1"), _neu("a2")
    info = q.verarbeiten(jetzt=JETZT)
    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.status == "fehler" and (a2.status, a2.versuche) == ("wartend", 0)
    assert info["uebersprungen"] == 1 and len(h.aufrufe) == 1
    # nächster Lauf: a2 wird bearbeitet
    q.verarbeiten(jetzt=JETZT)
    a2.refresh_from_db()
    assert a2.status == "fertig"


def test_mindestabstand_je_anbieter(bereit):
    einstellungen.setzen("lernen.ki_mindestabstand_sekunden", 30, akteur=None)
    h = Zaehler()
    q.handler_registrieren("tutor", h)
    a1, a2 = _neu("a1"), _neu("a2")
    info = q.verarbeiten(jetzt=JETZT)
    assert info == {"bearbeitet": 1, "fertig": 1, "uebersprungen": 1}
    # später Lauf, aber noch zu früh (Abstand wird aus der DB gelesen)
    KiAuftrag.objects.filter(pk=a1.pk).update(beendet_am=JETZT)
    assert q.verarbeiten(jetzt=JETZT + timedelta(seconds=29)) == {"uebersprungen": 1}
    info = q.verarbeiten(jetzt=JETZT + timedelta(seconds=30))
    assert info == {"bearbeitet": 1, "fertig": 1}
    a2.refresh_from_db()
    assert a2.status == "fertig"


def test_aufträge_pro_lauf_begrenzt(bereit):
    einstellungen.setzen("lernen.ki_auftraege_pro_lauf", 2, akteur=None)
    q.handler_registrieren("tutor", Zaehler())
    for i in range(3):
        _neu(f"k{i}")
    assert q.verarbeiten(jetzt=JETZT)["fertig"] == 2
    assert q.verarbeiten(jetzt=JETZT)["fertig"] == 1


def test_haengender_auftrag_wird_zurueckgesetzt(bereit):
    h = Zaehler()
    q.handler_registrieren("tutor", h)
    a = _neu()
    KiAuftrag.objects.filter(pk=a.pk).update(
        status="laeuft", versuche=1, gestartet_am=JETZT - timedelta(minutes=20)
    )
    info = q.verarbeiten(jetzt=JETZT)
    a.refresh_from_db()
    assert info == {"zurueckgesetzt": 1}
    assert (a.status, a.fehler_art) == ("wartend", "abgebrochen")
    assert a.naechster_versuch_am == JETZT + timedelta(seconds=60)
    # frisch laufende Aufträge (anderer Prozess) bleiben unberührt
    KiAuftrag.objects.filter(pk=a.pk).update(
        status="laeuft", gestartet_am=JETZT - timedelta(minutes=1)
    )
    assert q.verarbeiten(jetzt=JETZT) == {}
    assert h.aufrufe == []


def test_bedingte_updates_kein_doppelter_zugriff(bereit, monkeypatch):
    """Wurde ein Auftrag zwischen Auswahl und Beanspruchung erledigt, wird er nicht erneut
    bearbeitet (bedingtes UPDATE ... WHERE status = 'wartend')."""
    h = Zaehler()
    q.handler_registrieren("tutor", h)
    a = _neu()
    echt = ki_selectors.zuordnung_fuer

    def zuordnung_mit_wettlauf(aufgabe):
        KiAuftrag.objects.filter(pk=a.pk).update(status="fertig")  # anderer Lauf war schneller
        return echt(aufgabe)

    monkeypatch.setattr(ki_selectors, "zuordnung_fuer", zuordnung_mit_wettlauf)
    assert q.verarbeiten(jetzt=JETZT) == {}
    assert h.aufrufe == []


def test_auftrag_verschwindet_zwischen_auswahl_und_lauf(bereit, monkeypatch):
    a = _neu()
    echt_filter = KiAuftrag.objects.filter

    def loeschen_dann(*args, **kw):
        if kw.get("pk") == a.pk and kw.get("status") == KiAuftragStatus.WARTEND:
            KiAuftrag.objects.all().delete()
        return echt_filter(*args, **kw)

    monkeypatch.setattr(KiAuftrag.objects, "filter", loeschen_dann)
    assert q.verarbeiten(jetzt=JETZT) == {}


def test_fehlschlag_nur_aus_laeuft(bereit):
    a = _neu()
    KiAuftrag.objects.filter(pk=a.pk).update(status="fertig")
    assert q._fehlschlag(a, "server", wiederholbar=True, jetzt=JETZT) == 0
    a.refresh_from_db()
    assert a.status == "fertig"


def test_verlorene_sperre_beendet_den_lauf(bereit):
    class Weg:
        def verlaengern(self, lease):
            return False

    h = Zaehler()
    q.handler_registrieren("tutor", h)
    _neu()
    assert q.verarbeiten(Weg(), jetzt=JETZT) == {"sperre_verloren": 1}
    assert h.aufrufe == []


# --- Job und Job-Sperre --------------------------------------------------------------------------


def test_job_laeuft_unter_sperre_und_protokolliert(bereit):
    q.handler_registrieren("tutor", Zaehler())
    _neu()
    call_command("ki_auftraege_verarbeiten", stdout=open("/dev/null", "w"))
    lauf = JobLauf.objects.get(name="ki_auftraege_verarbeiten")
    assert lauf.status == JobStatus.OK and lauf.info["fertig"] == 1
    assert not jobs.JobSperre.objects.filter(name="ki_auftraege_verarbeiten").exists()


def test_job_ueberspringt_bei_belegter_sperre(bereit):
    h = Zaehler()
    q.handler_registrieren("tutor", h)
    a = _neu()
    with jobs.sperre("ki_auftraege_verarbeiten", lease=timedelta(minutes=15)) as s:
        assert s is not None
        call_command("ki_auftraege_verarbeiten", stdout=open("/dev/null", "w"))
    lauf = JobLauf.objects.get(name="ki_auftraege_verarbeiten")
    assert lauf.status == JobStatus.UEBERSPRUNGEN and h.aufrufe == []
    a.refresh_from_db()
    assert a.status == "wartend"


def test_job_ohne_konfigurierte_ki_ist_leer(db):
    call_command("ki_auftraege_verarbeiten", stdout=open("/dev/null", "w"))
    lauf = JobLauf.objects.get(name="ki_auftraege_verarbeiten")
    assert lauf.status == JobStatus.OK and lauf.info == {}
