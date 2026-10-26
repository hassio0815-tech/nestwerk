"""AP32 Prognose und Kalibrierung: Sondertag-Prognose mit Grenzen, Ampel, Empfehlung per
Simulation, Übernahme mit Audit, Zugriff (Kind sieht nichts davon)."""

from datetime import timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from apps.kern import einstellungen
from apps.kern.models import AuditEintrag
from apps.sondertag import grenzen, prognose
from apps.spielregeln import selectors as spielregeln
from apps.spielregeln.models import Kalibrierung, Wochenauswertung
from apps.spielregeln.prognose import Basis

from .conftest import GO_LIVE

EINS = Decimal(1)
REGELN = grenzen.Regeln(go_live=GO_LIVE, max_pro_jahr=2, abstand=150)
STUFEN = (
    (2, "Uncommon", 2000, 20),
    (3, "Rare", 5000, 42),
    (4, "Epic", 9000, 64),
    (5, "Legendary", 14000, 90),
    (6, "God Mode", 20000, 120),
)


@pytest.fixture(autouse=True)
def prognose_einstellungen(db):
    for schluessel, wert in {
        "spielregeln.prognose_wochen": 6,
        "spielregeln.prognose_min_wochen": 3,
        "spielregeln.prognose_ziel_sondertage": 2,
        "spielregeln.prognose_kind_zeigen": True,
    }.items():
        einstellungen.setzen(schluessel, wert, akteur=None)


def _eingabe(xp_woche=175, quote=1, stufen=STUFEN, **extra):
    werte = {
        "heute": GO_LIVE,
        "basis": Basis(6, Fraction(xp_woche), Fraction(quote), True),
        "xp": 0,
        "aktive_wochen": 0,
        "stufen": stufen,
        "top_stufe": 6,
        "global_schwelle": EINS,
        "global_wochen": EINS,
        "schritte": tuple(prognose.Schritt(f"Rang {s[0]}", s[0], 6) for s in stufen[:-1]),
        "vorhanden": (),
        "regeln": REGELN,
        "mods_pro_woche": 1,
        "zyklus_laenge": 26,
        "ziel": 2,
    }
    return prognose.Eingabe(**{**werte, **extra})


def _grenzen_eingehalten(daten):
    daten = sorted(daten)
    assert all((b - a).days >= 150 for a, b in zip(daten, daten[1:], strict=False))
    for j in prognose._app_jahre(GO_LIVE, GO_LIVE):
        assert sum(1 for d in daten if j.enthaelt(d)) <= 2


def test_reproduzierbar():
    e = _eingabe()
    assert prognose.rechnen(e, EINS, EINS) == prognose.rechnen(e, EINS, EINS)


def test_startwerte_treffen_das_ziel_zwei_je_jahr():
    erg = prognose.rechnen(_eingabe(), EINS, EINS)
    # Rang 2: Woche 20 + 6 Wochen Zeitbremse; Rang 3: Woche 42 + 6 (Review Phase 2)
    assert erg.termine[0].datum == GO_LIVE + timedelta(weeks=26)
    assert erg.termine[1].datum == GO_LIVE + timedelta(weeks=48)
    assert [j.anzahl for j in erg.jahre] == [2, 2]
    assert erg.fehlbetrag == 0 and all(j.ampel == prognose.GRUEN for j in erg.jahre)


def test_grenzen_im_prognosewert_zwei_je_jahr_und_150_tage():
    schnell = tuple((s, n, 0, 0) for s, n, *_ in STUFEN)  # alles sofort erreicht
    erg = prognose.rechnen(_eingabe(stufen=schnell), EINS, EINS)
    daten = [t.datum for t in erg.termine]
    assert len(daten) == 4
    _grenzen_eingehalten(daten)
    assert erg.termine[0].datum == GO_LIVE + timedelta(weeks=6)
    assert erg.termine[1].datum == erg.termine[0].datum + timedelta(days=150)
    assert erg.termine[2].verschoben_tage > 0  # durch die Jahresgrenze verschoben
    assert [j.anzahl for j in erg.jahre] == [2, 2]


def test_vorhandene_sondertage_zaehlen_im_jahr_und_im_abstand():
    vorhanden = (GO_LIVE + timedelta(days=10),)
    erg = prognose.rechnen(_eingabe(vorhanden=vorhanden), EINS, EINS)
    _grenzen_eingehalten([*vorhanden, *(t.datum for t in erg.termine)])
    assert erg.termine[0].datum >= vorhanden[0] + timedelta(days=150)


def test_zu_wenig_historie_keine_termine():
    e = _eingabe(basis=Basis(1, Fraction(0), Fraction(0), False))
    erg = prognose.rechnen(e, EINS, EINS)
    assert erg.ziele == [] and erg.termine == []
    assert erg.fehlbetrag == 4  # nichts belegt


def test_ampel_und_abweichung():
    j = prognose.JahrZahl(1, GO_LIVE, GO_LIVE + timedelta(days=365), 2, 2)
    assert (j.ampel, j.abweichung) == ("gruen", 0)
    assert prognose.JahrZahl(1, GO_LIVE, GO_LIVE, 1, 2).ampel == "gelb"
    assert prognose.JahrZahl(1, GO_LIVE, GO_LIVE, 0, 2).ampel == "rot"


def test_empfehlung_mindestwochen_wenn_xp_nie_bindet():
    # unregelmäßiges Kind: jede 2. Woche aktiv, 175 XP je Kalenderwoche: Mindestwochen bremsen
    e = _eingabe(xp_woche=175, quote=Fraction(1, 2))
    erg = prognose.rechnen(e, EINS, EINS)
    assert erg.fehlbetrag > 0
    empf = prognose.empfehlen(e, EINS, EINS, erg)
    assert empf is not None and empf.knopf == prognose.WOCHEN and empf.faktor < 1
    neu = prognose.rechnen(e, EINS, empf.faktor)
    assert neu.fehlbetrag < erg.fehlbetrag
    assert "Mindestwochen" in empf.text


def test_empfehlung_schwelle_wenn_xp_bindet():
    e = _eingabe(xp_woche=60)
    erg = prognose.rechnen(e, EINS, EINS)
    assert any(z.engpass == "xp" for z in erg.ziele)
    empf = prognose.empfehlen(e, EINS, EINS, erg)
    assert empf is not None and empf.knopf == prognose.SCHWELLE and empf.faktor < 1
    assert prognose.rechnen(e, empf.faktor, EINS).fehlbetrag < erg.fehlbetrag


def test_keine_empfehlung_wenn_ziel_getroffen():
    e = _eingabe()
    assert prognose.empfehlen(e, EINS, EINS, prognose.rechnen(e, EINS, EINS)) is None


def test_faktor_wochen_im_ergebnis():
    e = _eingabe(xp_woche=175, quote=Fraction(1, 2))
    langsam = prognose.rechnen(e, EINS, EINS).ziele[0].wochen
    schneller = prognose.rechnen(e, EINS, Decimal("0.5")).ziele[0].wochen
    assert schneller < langsam


# --- mit Datenbank ----------------------------------------------------------------------------


def _verlauf(kind, n=6, xp=175):
    for i in range(n):
        montag = GO_LIVE + timedelta(weeks=i)
        Wochenauswertung.objects.create(
            kind=kind,
            iso_jahr=montag.isocalendar()[0],
            iso_woche=montag.isocalendar()[1],
            montag=montag,
            aktiv=True,
            neutral=False,
            pausentage=0,
            xp_woche=xp,
            wochenserie_danach=i + 1,
            aktive_wochen_gesamt=i + 1,
        )


def test_fuer_kind_zu_wenig_historie_hinweis(anna, uhr):
    z = prognose.fuer_kind(anna, GO_LIVE)
    assert not z.basis.genug and "Zu wenig Verlauf" in z.texte[0]
    assert z.naechster_rang is None and z.naechster_sondertag is None


def test_fuer_kind_mit_verlauf(anna, uhr):
    _verlauf(anna)
    heute = GO_LIVE + timedelta(weeks=6, days=2)
    z = prognose.fuer_kind(anna, heute)
    assert z.basis.genug and z.naechster_rang.stufe == 2
    assert z.naechster_sondertag is not None
    assert prognose.fuer_kind(anna, heute).ergebnis == z.ergebnis


def test_eltern_seite(eltern_client, anna, uhr):
    _verlauf(anna)
    uhr.stellen(GO_LIVE + timedelta(weeks=6, days=2))
    html = eltern_client.get("/eltern/prognose/").content.decode()
    assert "Prognose" in html and "Anna" in html and "data-pg-rang" in html
    assert "data-ampel" in html


def test_eltern_seite_zu_wenig_historie(eltern_client, anna):
    assert "data-pg-zuwenig" in eltern_client.get("/eltern/prognose/").content.decode()


def test_uebernahme_setzt_kalibrierung_mit_audit(eltern_client, anna, mama):
    antwort = eltern_client.post(
        "/eltern/prognose/uebernehmen/",
        {"kind": anna.pk, "knopf": "wochen", "faktor": "0.90", "notiz": "Empfehlung"},
    )
    assert antwort.status_code == 302
    assert spielregeln.kind_wochen_faktor(anna) == Decimal("0.90")
    a = AuditEintrag.objects.filter(aktion="kalibrierung.wochen_geaendert").get()
    assert a.akteur == mama and a.details["neu"] == "0.90"
    eltern_client.post(
        "/eltern/prognose/uebernehmen/", {"kind": anna.pk, "knopf": "schwelle", "faktor": "0.8"}
    )
    assert spielregeln.kind_faktor(anna) == Decimal("0.80")
    assert AuditEintrag.objects.filter(aktion="kalibrierung.geaendert").exists()


def test_uebernahme_mod_faktoren_je_kind(eltern_client, anna):
    eltern_client.post(
        "/eltern/prognose/uebernehmen/",
        {"kind": anna.pk, "knopf": "mods", "faktor_preis": "0,8", "faktor_bauzeit": "0,5"},
    )
    assert spielregeln.preis_faktor(anna) == Decimal("0.80")
    assert spielregeln.bauzeit_faktor(anna) == Decimal("0.50")


def test_fehlerhafter_faktor_wird_gemeldet(eltern_client, anna):
    antwort = eltern_client.post(
        "/eltern/prognose/uebernehmen/", {"kind": anna.pk, "knopf": "wochen", "faktor": "abc"}
    )
    assert antwort.status_code == 400 and "Faktor" in antwort.content.decode()
    assert not Kalibrierung.objects.filter(kind=anna).exists()


def test_kind_sieht_keine_eltern_info(kind_client, anna):
    assert kind_client.get("/eltern/prognose/").status_code in (302, 403, 404)
    antwort = kind_client.post(
        "/eltern/prognose/uebernehmen/", {"kind": anna.pk, "knopf": "wochen", "faktor": "0.5"}
    )
    assert antwort.status_code in (302, 403, 404)
    assert spielregeln.kind_wochen_faktor(anna) is None
    html = kind_client.get("/kind/").content.decode()
    for verboten in ("Engpass", "Prognose &amp; Kalibrierung", "Ampel", "Faktor"):
        assert verboten not in html
