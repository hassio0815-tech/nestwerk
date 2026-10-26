"""Familienziel (AP29): Fortschritt, Bedingung, Erfolg genau einmal, Abstimmung, Gleichstand,
Großziel, Wochenwechsel/Catch-up, Oberfläche."""

import threading
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection

from apps.ereignisse.models import Ereignis
from apps.familienziel import events, selectors, services
from apps.familienziel.models import (
    AbstimmungStatus,
    Familienbelohnung,
    Familienwoche,
    Grossziel,
    Stimme,
    WochenStatus,
)
from apps.kern import einstellungen
from apps.kern.models import JobLauf
from apps.kern.zeit import IsoWoche
from apps.punkte.models import Art
from apps.spielregeln import services as spielregeln

from .conftest import GO_LIVE, lok

W43, W44, W45, W46, W47 = (IsoWoche(2026, w) for w in (43, 44, 45, 46, 47))


def zeile(iso=W43):
    z, _ = services.woche_sicherstellen(iso)
    return z


def anzahl(typ):
    return Ereignis.objects.filter(typ_id=typ).count()


# --- Startwerte -------------------------------------------------------------------------------


def test_startwerte_exakt():
    assert [b.titel for b in Familienbelohnung.objects.order_by("reihenfolge")] == [
        "Pizza",
        "Spieleabend",
        "Kino",
        "Eis essen",
        "Grillen",
    ]
    assert not Familienbelohnung.objects.filter(ist_grossziel=True).exists()
    werte = einstellungen.werte(
        "familienziel.wochenziel_punkte",
        "familienziel.grossziel_serie",
        "familienziel.abstimmung_tag",
    )
    assert werte == {
        "familienziel.wochenziel_punkte": 450,
        "familienziel.grossziel_serie": 4,
        "familienziel.abstimmung_tag": 7,
    }


# --- Fortschritt ------------------------------------------------------------------------------


def test_fortschritt_zaehlt_alle_xp_und_korrekturen_mindern(anna, ben, mama, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    xp(anna, 100)
    xp(ben, 50, art=Art.SONDERPUNKTE, aktiv=False)
    xp(anna, 20, art=Art.SERIENBONUS, aktiv=False)
    st = selectors.stand(W43, 450)
    assert st.punkte == 170
    assert {b.kind.pk: b.xp for b in st.beitraege} == {anna.pk: 120, ben.pk: 50}
    xp(anna, -40, art=Art.KORREKTUR, aktiv=False, von=mama, begruendung="Fehler")
    assert selectors.stand(W43, 450).punkte == 130
    assert selectors.stand(W43, 450).prozent == 28


def test_beitraege_alphabetisch_ohne_wertung(anna, ben, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    xp(ben, 400)
    xp(anna, 1)
    namen = [b.kind.anzeigename for b in selectors.stand(W43, 450).beitraege]
    assert namen == ["Anna", "Ben"]


# --- Erfolg + Bedingung -----------------------------------------------------------------------


def test_erfolg_braucht_jedes_nicht_pausierte_kind(anna, ben, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    zeile()
    xp(anna, 500)
    z = Familienwoche.objects.get(iso_woche=43)
    assert z.status == WochenStatus.LAUFEND  # Ben hat noch keine Aufgabe
    assert selectors.ansicht().namen_offen == ["Ben"]
    xp(ben, 1)
    z.refresh_from_db()
    assert z.status == WochenStatus.ERREICHT and z.erreicht_am is not None


def test_pausiertes_kind_braucht_keine_aufgabe(anna, ben, mama, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    spielregeln.pause_setzen(ben, von=mama, ab=GO_LIVE)
    zeile()
    xp(anna, 450)
    assert Familienwoche.objects.get(iso_woche=43).status == WochenStatus.ERREICHT


def test_erfolg_meldet_eltern_und_jedes_kind(anna, ben, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    zeile()
    xp(anna, 450)
    xp(ben, 1)
    assert anzahl(events.ERREICHT) == 1
    assert anzahl(events.ERREICHT_KIND) == 2
    e = Ereignis.objects.get(typ_id=events.ERREICHT)
    assert e.daten["belohnung"] == "Wochenziel"
    # weitere Buchungen und der Job melden nichts mehr
    xp(anna, 50)
    services.sicherstellen()
    assert anzahl(events.ERREICHT) == 1


def test_korrektur_nach_erfolg_nimmt_ihn_nicht_zurueck(anna, mama, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    zeile()
    xp(anna, 450)
    xp(anna, -100, art=Art.KORREKTUR, aktiv=False, von=mama, begruendung="x")
    assert Familienwoche.objects.get(iso_woche=43).status == WochenStatus.ERREICHT
    assert selectors.ansicht().stand.punkte == 350


@pytest.mark.django_db(transaction=True)
def test_erfolg_genau_einmal_parallel(anna, ben, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    zeile()
    # Punkte/Aktivität ohne Handler vorbereiten: Handler kurz abschalten
    from apps.ereignisse import registry

    with registry.isoliert():
        xp(anna, 500)
        xp(ben, 5)
    assert Familienwoche.objects.get(iso_woche=43).status == WochenStatus.LAUFEND
    start = threading.Barrier(6)
    ergebnisse = [None] * 6

    def lauf(nr):
        try:
            start.wait()
            ergebnisse[nr] = services.erfolg_pruefen(W43, uhr.jetzt)
        except Exception as exc:  # noqa: BLE001
            ergebnisse[nr] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=lauf, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ergebnisse.count(True) == 1, ergebnisse
    assert all(e is True or e is False for e in ergebnisse), ergebnisse
    assert anzahl(events.ERREICHT) == 1
    assert anzahl(events.ERREICHT_KIND) == 2


# --- Abstimmung -------------------------------------------------------------------------------


def sonntag(uhr, stunde=12):
    return uhr.stellen(lok(2026, 10, 25, stunde))  # So in W43, Abstimmung für W44


def wahl(name):
    return Familienbelohnung.objects.get(titel=name).pk


def test_abstimmung_nur_im_fenster_und_stimme_aenderbar(anna, uhr):
    uhr.stellen(lok(2026, 10, 24, 12))  # Samstag
    with pytest.raises(services.FamilienzielFehler):
        services.stimme_abgeben(anna, wahl("Pizza"))
    sonntag(uhr)
    services.stimme_abgeben(anna, wahl("Pizza"))
    services.stimme_abgeben(anna, wahl("Kino"))
    assert Stimme.objects.get(kind=anna).belohnung.titel == "Kino"
    assert Stimme.objects.count() == 1
    with pytest.raises(services.FamilienzielFehler):
        services.stimme_abgeben(anna, 99999)
    uhr.stellen(lok(2026, 10, 26, 0, 1))
    with pytest.raises(services.FamilienzielFehler):
        services.stimme_abgeben(anna, wahl("Pizza"))


def test_mehrheit_gewinnt_nach_ende(anna, ben, uhr):
    sonntag(uhr)
    services.sicherstellen()
    assert anzahl(events.ABSTIMMUNG_OFFEN) == 2
    services.stimme_abgeben(anna, wahl("Kino"))
    services.stimme_abgeben(ben, wahl("Kino"))
    services.sicherstellen()
    assert Familienwoche.objects.get(iso_woche=44).abstimmung_status == AbstimmungStatus.OFFEN
    uhr.stellen(lok(2026, 10, 26, 0, 5))
    services.sicherstellen()
    w44 = Familienwoche.objects.get(iso_woche=44)
    assert (w44.abstimmung_status, w44.belohnung.titel) == (AbstimmungStatus.GESCHLOSSEN, "Kino")


def test_gleichstand_geht_an_eltern_und_wird_entschieden(anna, ben, mama, uhr):
    sonntag(uhr)
    services.sicherstellen()
    services.stimme_abgeben(anna, wahl("Pizza"))
    services.stimme_abgeben(ben, wahl("Grillen"))
    uhr.stellen(lok(2026, 10, 26, 0, 5))
    services.sicherstellen()
    services.sicherstellen()
    w44 = Familienwoche.objects.get(iso_woche=44)
    assert w44.abstimmung_status == AbstimmungStatus.GLEICHSTAND and w44.belohnung is None
    gleichstand = Ereignis.objects.filter(
        typ_id=events.ABSTIMMUNG_GLEICHSTAND, schluessel__endswith="2026-W44"
    )
    assert gleichstand.count() == 1
    assert "Grillen, Pizza" in gleichstand.get().daten["hinweis"]
    assert w44.pk in [w.pk for w in selectors.gleichstand_wochen()]
    services.woche_festlegen(w44, von=mama, belohnung=Familienbelohnung.objects.get(titel="Pizza"))
    w44.refresh_from_db()
    assert (w44.abstimmung_status, w44.belohnung.titel) == (
        AbstimmungStatus.ELTERN_ENTSCHIEDEN,
        "Pizza",
    )
    assert w44.pk not in [w.pk for w in selectors.gleichstand_wochen()]


def test_ohne_stimmen_gilt_vorwochen_belohnung_sonst_eltern(anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 19, 12))
    services.sicherstellen()  # W43 ohne Abstimmung, keine Vorwoche: Eltern entscheiden
    w43 = Familienwoche.objects.get(iso_woche=43)
    assert w43.abstimmung_status == AbstimmungStatus.GLEICHSTAND
    services.woche_festlegen(
        w43, von=mama, belohnung=Familienbelohnung.objects.get(titel="Eis essen")
    )
    sonntag(uhr)
    services.sicherstellen()
    uhr.stellen(lok(2026, 10, 26, 0, 5))
    services.sicherstellen()
    w44 = Familienwoche.objects.get(iso_woche=44)
    assert (w44.abstimmung_status, w44.belohnung.titel) == (
        AbstimmungStatus.GESCHLOSSEN,
        "Eis essen",
    )


def test_eltern_koennen_ziel_ueberschreiben_und_erfolg_greift(anna, mama, uhr, xp):
    uhr.stellen(lok(2026, 10, 21, 12))
    z = zeile()
    xp(anna, 100)
    services.woche_festlegen(z, von=mama, ziel_punkte=80)
    assert Familienwoche.objects.get(pk=z.pk).status == WochenStatus.ERREICHT
    with pytest.raises(services.FamilienzielFehler):
        services.woche_festlegen(z, von=mama, ziel_punkte=500)


# --- Großziel ---------------------------------------------------------------------------------


def erreicht(iso, status=WochenStatus.ERREICHT):
    z = zeile(iso)
    Familienwoche.objects.filter(pk=z.pk).update(
        status=status,
        erreicht_am=lok(2026, 10, 1, 12) if status == WochenStatus.ERREICHT else None,
        finalisiert_am=lok(2026, 10, 1, 12),
    )


def test_grossziel_nach_vier_in_folge_mit_neutraler_woche(anna, uhr, xp):
    uhr.stellen(lok(2026, 11, 12, 12))  # Do in W46
    erreicht(W43)
    erreicht(W44, WochenStatus.NEUTRAL)
    erreicht(W45)
    zeile(IsoWoche(2026, 46))
    erreicht(IsoWoche(2026, 42))
    assert services.grossziel_pruefen() is None  # 42, 43, 45 = 3
    assert selectors.serie() == 3
    xp(anna, 450, tag=lok(2026, 11, 12, 12).date())
    g = Grossziel.objects.get()
    assert g.ausloesende_woche.iso_woche == 46 and g.name == "Ausflug"
    assert anzahl(events.GROSSZIEL) == 1 and anzahl(events.GROSSZIEL_KIND) == 1
    assert selectors.serie() == 0
    services.grossziel_pruefen()
    assert Grossziel.objects.count() == 1


def test_verfehlte_woche_bricht_die_folge(anna, uhr):
    uhr.stellen(lok(2026, 11, 12, 12))
    for iso, status in (
        (IsoWoche(2026, 42), WochenStatus.ERREICHT),
        (W43, WochenStatus.ERREICHT),
        (W44, WochenStatus.VERFEHLT),
        (W45, WochenStatus.ERREICHT),
        (IsoWoche(2026, 46), WochenStatus.ERREICHT),
    ):
        erreicht(iso, status)
    assert services.grossziel_pruefen() is None
    assert selectors.serie() == 2


def test_gesenkte_serie_gibt_genau_ein_grossziel_an_der_juengsten_woche(anna, uhr):
    """Review AP31 (AP29-Prüfpunkt): Großziel wird aus der Historie abgeleitet. Senken die Eltern
    die nötige Folge unter die schon erreichte, entsteht genau ein Großziel (jüngste Woche),
    nicht rückwirkend eines je Teilfolge."""
    uhr.stellen(lok(2026, 11, 12, 12))
    for iso in (IsoWoche(2026, 42), W43, W44):
        erreicht(iso)
    assert services.grossziel_pruefen() is None
    einstellungen.setzen("familienziel.grossziel_serie", 1, akteur=None)
    for _ in range(3):
        services.grossziel_pruefen()
    g = Grossziel.objects.get()
    assert g.ausloesende_woche.iso_woche == 44
    assert selectors.serie() == 0


def test_catch_up_nach_ausfall_verliert_geschaffte_folge_nicht(anna, uhr):
    """Folge 4 geschafft, danach verfehlt, Prüfung erst danach (Catch-up): Großziel trotzdem."""
    uhr.stellen(lok(2026, 11, 26, 12))
    for iso in (IsoWoche(2026, 42), W43, W44, W45):
        erreicht(iso)
    erreicht(IsoWoche(2026, 46), WochenStatus.VERFEHLT)
    g = services.grossziel_pruefen()
    assert g is not None and g.ausloesende_woche.iso_woche == 45


# --- Wochenwechsel / Catch-up -----------------------------------------------------------------


def test_catch_up_idempotent_und_auswertung(anna, ben, uhr, xp):
    uhr.stellen(lok(2026, 10, 19, 12))
    services.sicherstellen()
    xp(anna, 500, tag=GO_LIVE)
    xp(ben, 1, tag=GO_LIVE)  # W43 erreicht (live)
    uhr.stellen(lok(2026, 11, 20, 12))  # fünf Wochen später
    erste = services.sicherstellen()
    zweite = services.sicherstellen()
    assert zweite["angelegt"] == 0 and zweite["abgeschlossen"] == 0
    assert erste["angelegt"] >= 4
    status = {z.iso_woche: z.status for z in Familienwoche.objects.all()}
    assert status[43] == WochenStatus.ERREICHT
    assert status[44] == status[45] == WochenStatus.VERFEHLT
    assert Familienwoche.objects.filter(finalisiert_am__isnull=False).count() >= 4
    assert Familienwoche.objects.count() == len(status)
    # Catch-up meldet keine alten Wochen als Ereignis
    assert anzahl(events.ABSTIMMUNG_GLEICHSTAND) == 2  # Startwoche + laufende Woche


def test_familienpause_macht_woche_neutral(anna, ben, mama, uhr):
    uhr.stellen(lok(2026, 10, 19, 12))
    spielregeln.pause_setzen(None, von=mama, ab=GO_LIVE, bis=GO_LIVE + timedelta(days=6))
    services.sicherstellen()
    uhr.stellen(lok(2026, 10, 27, 12))
    services.sicherstellen()
    assert Familienwoche.objects.get(iso_woche=43).status == WochenStatus.NEUTRAL


def test_job_command(anna, uhr):
    uhr.stellen(lok(2026, 10, 21, 12))
    call_command("familienwoche_sicherstellen")
    call_command("familienwoche_sicherstellen")
    laeufe = JobLauf.objects.filter(name="familienwoche_sicherstellen").order_by("id")
    assert [lauf.info["angelegt"] for lauf in laeufe] == [1, 0]


# --- Oberfläche -------------------------------------------------------------------------------


def test_tablet_zeigt_leiste_und_abstimmung(client, anna, ben, uhr, xp):
    uhr.stellen(lok(2026, 10, 25, 12))
    xp(anna, 120)
    html = client.get("/tablet/").content.decode()
    assert 'data-kachel="familienziel.leiste"' in html
    assert "120" in html and "450" in html
    assert "data-fz-abstimmung" in html and "Pizza" in html


def test_kind_stimmt_ueber_kachel_ab(kind_client, anna, uhr):
    sonntag(uhr)
    html = kind_client.get("/kind/").content.decode()
    assert "data-fz-abstimmung" in html
    r = kind_client.post("/kind/familienziel/abstimmen/", {"belohnung": wahl("Spieleabend")})
    assert r.status_code == 302
    assert Stimme.objects.get(kind=anna).belohnung.titel == "Spieleabend"


def test_eltern_seite_und_belohnungsliste(eltern_client, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 12))
    assert eltern_client.get("/eltern/familienziel/").status_code == 200
    r = eltern_client.post(
        "/eltern/familienziel/belohnung/neu/", {"titel": "Zoo", "symbol": "sonne"}
    )
    assert r.status_code == 302
    zoo = Familienbelohnung.objects.get(titel="Zoo")
    eltern_client.post(f"/eltern/familienziel/belohnung/{zoo.pk}/loeschen/")
    assert not Familienbelohnung.objects.filter(titel="Zoo").exists()
    w = Familienwoche.objects.get(iso_woche=43)
    r = eltern_client.post(
        f"/eltern/familienziel/woche/{w.pk}/", {"ziel_punkte": 300, "belohnung": wahl("Kino")}
    )
    assert r.status_code == 302
    w.refresh_from_db()
    assert (w.ziel_punkte, w.belohnung.titel) == (300, "Kino")


def test_kinder_duerfen_eltern_seite_nicht(kind_client):
    assert kind_client.get("/eltern/familienziel/").status_code in (302, 403)


def test_konfetti_popup_wird_gerendert(client, anna):
    from types import SimpleNamespace

    from django.template.loader import render_to_string

    p = SimpleNamespace(art=events.ERREICHT_KIND, titel="Geschafft! Pizza", text="Super")
    html = render_to_string("benachrichtigung/_popups.html", {"popups": [p]})
    assert "toast--familienziel" in html and "konfetti" in html and "Geschafft! Pizza" in html
    assert "<script" not in html


def test_abschluss_wie_spielregeln_auch_ueber_zeitumstellung():
    """Review AP31: gleicher Abschlusszeitpunkt wie die Wochenauswertung der Kinder (lokale
    Wanduhr). Puffer 168 h über das Sommerzeit-Ende (25.10.2026) -> Mo 26.10. 00:00 lokal."""
    from apps.familienziel import zeitplan
    from apps.kern import zeit

    einstellungen.setzen("spielregeln.puffer_stunden", 168, akteur=None)
    ab = zeitplan.abschluss_zeitpunkt(IsoWoche(2026, 42))
    lokal = zeit.lokal(ab)
    assert (lokal.date().isoformat(), lokal.hour) == ("2026-10-26", 0)
