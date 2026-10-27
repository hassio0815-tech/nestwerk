"""AP22 Ränge: Startwerte (E14), beide Bedingungen, Mehrfachsprung, Fakt bleibt bei
Schwellenänderung und Korrektur (K2), Kalibrierung global x Kind (K3), Prüf-Auslöser,
Neuberechnung, Oberflächen."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction

from apps.ereignisse.models import Ereignis
from apps.kern.models import AuditEintrag
from apps.punkte import services as punkte
from apps.punkte.models import Art
from apps.spielregeln import selectors, services
from apps.spielregeln.models import Aktivitaet, Kalibrierung, KindStand, Rang, RangAufstieg
from apps.spielregeln.registry import metrik_wert

from .conftest import GO_LIVE, lok

_zaehler = iter(range(10**6))


def _xp(kind, menge):
    with transaction.atomic():
        return punkte.buchen(
            kind,
            Art.AUFGABE,
            menge,
            schluessel=f"test:{next(_zaehler)}",
            quelle_modul="test",
            von=None,
        )


def _wochen(kind, uhr, anzahl):
    """``anzahl`` aktive, abgeschlossene Wochen ab Go-live; Uhr = Mittwoch danach."""
    for i in range(anzahl):
        Aktivitaet.objects.create(
            kind=kind, datum=GO_LIVE + timedelta(weeks=i, days=1), modul="t", referenz=f"w{i}"
        )
    uhr.stellen(lok(2026, 10, 21, 12) + timedelta(weeks=anzahl))
    services.wochen_sicherstellen(kind)


def _stufen(kind):
    return [f.rang.stufe for f in selectors.rang_aufstiege(kind)]


def test_startwerte_entscheidung_14(db):
    werte = [
        (r.stufe, r.schluessel, r.name, r.xp_schwelle, r.min_aktive_wochen, r.mod_preis)
        for r in Rang.objects.order_by("stufe")
    ]
    assert werte == [
        (1, "common", "Common", 0, 0, 40),
        (2, "uncommon", "Uncommon", 2000, 20, 60),
        (3, "rare", "Rare", 5000, 42, 90),
        (4, "epic", "Epic", 9000, 64, 130),
        (5, "legendary", "Legendary", 14000, 90, 180),
        (6, "godmode", "God Mode", 20000, 120, 250),
    ]
    assert Rang.objects.get(ist_endstufe=True).selten == "god"
    assert Kalibrierung.objects.get(kind__isnull=True).faktor_schwelle == Decimal("1.00")


def test_startrang_ohne_fakt(anna, uhr):
    assert selectors.aktueller_rang(anna).schluessel == "common"
    assert services.raenge_pruefen(anna) == [] and not RangAufstieg.objects.exists()
    assert metrik_wert("rang", anna) == 1


def test_beide_bedingungen_noetig(anna, uhr):
    _xp(anna, 5000)
    assert services.raenge_pruefen(anna, aktive_wochen=19) == []
    assert services.raenge_pruefen(anna, xp=1999, aktive_wochen=200) == []
    neu = services.raenge_pruefen(anna, aktive_wochen=20)
    assert [f.rang.stufe for f in neu] == [2]
    assert (neu[0].xp_bei_aufstieg, neu[0].aktive_wochen_bei_aufstieg) == (5000, 20)


def test_mehrfachsprung_alle_zwischenstufen(anna, uhr):
    _xp(anna, 9500)
    neu = services.raenge_pruefen(anna, aktive_wochen=70)
    assert [f.rang.stufe for f in neu] == [2, 3, 4]
    assert selectors.aktueller_rang(anna).schluessel == "epic"
    assert metrik_wert("rang", anna) == 4
    ereignisse = Ereignis.objects.filter(typ_id="rang.aufgestiegen")
    assert ereignisse.count() == 1  # ein Pop-up für den Sprung
    daten = ereignisse.get().daten
    assert (daten["stufe"], daten["stufen"], daten["vorher"], daten["rang"]) == (
        4,
        [2, 3, 4],
        1,
        "Epic",
    )
    assert services.raenge_pruefen(anna, aktive_wochen=70) == []  # idempotent
    assert AuditEintrag.objects.filter(aktion="rang.aufgestiegen").count() == 1


def test_rang_bleibt_bei_schwellenerhoehung_und_korrektur(anna, mama, uhr):
    buchung = _xp(anna, 2100)
    services.raenge_pruefen(anna, aktive_wochen=20)
    uncommon = Rang.objects.get(schluessel="uncommon")
    with transaction.atomic():
        services.rang_aendern(
            uncommon, von=mama, name="Bronze", xp_schwelle=3000, min_aktive_wochen=30
        )
    with transaction.atomic():
        punkte.gegenbuchen(buchung, begruendung="Korrektur", von=mama)  # K2: XP sinkt
    services.raenge_pruefen(anna, aktive_wochen=20)
    assert _stufen(anna) == [2]
    assert selectors.aktueller_rang(anna).name == "Bronze"  # umbenannt, Fakt bleibt
    eintrag = AuditEintrag.objects.get(aktion="rang.geaendert")
    assert eintrag.details["neu"] == {
        "name": "Bronze",
        "xp_schwelle": 3000,
        "min_aktive_wochen": 30,
    }


def test_schwellen_muessen_steigen(mama, db):
    rare = Rang.objects.get(schluessel="rare")
    with pytest.raises(services.RangFehler, match="XP-Schwelle"):
        services.rang_aendern(rare, von=mama, name="Rare", xp_schwelle=1000, min_aktive_wochen=42)
    with pytest.raises(services.RangFehler, match="Aktive Wochen"):
        services.rang_aendern(rare, von=mama, name="Rare", xp_schwelle=5000, min_aktive_wochen=90)
    with pytest.raises(services.RangFehler, match="Name"):
        services.rang_aendern(rare, von=mama, name=" ", xp_schwelle=5000, min_aktive_wochen=42)
    rare.refresh_from_db()
    assert (rare.name, rare.xp_schwelle) == ("Rare", 5000)


def test_niedrigere_schwelle_loest_aufstieg_aus(anna, mama, uhr):
    _wochen(anna, uhr, 3)
    _xp(anna, 600)
    with transaction.atomic():
        services.rang_aendern(
            Rang.objects.get(schluessel="uncommon"),
            von=mama,
            name="Uncommon",
            xp_schwelle=500,
            min_aktive_wochen=3,
        )
    assert _stufen(anna) == [2]


def test_kalibrierung_global_mal_kind(anna, ben, mama, uhr):
    _xp(anna, 2400)
    _xp(ben, 2400)
    with transaction.atomic():
        services.kalibrierung_setzen(None, "1,25", von=mama, notiz="zu schnell")
    assert selectors.wirksamer_faktor(anna) == Decimal("1.25")
    assert services.raenge_pruefen(anna, aktive_wochen=20) == []  # braucht 2500
    with transaction.atomic():
        services.kalibrierung_setzen(anna, "0.8", von=mama)
    assert selectors.wirksamer_faktor(anna) == Decimal("1.0000")
    assert services.raenge_pruefen(anna, aktive_wochen=20)[0].schwelle_bei_aufstieg == 2000
    assert services.raenge_pruefen(ben, aktive_wochen=20) == []
    assert selectors.rang_fortschritt(ben, aktive_wochen=20).xp_fehlt == 100
    aktionen = list(
        AuditEintrag.objects.filter(aktion="kalibrierung.geaendert").values_list(
            "objekt_id", "details"
        )
    )
    assert aktionen[0] == ("global", {"alt": "1.00", "neu": "1.25", "notiz": "zu schnell"})
    assert aktionen[1][1]["neu"] == "0.80"
    with transaction.atomic():
        services.kalibrierung_setzen(anna, None, von=mama)  # eigener Faktor entfernt
    assert selectors.kind_faktor(anna) is None
    assert _stufen(anna) == [2]  # Fakt bleibt


@pytest.mark.parametrize("wert", ["0,2", "4.5", "abc"])
def test_kalibrierung_bereich(mama, db, wert):
    with pytest.raises(services.RangFehler, match="Faktor"):
        services.kalibrierung_setzen(None, wert, von=mama)


def test_pruefung_bei_xp_buchung(anna, uhr):
    _wochen(anna, uhr, 20)
    assert _stufen(anna) == []
    _xp(anna, 2000)  # punkte.gebucht -> synchron geprüft
    assert _stufen(anna) == [2]
    assert KindStand.objects.get(kind=anna).rang.schluessel == "uncommon"
    assert Ereignis.objects.filter(typ_id="rang.aufgestiegen", kind=anna).count() == 1


def test_pruefung_im_wochenabschluss(anna, uhr):
    _wochen(anna, uhr, 19)
    _xp(anna, 2500)
    assert _stufen(anna) == []
    Aktivitaet.objects.create(
        kind=anna, datum=GO_LIVE + timedelta(weeks=19, days=1), modul="t", referenz="w19"
    )
    uhr.weiter(weeks=1)
    services.wochen_sicherstellen()
    assert _stufen(anna) == [2]


def test_neuberechnung_konsistent(anna, mama, uhr):
    _wochen(anna, uhr, 20)
    _xp(anna, 2100)
    services.wochen_sicherstellen(anna)
    assert services.neu_berechnen() == []
    with transaction.atomic():
        services.rang_aendern(
            Rang.objects.get(schluessel="uncommon"),
            von=mama,
            name="Uncommon",
            xp_schwelle=2500,
            min_aktive_wochen=20,
        )
    services.wochen_sicherstellen(anna)
    assert services.neu_berechnen() == []  # Rang bleibt Fakt, Stand passt
    KindStand.objects.filter(kind=anna).update(rang=Rang.objects.get(schluessel="common"))
    assert [a.feld for a in services.neu_berechnen()] == ["rang"]
    services.neu_berechnen(schreiben=True)
    assert services.neu_berechnen() == []


def test_neuberechnung_meldet_fehlenden_aufstieg(anna, uhr):
    _wochen(anna, uhr, 20)
    _xp(anna, 2100)
    RangAufstieg.objects.all().delete()
    KindStand.objects.update(rang=Rang.objects.get(schluessel="common"))
    assert [a.feld for a in services.neu_berechnen()] == ["rang_aufstieg_fehlt"]
    services.neu_berechnen(schreiben=True)
    assert _stufen(anna) == [2] and services.neu_berechnen() == []


# --- Oberfläche ------------------------------------------------------------------------------


def test_kind_kachel_rang_und_fortschritt(kind_client, anna, uhr):
    _wochen(anna, uhr, 5)
    _xp(anna, 500)
    html = kind_client.get("/kind/dungeon/").content.decode()
    assert 'data-kachel="spielregeln.kind_rang"' in html
    assert 'data-selten="common" data-rang="common"' in html
    assert "Noch 1500 XP und 15 aktive Wochen bis Uncommon." in html


def test_eltern_raenge_verwalten(eltern_client, anna, mama, uhr):
    html = eltern_client.get("/eltern/raenge/").content.decode()
    assert 'data-rang="godmode"' in html and "Kalibrierung" in html
    assert (
        'data-kachel="spielregeln.eltern_raenge"'
        in eltern_client.get("/eltern/dungeon/").content.decode()
    )
    rare = Rang.objects.get(schluessel="rare")
    antwort = eltern_client.post(
        f"/eltern/raenge/{rare.pk}/",
        {"name": "Silber", "xp_schwelle": "5200", "min_aktive_wochen": "42"},
    )
    assert antwort.status_code == 302
    rare.refresh_from_db()
    assert (rare.name, rare.xp_schwelle) == ("Silber", 5200)
    antwort = eltern_client.post(
        f"/eltern/raenge/{rare.pk}/",
        {"name": "Silber", "xp_schwelle": "100", "min_aktive_wochen": "42"},
    )
    assert antwort.status_code == 400 and "muss mit dem Rang steigen" in antwort.content.decode()
    antwort = eltern_client.post(
        "/eltern/raenge/kalibrierung/", {"ziel": str(anna.pk), "faktor": "0,9"}
    )
    assert antwort.status_code == 302 and selectors.kind_faktor(anna) == Decimal("0.90")


def test_kind_darf_raenge_nicht(kind_client, anna):
    assert kind_client.get("/eltern/raenge/").status_code == 403
    rare = Rang.objects.get(schluessel="rare")
    antwort = kind_client.post(
        f"/eltern/raenge/{rare.pk}/",
        {"name": "X", "xp_schwelle": "5000", "min_aktive_wochen": "42"},
    )
    assert antwort.status_code == 403
    assert Rang.objects.get(pk=rare.pk).name == "Rare"
