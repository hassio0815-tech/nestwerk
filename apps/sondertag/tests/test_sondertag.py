"""Sondertag mit DB (AP27): Anspruch aus Meilenstein, Warteschlange, Wunsch, K6, Übergabe,
Korrektur, Historie, Idempotenz, Fortschritt, Views."""

from datetime import date, timedelta

import pytest
from django.db import transaction

from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen
from apps.kern import registry as kern_registry
from apps.kern.models import AuditEintrag
from apps.sondertag import events, selectors, services
from apps.sondertag.meilensteine_start import GODMODE_SCHLUESSEL, rang_schluessel
from apps.sondertag.models import SondertagAnspruch, Status
from apps.spielregeln import services as spielregeln
from apps.spielregeln.models import MeilensteinErreicht, MeilensteinRegel

from .conftest import GO_LIVE


def tag(n):
    return GO_LIVE + timedelta(days=n)


@pytest.fixture
def metriken(monkeypatch):
    """Metrik-Werte je Kind setzen: ``metriken[kind.pk] = {"rang": 2, ...}``; Bereiche als
    ``{"godmode_zyklus.bereiche": {...}}``. Unbekannte Metriken -> echter Provider."""
    werte = {}
    original = kern_registry.fortschritt

    def fortschritt(schluessel, *args, **kwargs):
        if schluessel.startswith("metrik.") and args:
            eintrag = werte.get(getattr(args[0], "pk", None), {})
            name = schluessel.removeprefix("metrik.")
            if name in eintrag:
                return eintrag[name]
        return original(schluessel, *args, **kwargs)

    monkeypatch.setattr(kern_registry, "fortschritt", fortschritt)
    return werte


def pruefen(kind):
    with transaction.atomic():
        return spielregeln.abzeichen_pruefen(kind)


def rang_fertig(metriken, kind, stufe):
    metriken.setdefault(kind.pk, {}).update({"rang": stufe, f"ausbaustufe_seltenheit_{stufe}": 6})
    return pruefen(kind)


# --- Anspruch aus Meilenstein -----------------------------------------------------------------


def test_meilensteine_angelegt():
    schluessel = set(
        MeilensteinRegel.objects.filter(belohnungsart="sondertag").values_list(
            "schluessel", flat=True
        )
    )
    assert schluessel == {rang_schluessel(n) for n in (2, 3, 4, 5)} | {GODMODE_SCHLUESSEL}
    regel = MeilensteinRegel.objects.get(schluessel=rang_schluessel(3))
    assert regel.bedingungen == [
        {"metrik": "rang", "vergleich": ">=", "wert": 3},
        {"metrik": "ausbaustufe_seltenheit_3", "vergleich": ">=", "wert": 6},
    ]
    assert MeilensteinRegel.objects.get(schluessel=GODMODE_SCHLUESSEL).wiederholbar == "bereich"


def test_meilenstein_erzeugt_anspruch_und_popup(anna, mama, papa, metriken, uhr):
    uhr.stellen(tag(30))
    ergebnis = rang_fertig(metriken, anna, 2)
    assert len(ergebnis.erreicht) == 1
    anspruch = SondertagAnspruch.objects.get(kind=anna)
    assert anspruch.status == Status.VERDIENT
    assert anspruch.einloesbar_ab == tag(30)
    assert anspruch.meilenstein == ergebnis.erreicht[0]
    typen = set(Ereignis.objects.filter(kind=anna).values_list("typ_id", flat=True))
    assert {events.FREIGESCHALTET, events.VERDIENT_ELTERN} <= typen
    # nur Ausbaustufe 5 von 6: kein Meilenstein
    metriken[anna.pk]["ausbaustufe_seltenheit_3"] = 5
    metriken[anna.pk]["rang"] = 3
    assert pruefen(anna).erreicht == []


def test_idempotenz_doppelte_ereignisse_ein_anspruch(anna, metriken, uhr):
    rang_fertig(metriken, anna, 2)
    fakt = MeilensteinErreicht.objects.get(kind=anna)
    ereignis = fakt.ereignis
    with transaction.atomic():
        services.nach_meilenstein(ereignis)
        services.nach_meilenstein(ereignis)
        services.anspruch_anlegen(anna, fakt.pk)
    pruefen(anna)
    assert SondertagAnspruch.objects.filter(kind=anna).count() == 1
    assert services.nachholen() == 0


def test_andere_belohnungsart_ignoriert(anna):
    class E:
        daten = {"belohnungsart": "modset", "erreicht": 1}
        kind_id = anna.pk
        kind = anna
        pk = 1

    assert services.nach_meilenstein(E()) is None
    assert not SondertagAnspruch.objects.exists()


def test_nachholen_fuer_fakt_ohne_anspruch(anna, metriken, uhr):
    rang_fertig(metriken, anna, 2)
    SondertagAnspruch.objects.all().delete()
    assert services.nachholen() == 1
    assert services.nachholen() == 0


def test_fruehe_meilensteine_bleiben_in_warteschlange(anna, metriken, uhr):
    """Rang 2 bis 4 schnell hintereinander: alle verdient, einlösbar nacheinander."""
    for n, (stufe, t) in enumerate(((2, 10), (3, 40), (4, 80))):
        uhr.stellen(tag(t))
        rang_fertig(metriken, anna, stufe)
        assert SondertagAnspruch.objects.filter(kind=anna).count() == n + 1
    uhr.stellen(tag(90))
    liste = selectors.warteschlange(anna)
    assert [e.position for e in liste] == [0, 1, 2]
    assert liste[0].einloesbar is True
    assert liste[1].einloesbar_ab == tag(90 + 150)
    # erster frühestens heute (Tag 90), zweiter Tag 240; App-Jahr 1 damit voll und 150 Tage
    assert liste[2].einloesbar_ab == tag(390)
    assert not liste[1].einloesbar
    # Themenwechsel o. ä.: Metrik fällt auf 0, Ansprüche bleiben (Fakten)
    metriken[anna.pk]["ausbaustufe_seltenheit_4"] = 0
    pruefen(anna)
    assert SondertagAnspruch.objects.filter(kind=anna).count() == 3


# --- Wunsch und Annahme (K6) ------------------------------------------------------------------


def _anspruch(anna, metriken, uhr, t=0, stufe=2):
    uhr.stellen(tag(t))
    rang_fertig(metriken, anna, stufe)
    return SondertagAnspruch.objects.filter(kind=anna).order_by("-id").first()


def test_wunsch_an_beide_eltern(anna, mama, papa, metriken, uhr):
    a = _anspruch(anna, metriken, uhr)
    services.wunsch_senden(anna, a, wunsch="  Kletterhalle   und Pizza ", begleitung="papa")
    a.refresh_from_db()
    assert a.status == Status.WUNSCH_OFFEN
    assert a.wunsch == "Kletterhalle und Pizza"
    assert a.begleitung_wunsch == "papa"
    e = Ereignis.objects.get(typ_id=events.WUNSCH)
    assert e.daten["begleitung"] == "Papa"
    from apps.ereignisse import registry

    assert registry.typ(events.WUNSCH).entscheidung is True
    assert registry.typ(events.WUNSCH).zielgruppe == "eltern"  # Router: alle Eltern


@pytest.mark.parametrize(
    ("text", "begleitung", "meldung"),
    [("", "egal", "Schreib"), ("x" * 301, "egal", "zu lang"), ("Zoo", "oma", "Wähle")],
)
def test_wunsch_pruefungen(anna, metriken, uhr, text, begleitung, meldung):
    a = _anspruch(anna, metriken, uhr)
    with pytest.raises(services.SondertagFehler, match=meldung):
        services.wunsch_senden(anna, a, wunsch=text, begleitung=begleitung)


def test_k6_wunsch_sofort_annahme_erst_ab_einloesbar(anna, mama, papa, metriken, uhr):
    services.manuell_erfassen(anna, von=mama, datum=tag(0))
    a = _anspruch(anna, metriken, uhr, t=20)
    assert a.einloesbar_ab == tag(150)
    services.wunsch_senden(anna, a, wunsch="Freizeitpark", begleitung="egal")  # sofort möglich
    with pytest.raises(services.SondertagFehler, match="erst ab 18.03.2027"):
        services.annehmen(a, von=mama, heute=tag(149))
    services.annehmen(a, von=mama, heute=tag(150))
    a.refresh_from_db()
    assert a.status == Status.ANGENOMMEN
    assert a.annahme_datum == tag(150)
    assert a.angenommen_von == mama and a.begleitung == mama
    assert Ereignis.objects.filter(typ_id=events.ANGENOMMEN, kind=anna).count() == 1


def test_wunsch_vor_einloesbar_abschaltbar(anna, mama, metriken, uhr):
    einstellungen.setzen("sondertag.wunsch_vor_einloesbar_erlaubt", False, akteur=None)
    services.manuell_erfassen(anna, von=mama, datum=tag(0))
    a = _anspruch(anna, metriken, uhr, t=20)
    with pytest.raises(services.SondertagFehler, match="ab 18.03.2027"):
        services.wunsch_senden(anna, a, wunsch="Zoo", begleitung="egal")
    uhr.stellen(tag(150))
    services.wunsch_senden(anna, a, wunsch="Zoo", begleitung="egal")


def test_nur_erster_anspruch_und_nur_mit_wunsch(anna, mama, metriken, uhr):
    erster = _anspruch(anna, metriken, uhr, t=0, stufe=2)
    zweiter = _anspruch(anna, metriken, uhr, t=1, stufe=3)
    with pytest.raises(services.SondertagFehler, match="keinen Wunsch"):
        services.wunsch_senden(anna, zweiter, wunsch="Zoo", begleitung="egal")
    with pytest.raises(services.SondertagFehler, match="keinen offenen Wunsch"):
        services.annehmen(erster, von=mama, heute=tag(1))
    services.wunsch_senden(anna, erster, wunsch="Zoo", begleitung="mama")
    with pytest.raises(services.SondertagFehler, match="nur Eltern"):
        services.annehmen(erster, von=anna, heute=tag(1))
    services.annehmen(erster, von=mama, heute=tag(1))
    zweiter.refresh_from_db()
    assert zweiter.einloesbar_ab == tag(151)  # nach Annahme neu berechnet


def test_uebergabe_aendert_nur_begleitung(anna, mama, papa, metriken, uhr):
    a = _anspruch(anna, metriken, uhr)
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="mama")
    with pytest.raises(services.SondertagFehler, match="nach der Annahme"):
        services.uebergeben(a, von=mama, an=papa)
    services.annehmen(a, von=mama, heute=tag(0))
    services.uebergeben(a, von=mama, an=papa)
    a.refresh_from_db()
    assert a.begleitung == papa and a.angenommen_von == mama
    assert a.annahme_datum == tag(0)
    eintrag = AuditEintrag.objects.get(aktion="sondertag.uebergeben")
    assert eintrag.details == {"alt": str(mama.pk), "neu": str(papa.pk)}
    with pytest.raises(services.SondertagFehler, match="begleitet schon"):
        services.uebergeben(a, von=papa, an=papa)
    assert Ereignis.objects.filter(typ_id=events.UEBERGEBEN).count() == 1


def test_korrektur_bezugsdatum_plant_neu(anna, mama, metriken, uhr):
    a = _anspruch(anna, metriken, uhr, t=0, stufe=2)
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="egal")
    services.annehmen(a, von=mama, heute=tag(0))
    b = _anspruch(anna, metriken, uhr, t=10, stufe=3)
    assert b.einloesbar_ab == tag(150)
    # Termin war in Wahrheit erst an Tag 40: Eltern korrigieren das Bezugsdatum
    services.bezugsdatum_korrigieren(a, tag(40), von=mama, heute=tag(10))
    b.refresh_from_db()
    assert b.einloesbar_ab == tag(190)
    eintrag = AuditEintrag.objects.get(aktion="sondertag.korrigiert")
    assert eintrag.details["alt"] == {"annahme_datum": tag(0).isoformat()}
    assert eintrag.details["neu"] == {"annahme_datum": tag(40).isoformat()}


def test_historie_manuell_vor_go_live_und_loeschen(anna, mama, papa, metriken, uhr):
    vorher = GO_LIVE - timedelta(days=100)
    m = services.manuell_erfassen(anna, von=mama, datum=vorher, begleitung=papa.pk, notiz="Zoo")
    assert m.status == Status.STATTGEFUNDEN and m.begleitung == papa
    a = _anspruch(anna, metriken, uhr, t=10)
    assert a.einloesbar_ab == vorher + timedelta(days=150)
    services.eintrag_aendern(m, von=mama, begleitung=mama.pk, notiz="Zoo mit Mama")
    m.refresh_from_db()
    assert m.begleitung == mama and m.notiz == "Zoo mit Mama"
    with pytest.raises(services.SondertagFehler, match="manuell"):
        services.manuell_loeschen(a, von=mama)
    services.manuell_loeschen(m, von=mama)
    a.refresh_from_db()
    assert a.einloesbar_ab == tag(10)


def test_stattgefunden(anna, mama, metriken, uhr):
    a = _anspruch(anna, metriken, uhr)
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="egal")
    services.annehmen(a, von=mama, heute=tag(0))
    services.stattgefunden(a, von=mama, datum="2026-11-07")
    a.refresh_from_db()
    assert a.status == Status.STATTGEFUNDEN and a.stattgefunden_am == date(2026, 11, 7)


def test_annahme_prueft_grenzen_serverseitig(anna, mama, metriken, uhr):
    """Auch wenn das gespeicherte einloesbar_ab veraltet ist, rechnet annehmen neu."""
    a = _anspruch(anna, metriken, uhr, t=0)
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="egal")
    services.manuell_erfassen(anna, von=mama, datum=tag(-10))  # nachgetragen
    SondertagAnspruch.objects.filter(pk=a.pk).update(einloesbar_ab=tag(0))  # veraltet
    with pytest.raises(services.SondertagFehler, match="erst ab"):
        services.annehmen(a, von=mama, heute=tag(5))


def test_zwei_pro_app_jahr_ueber_services(anna, mama, metriken, uhr):
    """52 Wochen mit vier verdienten Sondertagen: angenommen werden nur zwei im App-Jahr 1."""
    angenommen = []
    for stufe, t in ((2, 20), (3, 60), (4, 120), (5, 300)):
        uhr.stellen(tag(t))
        rang_fertig(metriken, anna, stufe)
    t = 20
    while t < 364:
        uhr.stellen(tag(t))
        e = selectors.aktueller(anna)
        if e and e.einloesbar:
            if not e.wunsch_offen:
                services.wunsch_senden(anna, e.anspruch, wunsch="Tag", begleitung="egal")
            services.annehmen(e.anspruch, von=mama, heute=tag(t))
            angenommen.append(tag(t))
        t += 1
    assert angenommen == [tag(20), tag(170)]
    assert len(selectors.warteschlange(anna)) == 2
    assert selectors.aktueller(anna).einloesbar_ab == date(2027, 10, 19)


# --- Fortschritt und Übersicht ----------------------------------------------------------------


def test_fortschritt_mods_und_wochen(anna, mama, metriken, uhr):
    metriken[anna.pk] = {"rang": 3, "ausbaustufe_seltenheit_2": 6, "ausbaustufe_seltenheit_3": 4}
    services.manuell_erfassen(anna, von=mama, datum=tag(0))
    uhr.stellen(tag(130))
    pruefen(anna)  # Rang 2 erreicht -> Anspruch, einlösbar ab Tag 150
    f = selectors.fortschritt(anna)
    assert f.art == "verdient"
    assert "einlösbar ab 18.03.2027" in f.text
    assert f.weiter.startswith("Noch 2 Mods und")
    # Anspruch eingelöst: nächster Schritt mit Mods und Wochen (Abstand)
    a = SondertagAnspruch.objects.get(kind=anna, quelle="meilenstein")
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="egal")
    uhr.stellen(tag(150))
    services.annehmen(a, von=mama)
    f = selectors.fortschritt(anna)
    assert f.art == "unterwegs"
    assert f.mods_fehlen == 2
    # Abstand allein wäre Tag 300, aber App-Jahr 1 hat schon 2 (Tag 0 manuell, Tag 150)
    assert f.wochen_fehlen == 31  # bis 19.10.2027
    assert f.text == "Noch 2 Mods und 31 Wochen bis zum Sondertag"
    assert f.bestaetigt == a


def test_fortschritt_ab_rang_und_godmode(anna, metriken, uhr):
    metriken[anna.pk] = {"rang": 1}
    f = selectors.fortschritt(anna)
    assert f.art == "ab_rang" and "Uncommon" in f.text
    metriken[anna.pk] = {
        "rang": 6,
        **{f"ausbaustufe_seltenheit_{n}": 6 for n in range(2, 6)},
        "godmode_aktivwochen": 30,
        "godmode_zyklus": 1,
        "godmode_zyklus.bereiche": {"zyklus-1": (1, "Zyklus 1"), "zyklus-2": (0, "Zyklus 2")},
        "godmode_set_vollstaendig": 0,
        "godmode_set_vollstaendig.bereiche": {"zyklus-1": (4, "Set 1"), "zyklus-2": (0, "")},
    }
    kern_registry_vorhanden = kern_registry.provider_vorhanden("metrik.godmode_zyklus.bereiche")
    assert kern_registry_vorhanden
    pruefen(anna)  # Rang 2-5 erreicht, Zyklus 1 noch nicht (Set 4/6)
    assert SondertagAnspruch.objects.filter(kind=anna).count() == 4
    # Ansprüche aus dem Weg räumen, damit der Zyklus-Fortschritt sichtbar wird
    SondertagAnspruch.objects.filter(kind=anna).update(
        status=Status.STATTGEFUNDEN, annahme_datum=tag(-400)
    )
    f = selectors.fortschritt(anna)
    assert f.art == "unterwegs"
    assert f.extra["zyklus"] == 1
    assert f.mods_fehlen == 2
    # Set 1 komplett -> wiederholbarer Meilenstein für Bereich zyklus-1
    metriken[anna.pk]["godmode_set_vollstaendig.bereiche"] = {
        "zyklus-1": (6, "Set 1"),
        "zyklus-2": (0, ""),
    }
    erreicht = pruefen(anna).erreicht
    assert [(f.regel.schluessel, f.bereich) for f in erreicht] == [(GODMODE_SCHLUESSEL, "zyklus-1")]
    assert SondertagAnspruch.objects.filter(kind=anna, status=Status.VERDIENT).count() == 1


def test_eltern_uebersicht_wer_mit_wem(anna, ben, mama, papa, metriken, uhr):
    services.manuell_erfassen(anna, von=mama, datum=tag(-200), begleitung=papa.pk)
    services.manuell_erfassen(anna, von=mama, datum=tag(-20), begleitung=mama.pk)
    zeilen = {z["kind"].pk: z for z in selectors.eltern_uebersicht()}
    z = zeilen[anna.pk]
    assert z["letzter"].annahme_datum == tag(-20) and z["letzter"].begleitung == mama
    assert {m["eltern"].pk: m["datum"] for m in z["mit_wem"]} == {
        mama.pk: tag(-20),
        papa.pk: tag(-200),
    }
    assert z["naechster_moeglich"] == tag(130)
    assert zeilen[ben.pk]["letzter"] is None


# --- Views ------------------------------------------------------------------------------------


def test_kind_wunsch_formular_und_senden(kind_client, anna, mama, papa, metriken, uhr):
    _anspruch(anna, metriken, uhr)
    antwort = kind_client.get("/kind/sondertag/wunsch/", HTTP_HX_REQUEST="true")
    inhalt = antwort.content.decode()
    assert antwort.status_code == 200
    assert 'name="begleitung" value="mama"' in inhalt and "egal" in inhalt
    antwort = kind_client.post(
        "/kind/sondertag/wunsch/",
        {"wunsch": "Trampolinhalle", "begleitung": "mama"},
        HTTP_HX_REQUEST="true",
    )
    assert "unterwegs" in antwort.content.decode()
    assert SondertagAnspruch.objects.get(kind=anna).status == Status.WUNSCH_OFFEN
    # Fehler im Pop-up: 200 mit Meldung (HTMX tauscht keine Fehlerantworten)
    antwort = kind_client.post(
        "/kind/sondertag/wunsch/", {"wunsch": "", "begleitung": "mama"}, HTTP_HX_REQUEST="true"
    )
    assert antwort.status_code == 200 and "Schreib auf" in antwort.content.decode()


def test_kind_startseite_zeigt_kachel(kind_client, anna, metriken, uhr):
    _anspruch(anna, metriken, uhr)
    inhalt = kind_client.get("/kind/").content.decode()
    assert 'data-sondertag="einloesbar"' in inhalt
    assert "Wunsch abschicken" in inhalt


def test_popup_festlich_mit_formular(anna):
    from types import SimpleNamespace

    from django.template.loader import render_to_string

    from apps.ereignisse import registry

    assert "popup" in registry.typ(events.FREIGESCHALTET).standard_kanaele
    p = SimpleNamespace(pk=1, art=events.FREIGESCHALTET, titel="Sondertag verdient!", text="Hi")
    html = render_to_string("benachrichtigung/_popups.html", {"popups": [p]})
    assert 'class="st-popup"' in html and "st-sterne" in html
    assert 'hx-get="/kind/sondertag/wunsch/"' in html
    assert "<script" not in html and "style=" not in html
    p = SimpleNamespace(pk=2, art=events.ANGENOMMEN, titel="Angenommen!", text="Papa plant")
    html = render_to_string("benachrichtigung/_popups.html", {"popups": [p]})
    assert "st-popup" in html and "hx-get" not in html


def test_eltern_seite_annehmen_und_uebergeben(eltern_client, anna, mama, papa, metriken, uhr):
    a = _anspruch(anna, metriken, uhr)
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="papa")
    inhalt = eltern_client.get("/eltern/sondertage/").content.decode()
    assert "Kino" in inhalt and "Wunsch angenommen" in inhalt
    assert eltern_client.post(f"/eltern/sondertage/{a.pk}/annehmen/").status_code == 302
    a.refresh_from_db()
    assert a.begleitung == mama
    antwort = eltern_client.post(f"/eltern/sondertage/{a.pk}/uebergeben/", {"an": papa.pk})
    assert antwort.status_code == 302
    a.refresh_from_db()
    assert a.begleitung == papa
    antwort = eltern_client.post(
        f"/eltern/sondertage/{a.pk}/aendern/",
        {"annahme_datum": "2026-10-25", "begleitung": papa.pk, "stattgefunden_am": "", "notiz": ""},
    )
    assert antwort.status_code == 302
    a.refresh_from_db()
    assert a.annahme_datum == date(2026, 10, 25)
    inhalt = eltern_client.get("/eltern/dungeon/").content.decode()
    assert "Sondertage verwalten" in inhalt


def test_eltern_annehmen_zu_frueh_zeigt_fehler(eltern_client, anna, mama, metriken, uhr):
    services.manuell_erfassen(anna, von=mama, datum=tag(-10))
    a = _anspruch(anna, metriken, uhr)
    services.wunsch_senden(anna, a, wunsch="Kino", begleitung="egal")
    inhalt = eltern_client.get("/eltern/sondertage/").content.decode()
    assert "data-st-ab" in inhalt
    antwort = eltern_client.post(f"/eltern/sondertage/{a.pk}/annehmen/")
    assert antwort.status_code == 400 and "erst ab" in antwort.content.decode()


def test_eltern_manuell_nachtragen(eltern_client, anna):
    antwort = eltern_client.post(
        "/eltern/sondertage/manuell/", {"kind": anna.pk, "datum": "2026-05-01", "notiz": "Zoo"}
    )
    assert antwort.status_code == 302
    assert SondertagAnspruch.objects.get(kind=anna).annahme_datum == date(2026, 5, 1)


def test_kind_darf_eltern_seite_nicht(kind_client):
    assert kind_client.get("/eltern/sondertage/").status_code in (302, 403)


# --- Meilenstein-Verwaltung (spielregeln) -----------------------------------------------------


def test_meilensteine_verwalten(eltern_client, mama):
    inhalt = eltern_client.get("/eltern/meilensteine/").content.decode()
    assert "Sondertag: Ausbaustufe 6 in Rare" in inhalt
    regel = MeilensteinRegel.objects.get(schluessel=rang_schluessel(3))
    antwort = eltern_client.post(
        f"/eltern/meilensteine/{regel.pk}/",
        {
            "name": "Rare komplett",
            "beschreibung": "",
            "metrik": ["rang", "ausbaustufe_seltenheit_3", ""],
            "vergleich": [">=", ">=", ">="],
            "wert": ["3", "5", "0"],
        },
    )
    assert antwort.status_code == 302
    regel.refresh_from_db()
    assert regel.name == "Rare komplett"
    assert regel.bedingungen[1] == {
        "metrik": "ausbaustufe_seltenheit_3",
        "vergleich": ">=",
        "wert": 5,
    }
    assert AuditEintrag.objects.filter(aktion="meilenstein.geaendert").exists()
    antwort = eltern_client.post(f"/eltern/meilensteine/{regel.pk}/aktiv/", {"aktiv": "0"})
    regel.refresh_from_db()
    assert regel.aktiv is False
    antwort = eltern_client.post(
        f"/eltern/meilensteine/{regel.pk}/",
        {"name": "x", "metrik": ["gibtsnicht"], "vergleich": [">="], "wert": ["1"]},
    )
    assert antwort.status_code == 400


def test_meilenstein_bereich_braucht_bereichsmetrik(mama):
    from apps.spielregeln.abzeichen import AbzeichenFehler, meilenstein_speichern

    regel = MeilensteinRegel.objects.get(schluessel=GODMODE_SCHLUESSEL)
    with pytest.raises(AbzeichenFehler, match="Bereich"):
        meilenstein_speichern(
            regel, von=mama, name="x", bedingungen=[{"metrik": "aktive_wochen", "wert": 1}]
        )


# --- Review AP31: "jetzt einlösbar" genau einmal ---------------------------------------------


def test_wartender_anspruch_meldet_einloesbar_genau_einmal(anna, mama, metriken, uhr):
    services.manuell_erfassen(anna, von=mama, datum=tag(-100))  # letzter Sondertag vor 100 Tagen
    a = _anspruch(anna, metriken, uhr, t=0)
    assert a.einloesbar_ab == tag(50) and a.einloesbar_gemeldet_am is None
    assert services.einloesbar_melden() == 0  # noch nicht einlösbar
    services.wunsch_senden(anna, a, wunsch="Zoo", begleitung="egal")
    uhr.stellen(tag(50))
    assert services.einloesbar_melden() == 1
    assert services.einloesbar_melden() == 0  # Doppellauf
    uhr.stellen(tag(51))
    assert services.einloesbar_melden() == 0
    assert Ereignis.objects.filter(typ_id=events.EINLOESBAR, kind=anna).count() == 1
    eltern = Ereignis.objects.get(typ_id=events.EINLOESBAR_ELTERN)
    assert "Zoo" in eltern.daten["hinweis"]
    a.refresh_from_db()
    assert a.einloesbar_gemeldet_am is not None


def test_sofort_einloesbar_meldet_nur_die_freischaltung(anna, metriken, uhr):
    a = _anspruch(anna, metriken, uhr, t=5)
    assert a.einloesbar_gemeldet_am is not None
    assert services.einloesbar_melden() == 0
    assert not Ereignis.objects.filter(typ_id=events.EINLOESBAR).exists()


def test_zweiter_in_der_warteschlange_meldet_erst_nach_annahme_des_ersten(
    anna, mama, metriken, uhr
):
    erster = _anspruch(anna, metriken, uhr, t=0, stufe=2)
    zweiter = _anspruch(anna, metriken, uhr, t=10, stufe=3)
    services.wunsch_senden(anna, erster, wunsch="Kino", begleitung="egal")
    services.annehmen(erster, von=mama, heute=tag(10))
    uhr.stellen(tag(159))
    assert services.einloesbar_melden() == 0
    uhr.stellen(tag(160))
    assert services.einloesbar_melden() == 1
    assert Ereignis.objects.get(typ_id=events.EINLOESBAR).daten["anspruch"] == zweiter.pk


def test_job_sondertag_sicherstellen_mit_joblauf(anna, metriken, uhr):
    from django.core.management import call_command

    from apps.kern.models import JobLauf

    call_command("sondertag_sicherstellen")
    call_command("sondertag_sicherstellen")
    assert JobLauf.objects.filter(name="sondertag_sicherstellen", status="ok").count() == 2
