"""Services: Aktivität, Storno, Pausen, Wochenauswertung (Puffer, Catch-up, Idempotenz),
Ereignisse, XP der Woche, Neuberechnung."""

from datetime import UTC, date, datetime

import pytest
from django.db import transaction

from apps.ereignisse.models import Ereignis
from apps.kern.models import AuditEintrag, Einstellung
from apps.kern.zeit import IsoWoche
from apps.spielregeln import events, selectors, services
from apps.spielregeln.models import Aktivitaet, KindStand, Pause, Wochenauswertung

from .conftest import lok

W43, W44, W45, W46 = (IsoWoche(2026, w) for w in (43, 44, 45, 46))
_nr = iter(range(1, 10_000))


def aktiv(kind, tag, *, storniert=False):
    """Historie direkt anlegen (ohne Nachführen)."""
    return Aktivitaet.objects.create(
        kind=kind, datum=tag, modul="test", referenz=str(next(_nr)), storniert=storniert
    )


def zeilen(kind):
    return [
        (f"{w.iso_jahr}-W{w.iso_woche}", w.aktiv, w.neutral, w.wochenserie_danach)
        for w in Wochenauswertung.objects.filter(kind=kind).order_by("montag")
    ]


def ereignisse(typ, kind=None):
    qs = Ereignis.objects.filter(typ_id=typ)
    return qs.filter(kind=kind) if kind is not None else qs


def erfassen(kind, meldedatum, bestaetigt, referenz=None):
    with transaction.atomic():
        return services.aktivitaet_erfassen(
            kind,
            meldedatum,
            modul="test",
            referenz=referenz or str(next(_nr)),
            erfasst_am=bestaetigt,
        )


# --- Wochenauswertung, Catch-up, Idempotenz --------------------------------------------------


def test_catch_up_ueber_mehrere_wochen_und_idempotent(anna, uhr):
    aktiv(anna, date(2026, 10, 20))
    aktiv(anna, date(2026, 10, 27))
    aktiv(anna, date(2026, 11, 10))
    uhr.stellen(lok(2026, 11, 18, 12))  # Mi W47: W43–W46 abgeschlossen

    ergebnis = services.wochen_sicherstellen()
    assert ergebnis["angelegt"] == 4 and ergebnis["finalisiert"] == 4
    assert zeilen(anna) == [
        ("2026-W43", True, False, 1),
        ("2026-W44", True, False, 2),
        ("2026-W45", False, False, 0),
        ("2026-W46", True, False, 1),
    ]
    stand = KindStand.objects.get(kind=anna)
    assert (stand.wochenserie, stand.aktive_wochen_gesamt, stand.rekord_wochenserie) == (1, 3, 2)
    assert stand.letzte_woche == "2026-W46"

    zweiter = services.wochen_sicherstellen()
    assert zweiter["angelegt"] == zweiter["geaendert"] == zweiter["finalisiert"] == 0
    assert ereignisse(events.WOCHE_AUSGEWERTET).count() == 4
    # Catch-up: nur die jüngste Woche meldet die Serie (keine Pop-up-Flut)
    assert list(ereignisse(events.SERIE_GESTIEGEN).values_list("daten__woche", flat=True)) == [
        "2026-W46"
    ]
    assert not ereignisse(events.SERIE_GERISSEN).exists()
    assert services.neu_berechnen() == []


def test_woche_im_puffer_ist_vorlaeufig_dann_final(anna, uhr):
    uhr.stellen(lok(2026, 10, 26, 22))  # Mo W44, W43 im Puffer
    erfassen(anna, date(2026, 10, 25), lok(2026, 10, 26, 21))  # Meldung So, Bestätigung Mo
    services.wochen_sicherstellen()
    w43 = Wochenauswertung.objects.get(kind=anna)
    assert (w43.aktiv, w43.finalisiert_am) == (True, None)
    assert KindStand.objects.get(kind=anna).wochenserie == 0  # Stand = letzte finalisierte
    assert not ereignisse(events.WOCHE_AUSGEWERTET).exists()

    uhr.stellen(lok(2026, 10, 27, 0, 10))  # Di 00:10: Abschluss
    services.wochen_sicherstellen()
    w43.refresh_from_db()
    assert w43.finalisiert_am == lok(2026, 10, 27, 0, 10)
    assert KindStand.objects.get(kind=anna).wochenserie == 1
    assert ereignisse(events.SERIE_GESTIEGEN, anna).get().daten["wochenserie"] == 1


def test_bestaetigung_nach_puffer_zaehlt_fuer_bestaetigungswoche(anna, uhr):
    uhr.stellen(lok(2026, 10, 27, 0, 30))
    a = erfassen(anna, date(2026, 10, 25), lok(2026, 10, 27, 0, 30))
    assert a.datum == date(2026, 10, 27)
    services.wochen_sicherstellen()
    assert zeilen(anna) == [("2026-W43", False, False, 0)]
    assert selectors.stand(anna).woche_aktiv is True


def test_laufende_woche_bricht_serie_nie(anna, uhr):
    aktiv(anna, date(2026, 10, 20))
    uhr.stellen(lok(2026, 10, 30, 12))  # Fr W44 ohne Aufgabe
    stand = selectors.stand(anna)
    assert (stand.wochenserie, stand.woche_aktiv) == (1, False)
    assert selectors.wochenserie_nach(anna, W44) == 1  # laufend, noch nicht aktiv: neutral
    aktiv(anna, date(2026, 10, 30))
    assert selectors.wochenserie_nach(anna, W44) == 2  # AP21: Vorwoche + 1


def test_serie_gerissen_wird_gemeldet(anna, uhr):
    aktiv(anna, date(2026, 10, 20))
    uhr.stellen(lok(2026, 10, 28, 12))
    services.wochen_sicherstellen()
    uhr.stellen(lok(2026, 11, 3, 1))  # W44 (ohne Aufgabe) abgeschlossen
    services.wochen_sicherstellen()
    gerissen = ereignisse(events.SERIE_GERISSEN, anna).get()
    assert gerissen.daten == {"woche": "2026-W44", "wochenserie": 0, "vorher": 1}
    services.wochen_sicherstellen()
    assert ereignisse(events.SERIE_GERISSEN).count() == 1


def test_ohne_go_live_keine_wochen(anna, uhr):
    Einstellung.objects.filter(schluessel="allgemein.go_live_datum").delete()
    aktiv(anna, date(2026, 10, 20))
    uhr.stellen(lok(2026, 11, 18, 12))
    services.wochen_sicherstellen()
    assert not Wochenauswertung.objects.exists()
    assert KindStand.objects.get(kind=anna).wochenserie == 0


# --- Storno ----------------------------------------------------------------------------------


def test_storno_korrigiert_auch_abgeschlossene_wochen(anna, uhr):
    aktiv(anna, date(2026, 10, 20))
    zweite = erfassen(anna, date(2026, 10, 27), lok(2026, 10, 27, 18), referenz="x1")
    aktiv(anna, date(2026, 11, 4))
    uhr.stellen(lok(2026, 11, 11, 12))
    services.wochen_sicherstellen()
    assert [z[3] for z in zeilen(anna)] == [1, 2, 3]

    with transaction.atomic():
        assert services.aktivitaet_stornieren(modul="test", referenz="x1") is True
        assert services.aktivitaet_stornieren(modul="test", referenz="x1") is False
    zweite.refresh_from_db()
    assert zweite.storniert
    assert [z[1:] for z in zeilen(anna)] == [(True, False, 1), (False, False, 0), (True, False, 1)]
    assert KindStand.objects.get(kind=anna).aktive_wochen_gesamt == 2
    assert services.neu_berechnen() == []


def test_erfassen_ist_idempotent_und_meldet_aktivitaet(anna, uhr):
    uhr.stellen(lok(2026, 10, 21, 12))
    a = erfassen(anna, date(2026, 10, 21), lok(2026, 10, 21, 11), referenz="r1")
    b = erfassen(anna, date(2026, 10, 21), lok(2026, 10, 21, 11), referenz="r1")
    assert a.pk == b.pk and Aktivitaet.objects.count() == 1
    daten = ereignisse(events.AKTIVITAET_ERFASST, anna).get().daten
    assert (daten["datum"], daten["tagesserie"]) == ("2026-10-21", 1)


def test_erfassen_nur_fuer_kinder(mama):
    with pytest.raises(services.SpielregelnFehler), transaction.atomic():
        services.aktivitaet_erfassen(mama, date(2026, 10, 21), modul="t", referenz="1")


# --- Pausen ----------------------------------------------------------------------------------


def test_rueckwirkende_pause_rettet_serie_mit_audit_und_ereignis(anna, mama, uhr):
    aktiv(anna, date(2026, 10, 20))
    aktiv(anna, date(2026, 11, 3))
    uhr.stellen(lok(2026, 11, 11, 12))
    services.wochen_sicherstellen()
    assert [z[3] for z in zeilen(anna)] == [1, 0, 1]

    pause = services.pause_setzen(
        anna, von=mama, ab=date(2026, 10, 28), bis=date(2026, 10, 28), grund="krank"
    )
    assert [z[1:] for z in zeilen(anna)] == [(True, False, 1), (False, True, 1), (True, False, 2)]
    eintrag = AuditEintrag.objects.get(aktion="pause.gesetzt")
    assert (eintrag.akteur, eintrag.kind, eintrag.details["grund"]) == (mama, anna, "krank")
    gestartet = ereignisse(events.PAUSE_GESTARTET, anna).get()
    assert gestartet.daten["zeitraum"] == "am 28.10.2026" and gestartet.akteur == mama
    assert pause.erstellt_von == mama and services.neu_berechnen() == []


def test_familienpause_gilt_fuer_alle_kinder(anna, ben, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    pause = services.pause_setzen(None, von=mama)
    assert pause.familie and pause.von == date(2026, 10, 21) and pause.bis is None
    assert ereignisse(events.PAUSE_GESTARTET).count() == 2
    assert selectors.aktuelle_pause(anna) == pause and selectors.ist_pausiert(ben)
    assert selectors.woche_pausiert(ben, W43)
    with pytest.raises(services.SpielregelnFehler, match="laufende Pause"):
        services.pause_setzen(None, von=mama)
    # Kind-Pause zusätzlich erlaubt (eigenes Ziel)
    services.pause_setzen(anna, von=mama)
    assert services.pausen_beenden_fuer(None, von=mama) == 1
    assert selectors.aktuelle_pause(anna).kind == anna
    # heute begonnen und beendet: der Tag bleibt pausiert (bis = von)
    assert selectors.aktuelle_pause(ben).familie


def test_pause_beenden_standard_gestern_und_geplante_loeschen(anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 19, 9))
    pause = services.pause_setzen(anna, von=mama)
    uhr.stellen(lok(2026, 10, 23, 9))
    services.pause_beenden(pause, von=mama)
    pause.refresh_from_db()
    assert pause.bis == date(2026, 10, 22)
    assert not selectors.ist_pausiert(anna)
    hinweis = ereignisse(events.PAUSE_BEENDET, anna).get().daten["hinweis"]
    assert hinweis == "Deine Pause endet am 22.10.2026."
    with pytest.raises(services.SpielregelnFehler, match="vorbei"):
        services.pause_beenden(pause, von=mama)

    geplant = services.pause_setzen(anna, von=mama, ab=date(2026, 11, 2), bis=date(2026, 11, 6))
    services.pause_beenden(geplant, von=mama)  # noch nicht begonnen -> gelöscht
    assert not Pause.objects.filter(pk=geplant.pk).exists()
    assert AuditEintrag.objects.filter(aktion="pause.geloescht").count() == 1
    assert ereignisse(events.PAUSE_BEENDET, anna).count() == 2


def test_pause_regeln(anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    with pytest.raises(services.SpielregelnFehler, match="nur Eltern"):
        services.pause_setzen(anna, von=anna)
    with pytest.raises(services.SpielregelnFehler, match="vor dem Beginn"):
        services.pause_setzen(anna, von=mama, ab=date(2026, 10, 22), bis=date(2026, 10, 21))
    with pytest.raises(services.SpielregelnFehler, match="zu lang"):
        services.pause_setzen(anna, von=mama, grund="x" * 121)
    pause = services.pause_setzen(anna, von=mama)
    with pytest.raises(services.SpielregelnFehler, match="nicht gelöscht"):
        services.pause_loeschen(pause, von=mama)
    # Hausautomation (später, Quelle ohne Elternteil)
    services.pause_setzen(None, von=None, quelle="hausautomation")
    assert Pause.objects.filter(quelle="hausautomation", erstellt_von=None).count() == 1


def test_pause_startet_heute_und_endet_heute_bleibt_ein_tag(anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    pause = services.pause_setzen(anna, von=mama)
    services.pause_beenden(pause, von=mama)
    pause.refresh_from_db()
    assert pause.bis == pause.von == date(2026, 10, 21)


# --- XP der Woche ----------------------------------------------------------------------------


def test_xp_woche_folgt_spaeten_buchungen(anna, mama, uhr):
    from apps.punkte import services as punkte

    aktiv(anna, date(2026, 10, 20))
    uhr.stellen(lok(2026, 10, 28, 12))
    with transaction.atomic():
        punkte.buchen(
            anna, punkte.Art.AUFGABE, 10, schluessel="t:1", quelle_modul="test",
            bezugsdatum=date(2026, 10, 20), von=mama,
        )  # fmt: skip
    services.wochen_sicherstellen()
    assert Wochenauswertung.objects.get(kind=anna).xp_woche == 10
    with transaction.atomic():
        punkte.buchen(
            anna, punkte.Art.SONDERPUNKTE, 5, schluessel="t:2", quelle_modul="test",
            bezugsdatum=date(2026, 10, 25), begruendung="toll", von=mama,
        )  # fmt: skip
    assert Wochenauswertung.objects.get(kind=anna).xp_woche == 15
    assert services.neu_berechnen() == []


# --- Neuberechnung ---------------------------------------------------------------------------


def test_neuberechnung_findet_und_behebt_abweichung(anna, uhr):
    aktiv(anna, date(2026, 10, 20))
    uhr.stellen(lok(2026, 11, 4, 12))
    assert [a.feld for a in services.neu_berechnen()] == ["noch nicht ausgewertet"]
    services.wochen_sicherstellen()
    Wochenauswertung.objects.filter(kind=anna, iso_woche=43).update(wochenserie_danach=7)
    KindStand.objects.filter(kind=anna).update(tagesserie=9)
    abw = services.neu_berechnen()
    assert {(a.wo, a.feld, a.gespeichert, a.berechnet) for a in abw} == {
        ("2026-W43", "wochenserie_danach", 7, 1),
        ("stand", "tagesserie", 9, 0),
    }
    services.neu_berechnen(schreiben=True)
    assert services.neu_berechnen() == []


def test_aktivitaeten_aus_ereignissen_nachtragen(anna, uhr):
    from apps.ereignisse import services as ereignis_services

    with transaction.atomic():
        for instanz, melde, best in ((1, "2026-10-25", "2026-10-27T08:00:00+01:00"),
                                     (2, "2026-10-21", "2026-10-21T18:00:00+02:00"),
                                     (3, "2026-10-22", "2026-10-22T18:00:00+02:00")):  # fmt: skip
            ereignis_services.veroeffentlichen(
                "aufgabe.erledigt",
                kind=anna,
                daten={"instanz_id": instanz, "bezugsdatum": melde, "bestaetigt_am": best},
            )
        ereignis_services.veroeffentlichen("aufgabe.korrigiert", kind=anna, daten={"instanz_id": 3})
    assert services.aktivitaeten_nachtragen() == {"angelegt": 3, "storniert": 1}
    assert services.aktivitaeten_nachtragen() == {"angelegt": 0, "storniert": 0}
    tage = dict(Aktivitaet.objects.values_list("referenz", "datum"))
    assert tage == {"1": date(2026, 10, 27), "2": date(2026, 10, 21), "3": date(2026, 10, 22)}
    assert Aktivitaet.objects.get(referenz="3").storniert


def test_datum_feld_ist_lokal(anna, uhr):
    """Bestätigung So 23:30 lokal (UTC 22:30) gehört zum Sonntag."""
    uhr.stellen(datetime(2026, 10, 25, 22, 30, tzinfo=UTC))
    a = erfassen(anna, date(2026, 10, 25), lok(2026, 10, 25, 23, 30))
    assert a.datum == date(2026, 10, 25)


def test_pausenformular_datum_im_iso_format(uhr):
    """Review AP31: <input type=date> verlangt JJJJ-MM-TT; das deutsche Format erzeugte eine
    Browser-Warnung und ein leeres Feld."""
    from apps.spielregeln.forms import PauseForm

    uhr.stellen(lok(2026, 10, 24, 12))
    html = str(PauseForm()["von"])
    assert 'value="2026-10-24"' in html
