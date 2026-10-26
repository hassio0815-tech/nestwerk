"""AP23 Abzeichen- und Meilenstein-Engine: Startwerte (E12), Verleihung als Fakt (bleibt bei
Schwellenänderung/Deaktivierung), Auslöser (Aktivität, Wochenabschluss, Rangaufstieg, Job),
Bereiche (Quartal, Rang), Erweiterbarkeit per Test-Metrik, Meilenstein-UND-Logik, Catch-up,
Oberflächen."""

from datetime import date, timedelta

import pytest
from django.db import transaction

from apps.ereignisse.models import Ereignis
from apps.kern.models import AuditEintrag
from apps.punkte import services as punkte
from apps.punkte.models import Art, Buchung
from apps.spielregeln import selectors, services
from apps.spielregeln.models import (
    AbzeichenDefinition,
    AbzeichenVerleihung,
    Aktivitaet,
    MeilensteinErreicht,
    Pause,
)

from . import testmodul_lernen as lernen
from .conftest import GO_LIVE, lok

_zaehler = iter(range(10**6))


def _schluessel(kind):
    return sorted((v.abzeichen.schluessel, v.bereich) for v in selectors.verleihungen(kind))


def _wochen(kind, uhr, anzahl, *, ohne=()):
    """Aktive Wochen ab Go-live (Woche ``i`` in ``ohne`` ausgelassen); Uhr = Mittwoch danach."""
    for i in range(anzahl):
        if i in ohne:
            continue
        Aktivitaet.objects.create(
            kind=kind, datum=GO_LIVE + timedelta(weeks=i, days=1), modul="t", referenz=f"w{i}"
        )
    uhr.stellen(lok(2026, 10, 21, 12) + timedelta(weeks=anzahl))
    services.wochen_sicherstellen(kind)


def _abzeichen_ereignisse(kind):
    return Ereignis.objects.filter(typ_id="abzeichen.verliehen", kind=kind)


# --- Startwerte -------------------------------------------------------------------------------


def test_startwerte_exakt_entscheidung_12(db):
    """E12: Tagesserie 7/14/30; Wochenserie 1/2/4/8/12/24/48; Quartal voll aktiv; je Rang."""
    zeilen = list(
        AbzeichenDefinition.objects.exclude(gruppe="ruhmeshalle").order_by("reihenfolge")
    )  # Ruhmeshalle (P3-A, Modul avatar) hat eigene Tests
    assert all(z.aktiv and z.modul == "spielregeln" and z.vergleich == ">=" for z in zeilen)

    def gruppe(name):
        return [(z.metrik, z.schwelle, z.wiederholbar) for z in zeilen if z.gruppe == name]

    assert gruppe("tagesserie") == [("rekord_tagesserie", n, "einmalig") for n in (7, 14, 30)]
    assert gruppe("wochenserie") == [
        ("rekord_wochenserie", n, "einmalig") for n in (1, 2, 4, 8, 12, 24, 48)
    ]
    assert gruppe("quartal") == [("quartal_voll_aktiv", 1, "bereich")]
    assert gruppe("rang") == [("rang", 2, "bereich")]  # ab Rang 2 = jeder Aufstieg
    assert len(zeilen) == 12
    assert all(z.symbol == z.schluessel for z in zeilen)  # AP28: eine Grafik je Schlüssel


# --- Auslöser und Fakten ----------------------------------------------------------------------


def test_wochenserie_beim_wochenabschluss_einmal(anna, uhr):
    _wochen(anna, uhr, 2)
    assert _schluessel(anna) == [("wochenserie-1", ""), ("wochenserie-2", "")]
    ereignis = _abzeichen_ereignisse(anna).get()  # ein Pop-up für beide (keine Flut)
    assert ereignis.daten["anzahl"] == 2
    assert ereignis.daten["abzeichen"] == "Wochenserie 1 (+1 weitere)"
    services.wochen_sicherstellen()
    services.abzeichen_alle_pruefen()
    assert AbzeichenVerleihung.objects.count() == 2 and _abzeichen_ereignisse(anna).count() == 1
    assert not Buchung.objects.exists()  # Abzeichen geben nie Punkte


def test_tagesserie_7_bei_aktivitaet(anna, uhr):
    for i in range(7):
        uhr.stellen(lok(2026, 10, 19, 18) + timedelta(days=i))
        with transaction.atomic():
            services.aktivitaet_erfassen(anna, GO_LIVE + timedelta(days=i), modul="t", referenz=i)
        if i == 5:
            assert _schluessel(anna) == []
    assert _schluessel(anna) == [("tagesserie-7", "")]
    daten = _abzeichen_ereignisse(anna).get().daten
    assert daten["abzeichen"] == "Tagesserie 7" and daten["symbol"] == "tagesserie-7"
    verleihung = AbzeichenVerleihung.objects.get()
    assert (verleihung.wert, verleihung.schwelle) == (7, 7)


def test_verleihung_bleibt_bei_schwellenerhoehung_und_deaktivierung(anna, mama, uhr):
    _wochen(anna, uhr, 1)
    d = AbzeichenDefinition.objects.get(schluessel="wochenserie-1")
    with transaction.atomic():
        services.abzeichen_speichern(
            d,
            von=mama,
            name="Erste Woche",
            beschreibung=d.beschreibung,
            metrik="rekord_wochenserie",
            schwelle=5,
        )
    services.wochen_sicherstellen()
    assert _schluessel(anna) == [("wochenserie-1", "")]
    v = AbzeichenVerleihung.objects.get()
    assert v.schwelle == 1  # Snapshot
    with transaction.atomic():
        services.abzeichen_aktiv_setzen(d, False, von=mama)
    services.abzeichen_alle_pruefen()
    vitrine = selectors.vitrine(anna)
    assert [a.titel for a in vitrine.verdient] == ["Erste Woche"]  # umbenannt, bleibt sichtbar
    eintrag = AuditEintrag.objects.filter(aktion="abzeichen.geaendert").first()
    assert eintrag.details["neu"] == {"name": "Erste Woche", "schwelle": 5}


def test_niedrigere_schwelle_verleiht_sofort(anna, mama, uhr):
    _wochen(anna, uhr, 1)
    d = AbzeichenDefinition.objects.get(schluessel="tagesserie-7")
    with transaction.atomic():
        services.abzeichen_speichern(
            d,
            von=mama,
            name=d.name,
            beschreibung=d.beschreibung,
            metrik="rekord_tagesserie",
            schwelle=1,
        )
    assert ("tagesserie-7", "") in _schluessel(anna)


def test_abzeichen_je_rangaufstieg(anna, uhr):
    with transaction.atomic():
        punkte.buchen(anna, Art.AUFGABE, 9500, schluessel="t:1", quelle_modul="test", von=None)
    services.raenge_pruefen(anna, aktive_wochen=70)  # rang.aufgestiegen -> synchron geprüft
    assert _schluessel(anna) == [
        ("rangaufstieg", "rang-2"),
        ("rangaufstieg", "rang-3"),
        ("rangaufstieg", "rang-4"),
    ]
    titel = [a.titel for a in selectors.vitrine(anna).verdient]
    assert titel == ["Rangaufstieg · Uncommon", "Rangaufstieg · Rare", "Rangaufstieg · Epic"]


def test_quartal_voll_aktiv_mit_pause(anna, uhr):
    """Q4 2026 beginnt vor Go-live (zählt nicht); Q1 2027 voll aktiv, W05 pausiert (neutral)."""
    pause_woche = 15  # 2027-W05 (Woche 0 = 2026-W43)
    assert GO_LIVE + timedelta(weeks=pause_woche) == date(2027, 2, 1)
    Pause.objects.create(
        kind=anna,
        von=date(2027, 2, 1),
        bis=date(2027, 2, 7),
        quelle="eltern",
    )
    _wochen(anna, uhr, 23, ohne=(pause_woche,))  # bis 2027-W12, Uhr 2027-03-31
    assert selectors.abgeschlossene_quartale(anna) == [(2026, 4, False), (2027, 1, True)]
    assert ("quartal-voll-aktiv", "2027-Q1") in _schluessel(anna)
    assert not any(b == "2026-Q4" for _, b in _schluessel(anna))
    v = AbzeichenVerleihung.objects.get(bereich="2027-Q1")
    assert v.bereich_bezeichnung == "Q1 2027"
    assert ("wochenserie-12", "") in _schluessel(anna)
    assert ("wochenserie-24", "") not in _schluessel(anna)


def test_catch_up_idempotent_und_neuberechnung(anna, uhr):
    _wochen(anna, uhr, 2)
    AbzeichenVerleihung.objects.filter(abzeichen__schluessel="wochenserie-2").delete()
    assert services.abzeichen_alle_pruefen() == {
        "abzeichen_verliehen": 1,
        "meilensteine_erreicht": 0,
    }
    assert services.abzeichen_alle_pruefen()["abzeichen_verliehen"] == 0
    services.neu_berechnen(schreiben=True)
    services.neu_berechnen(schreiben=True)
    assert AbzeichenVerleihung.objects.count() == 2
    assert services.neu_berechnen() == []


def test_unbekannte_metrik_wird_uebersprungen(anna, uhr):
    AbzeichenDefinition.objects.create(
        schluessel="weg", name="Weg", symbol="weg", metrik="modul_entfernt.x", schwelle=0
    )
    _wochen(anna, uhr, 1)
    assert _schluessel(anna) == [("wochenserie-1", "")]


def test_nur_kinder(mama, db):
    assert services.abzeichen_pruefen(mama).verliehen == []


# --- Erweiterbarkeit: neue Metrik ohne Engine-Änderung ----------------------------------------


def test_neue_metrik_aus_test_modul(anna, ben, uhr):
    with lernen.aktiv():
        AbzeichenDefinition.objects.create(
            schluessel="vokabeln-100",
            name="Vokabel-Profi",
            symbol="vokabeln-100",
            gruppe="lernen",
            metrik="lernen_test.vokabeln",
            schwelle=100,
            modul=lernen.MODUL,
        )
        lernen.setzen("lernen_test.vokabeln", anna, 99)
        services.abzeichen_pruefen(anna)
        assert _schluessel(anna) == []
        naechstes = selectors.vitrine(anna).naechste
        assert [(n.abzeichen.schluessel, n.wert, n.ziel) for n in naechstes][0] == (
            "vokabeln-100",
            99,
            100,
        )
        lernen.setzen("lernen_test.vokabeln", anna, 100)
        services.abzeichen_pruefen(anna)
        services.abzeichen_pruefen(ben)
        assert _schluessel(anna) == [("vokabeln-100", "")] and _schluessel(ben) == []
        assert selectors.symbol(AbzeichenDefinition.objects.get(schluessel="vokabeln-100")).icon
    # Modul weg: Fakt bleibt, Engine läuft weiter
    services.abzeichen_pruefen(anna)
    assert _schluessel(anna) == [("vokabeln-100", "")]


def test_neue_metrik_mit_bereichen(anna, uhr):
    with lernen.aktiv():
        AbzeichenDefinition.objects.create(
            schluessel="ausbau-voll",
            name="Voll ausgebaut",
            symbol="ausbau-voll",
            metrik="lernen_test.ausbaustufe",
            schwelle=6,
            wiederholbar="bereich",
        )
        lernen.setzen(
            "lernen_test.ausbaustufe.bereiche",
            anna,
            {"seltenheit-2": (6, "Uncommon"), "seltenheit-3": 4},
        )
        services.abzeichen_pruefen(anna)
        assert _schluessel(anna) == [("ausbau-voll", "seltenheit-2")]
        lernen.setzen("lernen_test.ausbaustufe.bereiche", anna, {"seltenheit-3": 6})
        services.abzeichen_pruefen(anna)
        assert _schluessel(anna) == [
            ("ausbau-voll", "seltenheit-2"),
            ("ausbau-voll", "seltenheit-3"),
        ]


# --- Meilensteine -----------------------------------------------------------------------------


def test_meilenstein_und_logik(anna, uhr):
    with lernen.aktiv():
        regel = services.meilenstein_anlegen(
            "test-rang-2-ausgebaut",
            "Rang 2 voll ausgebaut",
            [
                {"metrik": "lernen_test.stufe", "vergleich": ">=", "wert": 2},
                {"metrik": "lernen_test.ausbaustufe", "wert": 6},
            ],
            belohnungsart="sondertag",
            modul="test",
        )
        lernen.setzen("lernen_test.stufe", anna, 2)
        lernen.setzen("lernen_test.ausbaustufe", anna, 5)
        assert services.abzeichen_pruefen(anna).erreicht == []
        assert selectors.meilenstein_erreicht(anna, "test-rang-2-ausgebaut") is None
        stand = selectors.meilenstein_stand(anna, "test-rang-2-ausgebaut")
        assert [(s.metrik, s.ziel, s.wert, s.erfuellt) for s in stand] == [
            ("lernen_test.stufe", 2, 2, True),
            ("lernen_test.ausbaustufe", 6, 5, False),
        ]
        lernen.setzen("lernen_test.stufe", anna, 1)
        lernen.setzen("lernen_test.ausbaustufe", anna, 6)
        assert services.abzeichen_pruefen(anna).erreicht == []  # nur eine Bedingung
        lernen.setzen("lernen_test.stufe", anna, 3)
        uhr.weiter(hours=1)
        neu = services.abzeichen_pruefen(anna).erreicht
        assert len(neu) == 1
        fakt = selectors.meilenstein_erreicht(anna, "test-rang-2-ausgebaut")
        assert fakt.werte == {"lernen_test.stufe": 3, "lernen_test.ausbaustufe": 6}
        assert fakt.erreicht_am == uhr.jetzt
        ereignis = Ereignis.objects.get(typ_id="meilenstein.erreicht")
        assert fakt.ereignis == ereignis
        assert ereignis.daten["belohnungsart"] == "sondertag"
        assert ereignis.daten["regel"] == regel.schluessel and ereignis.daten["bereich"] == ""
        # Werte sinken: Fakt bleibt, kein zweites Ereignis
        lernen.setzen("lernen_test.ausbaustufe", anna, 0)
        services.abzeichen_pruefen(anna)
        services.abzeichen_pruefen(anna)
        assert MeilensteinErreicht.objects.count() == 1
        assert Ereignis.objects.filter(typ_id="meilenstein.erreicht").count() == 1
        # idempotentes Anlegen
        assert (
            services.meilenstein_anlegen(
                "test-rang-2-ausgebaut", "anders", [{"metrik": "rang", "wert": 9}], modul="x"
            ).name
            == "Rang 2 voll ausgebaut"
        )


def test_meilenstein_je_bereich_und_ohne_popup(anna, uhr):
    with lernen.aktiv():
        services.meilenstein_anlegen(
            "test-ausbau",
            "Ausbaustufe 6",
            [
                {"metrik": "lernen_test.ausbaustufe", "wert": 6},
                {"metrik": "lernen_test.stufe", "wert": 1},
            ],
            wiederholbar="bereich",
            modul="test",
        )
        lernen.setzen("lernen_test.stufe", anna, 1)
        lernen.setzen(
            "lernen_test.ausbaustufe.bereiche", anna, {"seltenheit-2": 6, "seltenheit-3": 2}
        )
        services.abzeichen_pruefen(anna, melden=False)
        assert [f.bereich for f in selectors.meilensteine_erreicht(anna)] == ["seltenheit-2"]
        # meilenstein.erreicht auch bei melden=False (Folgemodule gründen darauf Ansprüche)
        assert Ereignis.objects.filter(typ_id="meilenstein.erreicht").count() == 1
        lernen.setzen("lernen_test.stufe", anna, 0)
        lernen.setzen("lernen_test.ausbaustufe.bereiche", anna, {"seltenheit-3": 6})
        services.abzeichen_pruefen(anna)
        assert len(selectors.meilensteine_erreicht(anna)) == 1  # UND: Stufe fehlt jetzt


@pytest.mark.parametrize(
    "bedingungen, fehler",
    [
        ([], "Mindestens"),
        ([{"metrik": "gibt_es_nicht", "wert": 1}], "Unbekannte Metrik"),
        ([{"metrik": "rang", "vergleich": "<>", "wert": 1}], "Vergleich"),
        ([{"metrik": "rang", "wert": -1}], "Wert"),
    ],
)
def test_meilenstein_bedingungen_geprueft(db, bedingungen, fehler):
    with pytest.raises(services.AbzeichenFehler, match=fehler):
        services.meilenstein_anlegen("x", "X", bedingungen, modul="test")


def test_meilenstein_bereich_braucht_bereichsmetrik(db):
    with pytest.raises(services.AbzeichenFehler, match="Bereich"):
        services.meilenstein_anlegen(
            "x", "X", [{"metrik": "wochenserie", "wert": 1}], wiederholbar="bereich", modul="t"
        )


# --- Eltern-Pflege ----------------------------------------------------------------------------


def test_eltern_legen_abzeichen_an(anna, mama, uhr):
    _wochen(anna, uhr, 3)
    with transaction.atomic():
        d = services.abzeichen_speichern(
            None,
            von=mama,
            name="Drei Wochen aktiv",
            metrik="aktive_wochen",
            schwelle="3",
            beschreibung="Drei aktive Wochen insgesamt.",
        )
    assert (d.schluessel, d.symbol, d.gruppe) == (
        "drei-wochen-aktiv",
        "drei-wochen-aktiv",
        "wochenserie",
    )
    assert ("drei-wochen-aktiv", "") in _schluessel(anna)  # sofort geprüft
    with pytest.raises(services.AbzeichenFehler, match="Bereiche"):
        services.abzeichen_speichern(
            None, von=mama, name="X", metrik="aktive_wochen", schwelle=1, wiederholbar="bereich"
        )
    with pytest.raises(services.AbzeichenFehler, match="Metrik"):
        services.abzeichen_speichern(None, von=mama, name="X", metrik="nix", schwelle=1)
    with pytest.raises(services.AbzeichenFehler, match="Eltern"):
        services.abzeichen_speichern(None, von=anna, name="X", metrik="rang", schwelle=1)


# --- Oberflächen ------------------------------------------------------------------------------


def test_kind_vitrine_kachel(kind_client, anna, uhr):
    for i in range(7):
        Aktivitaet.objects.create(
            kind=anna, datum=GO_LIVE + timedelta(days=i), modul="t", referenz=f"d{i}"
        )
    uhr.stellen(lok(2026, 10, 25, 20))
    services.wochen_sicherstellen(anna)
    html = kind_client.get("/kind/dungeon/").content.decode()
    assert 'data-kachel="spielregeln.kind_abzeichen"' in html
    assert 'data-abzeichen="tagesserie-7"' in html and 'data-symbol="tagesserie-7"' in html
    assert 'data-abzeichen-naechstes="tagesserie-14"' in html
    assert 'data-abzeichen-naechstes="wochenserie-1"' in html
    assert "data-rekord" in html


def test_eltern_abzeichen_seite(eltern_client, anna, mama, uhr):
    _wochen(anna, uhr, 1)
    heim = eltern_client.get("/eltern/dungeon/").content.decode()
    assert 'data-kachel="spielregeln.eltern_abzeichen"' in heim
    html = eltern_client.get("/eltern/abzeichen/").content.decode()
    assert f'data-abzeichen-kind="{anna.pk}"' in html
    assert 'data-abzeichen-regel="rangaufstieg"' in html and "Wochenserie 1" in html
    antwort = eltern_client.post(
        "/eltern/abzeichen/neu/",
        {"name": "Fleißig", "metrik": "aktive_wochen", "vergleich": ">=", "schwelle": "1"},
    )
    assert antwort.status_code == 302
    assert ("fleissig", "") in _schluessel(anna)
    d = AbzeichenDefinition.objects.get(schluessel="tagesserie-30")
    antwort = eltern_client.post(
        f"/eltern/abzeichen/{d.pk}/",
        {"name": "Monat", "metrik": "rekord_tagesserie", "vergleich": ">=", "schwelle": "28"},
    )
    assert antwort.status_code == 302
    d.refresh_from_db()
    assert (d.name, d.schwelle, d.aktiv) == ("Monat", 28, True)
    antwort = eltern_client.post(f"/eltern/abzeichen/{d.pk}/aktiv/", {"aktiv": "0"})
    assert antwort.status_code == 302
    d.refresh_from_db()
    assert d.aktiv is False
    antwort = eltern_client.post(
        f"/eltern/abzeichen/{d.pk}/", {"name": "", "metrik": "rang", "schwelle": "1"}
    )
    assert antwort.status_code == 400 and "Name" in antwort.content.decode()


def test_kind_darf_abzeichen_nicht_verwalten(kind_client, anna):
    assert kind_client.get("/eltern/abzeichen/").status_code == 403
    d = AbzeichenDefinition.objects.get(schluessel="tagesserie-7")
    antwort = kind_client.post(f"/eltern/abzeichen/{d.pk}/aktiv/", {"aktiv": "0"})
    assert antwort.status_code == 403
    assert AbzeichenDefinition.objects.get(pk=d.pk).aktiv


def test_db_verhindert_doppelverleihung(anna, uhr):
    from django.db import IntegrityError

    _wochen(anna, uhr, 1)
    v = AbzeichenVerleihung.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        AbzeichenVerleihung.objects.create(
            kind=anna, abzeichen=v.abzeichen, bereich="", wert=1, schwelle=1
        )
