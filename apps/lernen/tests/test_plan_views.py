"""Seiten der Prüfungsvorbereitung: Kind (HTMX), Eltern (mitlesen), Rollenschutz, Isolation."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.kern import zeit
from apps.konten.tests.conftest import angemeldet
from apps.lernen import plan_selectors, plan_services
from apps.lernen.models import Frage, PortionArt, PortionStatus, Pruefung, Thema


def url(name, *args):
    return reverse(f"lernen:{name}", args=args)


def thema_mit(fach, anzahl, name):
    t = Thema.objects.create(fach=fach, klassenstufe=5, name=name)
    for i in range(anzahl):
        Frage.objects.create(thema=t, typ="frage", frage=f"Frage {name} {i}", antwort=f"a{i}")
    return t


@pytest.fixture
def client_b(kind_b):
    return angemeldet(Client(), kind_b)


@pytest.fixture
def lang(fach):
    return thema_mit(fach, 40, "Langes Thema")


@pytest.fixture
def pruefung(kind_a, fach, lang, uhr):
    return plan_services.pruefung_anlegen(
        kind_a, fach, "Mein Test", zeit.heute() + timedelta(days=14), themen=[lang]
    )


def termin(tage):
    return (zeit.heute() + timedelta(days=tage)).isoformat()


# --- Kind: Seiten --------------------------------------------------------------------------


def test_start_zeigt_link_zu_pruefungen(kind_client, fach):
    html = kind_client.get(url("start")).content.decode()
    assert url("pruefungen") in html and "data-lernen-pruefungen" in html


def test_liste_leer_und_mit_pruefung(kind_client, pruefung):
    html = kind_client.get(url("pruefungen")).content.decode()
    assert "Mein Test" in html and url("pruefung", pruefung.pk) in html
    assert "<progress" in html


def test_neu_formular_und_htmx_stoffwahl(kind_client, fach, lang):
    html = kind_client.get(url("pruefung_neu"), {"fach": fach.pk}).content.decode()
    assert "Wann ist die Prüfung?" in html and "Langes Thema" in html and "<html" in html
    assert "Wann ist die Prüfung?" in kind_client.get(url("pruefung_neu")).content.decode()
    teil = kind_client.get(url("pruefung_neu"), {"fach": fach.pk}, headers={"HX-Request": "true"})
    teil = teil.content.decode()
    assert "<html" not in teil and "Langes Thema" in teil and 'id="stoff-liste"' in teil


def test_anlegen_per_formular(kind_client, kind_a, fach, lang, uhr):
    antwort = kind_client.post(
        url("pruefung_anlegen"),
        {"fach": fach.pk, "titel": "Klassenarbeit", "termin": termin(15), "thema": [lang.pk]},
    )
    p = Pruefung.objects.get(kind=kind_a)
    assert antwort.status_code == 302 and antwort["Location"] == url("pruefung", p.pk)
    assert p.plan_ok and p.titel == "Klassenarbeit"
    html = kind_client.get(url("pruefung", p.pk)).content.decode()
    assert "Dein Plan" in html and "data-pruefung-plan" in html and "Heute dran" in html


@pytest.mark.parametrize(
    "daten",
    [
        {"termin": "gestern", "thema": ["1"]},  # kein Datum
        {"termin": "2000-01-01", "thema": ["1"]},  # Vergangenheit
        {"termin": "{morgen}"},  # kein Stoff
        {"termin": "{morgen}", "thema": ["99999"]},  # unbekanntes Thema
        {"termin": "{morgen}", "fach": "99999"},  # Fach gibt es nicht: nimmt das erste, kein Stoff
    ],
)
def test_anlegen_mit_fehlern_zeigt_freundlichen_hinweis(kind_client, fach, lang, uhr, daten):
    daten = {k: (termin(5) if v == "{morgen}" else v) for k, v in daten.items()}
    daten.setdefault("fach", fach.pk)
    if daten.get("thema") == ["1"]:
        daten["thema"] = [str(lang.pk)]
    antwort = kind_client.post(url("pruefung_anlegen"), daten)
    assert antwort.status_code == 400
    assert 'role="alert"' in antwort.content.decode()
    assert Pruefung.objects.count() == 0


def test_realitaetscheck_wird_verstaendlich_angezeigt(kind_client, kind_a, fach, uhr):
    gross = thema_mit(fach, 600, "Riesig")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Viel", zeit.heute() + timedelta(days=5), themen=[gross]
    )
    html = kind_client.get(url("pruefung", p.pk)).content.decode()
    assert "data-pruefung-check" in html
    assert "Das ist so zu viel" in html
    assert "Stoff" in html and "data-pruefung-vorschlaege" in html
    assert "Dein Fortschritt" not in html  # kein voller Plan
    assert plan_selectors.plan_portionen(p).count() == 0
    liste = kind_client.get(url("pruefungen")).content.decode()
    assert "data-pruefung-check" in liste


def test_ziel_vorschlag_nur_per_knopf(kind_client, kind_a, fach, uhr):
    gross = thema_mit(fach, 160, "Mittel")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Mittel", zeit.heute() + timedelta(days=8), themen=[gross]
    )
    check = plan_selectors.realitaetscheck(p, zeit.heute())
    v = next((x for x in check.vorschlaege if x.art == "ziel"), None)
    if v is None:
        pytest.skip("kein Zielvorschlag bei diesen Daten")
    html = kind_client.get(url("pruefung", p.pk)).content.decode()
    assert url("pruefung_ziel", p.pk) in html
    p.refresh_from_db()
    assert not p.plan_ok  # Ansehen ändert nichts
    assert kind_client.post(url("pruefung_ziel", p.pk), {"minuten": "x"}).status_code == 400
    assert kind_client.post(url("pruefung_ziel", p.pk), {"minuten": "200"}).status_code == 400
    assert kind_client.post(url("pruefung_ziel", p.pk), {"minuten": v.wert}).status_code == 302
    p.refresh_from_db()
    assert p.plan_ok


def test_stoff_weglassen_und_neu_rechnen(kind_client, kind_a, fach, uhr):
    a = thema_mit(fach, 300, "Teil A")
    b = thema_mit(fach, 10, "Teil B")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Zwei", zeit.heute() + timedelta(days=7), themen=[a, b]
    )
    assert not p.plan_ok
    html = kind_client.get(url("pruefung", p.pk)).content.decode()
    assert "Weglassen" in html
    assert kind_client.post(url("pruefung_neu_planen", p.pk)).status_code == 302
    stoff = p.stoffe.get(thema=a)
    assert kind_client.post(url("pruefung_stoff_entfernen", p.pk, stoff.pk)).status_code == 302
    p.refresh_from_db()
    assert p.plan_ok
    letzter = p.stoffe.get()
    assert kind_client.post(url("pruefung_stoff_entfernen", p.pk, letzter.pk)).status_code == 400
    assert kind_client.post(url("pruefung_stoff_entfernen", p.pk, 99999)).status_code == 404


def test_portion_ueben_und_erledigen_per_htmx(kind_client, kind_a, pruefung, uhr):
    portion = pruefung.portionen.filter(art=PortionArt.NEU).order_by("datum", "id").first()
    antwort = kind_client.post(url("pruefung_portion_start", pruefung.pk, portion.pk))
    assert antwort.status_code == 302
    sitzung_url = antwort["Location"]
    html = kind_client.get(sitzung_url).content.decode()
    assert "data-lernen-portion" in html and "Mein Test" in html
    assert "data-portion-erledigt" not in html
    hx = {"HX-Request": "true"}
    letzte = ""
    for _ in range(12):
        frage = Frage.objects.get(pk=_aktuelle_frage_id(sitzung_url, kind_client))
        uhr.weiter(seconds=15)
        letzte = kind_client.post(
            sitzung_url + "antwort/", {"eingabe": frage.antwort}, headers=hx
        ).content.decode()
        portion.refresh_from_db()
        if portion.status == PortionStatus.ERLEDIGT:
            break
        kind_client.get(sitzung_url, headers=hx)
    assert portion.status == PortionStatus.ERLEDIGT
    assert "data-portion-erledigt" in letzte


def _aktuelle_frage_id(sitzung_url, client):
    from apps.lernen.models import Lernsitzung

    nr = int(sitzung_url.strip("/").split("/")[-1])
    s = Lernsitzung.objects.get(pk=nr)
    if s.aktuell_frage_id is None:
        client.get(sitzung_url)
        s.refresh_from_db()
    return s.aktuell_frage_id


def test_portion_start_fehler_und_fremde_portion(kind_client, client_b, pruefung):
    puffer = pruefung.portionen.filter(art=PortionArt.PUFFER).first()
    assert (
        kind_client.post(url("pruefung_portion_start", pruefung.pk, puffer.pk)).status_code == 400
    )
    assert kind_client.post(url("pruefung_portion_start", pruefung.pk, 99999)).status_code == 404
    portion = pruefung.portionen.filter(art=PortionArt.NEU).first()
    assert client_b.post(url("pruefung_portion_start", pruefung.pk, portion.pk)).status_code == 404


def test_abbrechen_per_formular(kind_client, pruefung):
    assert kind_client.post(url("pruefung_abbrechen", pruefung.pk)).status_code == 302
    pruefung.refresh_from_db()
    assert pruefung.status == "abgebrochen"
    html = kind_client.get(url("pruefung", pruefung.pk)).content.decode()
    assert "beendet" in html and "Los geht" not in html
    assert "Mein Test" in kind_client.get(url("pruefungen")).content.decode()


def test_verpasster_tag_zeigt_den_freundlichen_hinweis(kind_client, kind_a, pruefung, uhr):
    uhr.weiter(days=3)
    html = kind_client.get(url("pruefung", pruefung.pk)).content.decode()
    assert "Kein Problem, ich habe den Plan angepasst" in html
    assert "data-pruefung-angepasst" in html
    assert "verpasst" not in html and "falsch" not in html.lower()


def test_knapper_termin_hinweis(kind_client, kind_a, fach, uhr):
    t = thema_mit(fach, 10, "Kurz")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Bald", zeit.heute() + timedelta(days=6), themen=[t]
    )
    assert "data-pruefung-knapp" in kind_client.get(url("pruefung", p.pk)).content.decode()


def test_pause_wird_im_realitaetscheck_genannt(kind_client, kind_a, fach, uhr):
    from apps.lernen.models import Lernpause

    t = thema_mit(fach, 100, "Pausiert")
    Lernpause.objects.create(kind=kind_a, von=zeit.heute(), bis=zeit.heute() + timedelta(days=6))
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Mit Pause", zeit.heute() + timedelta(days=8), themen=[t]
    )
    assert not p.plan_ok
    assert "Tage Pause" in kind_client.get(url("pruefung", p.pk)).content.decode()


# --- Kind: Probe-Prüfung -------------------------------------------------------------------


def test_probe_pruefung_ganzer_ablauf(kind_client, kind_a, fach, uhr):
    gut = thema_mit(fach, 4, "Gut")
    schwach = thema_mit(fach, 4, "Schwach")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Probe", zeit.heute() + timedelta(days=14), themen=[gut, schwach]
    )
    antwort = kind_client.post(url("pruefung_probe", p.pk))
    assert antwort.status_code == 302
    probe_url = antwort["Location"]
    hx = {"HX-Request": "true"}
    html = kind_client.get(probe_url).content.decode()
    assert "<html" in html and "Du hast so viel Zeit" in html
    ende = ""
    for _ in range(20):
        probe = plan_selectors.offene_probe(p)
        if probe is None:
            break
        aufgabe = plan_services.probe_aufgabe(probe)
        eingabe = "weiß nicht" if aufgabe.frage.thema_id == schwach.pk else aufgabe.frage.antwort
        teil = kind_client.post(probe_url + "antwort/", {"eingabe": eingabe}, headers=hx)
        assert "<html" not in teil.content.decode()
        ende = teil.content.decode()
    assert "data-probe-ergebnis" in ende
    assert "keine Note" in ende
    assert 'data-thema-einstufung="ueben"' in ende and 'data-thema-einstufung="staerke"' in ende
    assert url("probe_schwaechen", plan_selectors.letzte_probe(p).pk) in ende
    probe = plan_selectors.letzte_probe(p)
    assert kind_client.post(url("probe_schwaechen", probe.pk)).status_code == 302
    ende2 = kind_client.get(probe_url).content.decode()
    assert url("probe_schwaechen", probe.pk) not in ende2
    # Antwort auf eine fertige Probe: freundlicher Hinweis statt Absturz
    assert "alert" in kind_client.post(probe_url + "antwort/", {"eingabe": "x"}).content.decode()


def test_probe_fremder_404(client_b, kind_client, pruefung):
    probe = plan_services.probe_starten(pruefung)
    assert client_b.get(url("probe", probe.pk)).status_code == 404
    assert client_b.post(url("probe_antwort", probe.pk), {"eingabe": "x"}).status_code == 404
    assert client_b.post(url("probe_schwaechen", probe.pk)).status_code == 404
    assert client_b.post(url("pruefung_probe", pruefung.pk)).status_code == 404


# --- Isolation und Rollen ------------------------------------------------------------------


def test_geschwister_sehen_keine_fremden_plaene(client_b, pruefung):
    assert client_b.get(url("pruefung", pruefung.pk)).status_code == 404
    for name in (
        "pruefung_ziel",
        "pruefung_neu_planen",
        "pruefung_abbrechen",
        "pruefung_probe",
    ):
        assert client_b.post(url(name, pruefung.pk), {"minuten": "25"}).status_code == 404
    liste = client_b.get(url("pruefungen")).content.decode()
    assert "Mein Test" not in liste and url("pruefung", pruefung.pk) not in liste
    pruefung.refresh_from_db()
    assert pruefung.status in ("geplant", "aktiv")


def test_nur_kinder_nutzen_die_kind_seiten(eltern_client, client, pruefung):
    portion = pruefung.portionen.first()
    kind_urls = [
        ("pruefungen", ()),
        ("pruefung_neu", ()),
        ("pruefung", (pruefung.pk,)),
    ]
    for name, args in kind_urls:
        assert eltern_client.get(url(name, *args)).status_code in (302, 403)
        assert client.get(url(name, *args)).status_code in (302, 403)
    for name, args in (
        ("pruefung_anlegen", ()),
        ("pruefung_portion_start", (pruefung.pk, portion.pk)),
        ("pruefung_ziel", (pruefung.pk,)),
        ("pruefung_abbrechen", (pruefung.pk,)),
        ("pruefung_probe", (pruefung.pk,)),
    ):
        assert eltern_client.post(url(name, *args), {}).status_code in (302, 403)
    pruefung.refresh_from_db()
    assert pruefung.status in ("geplant", "aktiv")


def test_kinder_nutzen_keine_eltern_seiten(kind_client, pruefung):
    for name, args in (
        ("eltern_pruefungen", ()),
        ("eltern_pruefung", (pruefung.pk,)),
    ):
        assert kind_client.get(url(name, *args)).status_code in (302, 403)
    for name in ("eltern_pruefung_termin", "eltern_pruefung_loeschen"):
        assert kind_client.post(url(name, pruefung.pk), {"termin": termin(20)}).status_code in (
            302,
            403,
        )
    assert Pruefung.objects.filter(pk=pruefung.pk).exists()
    pruefung.refresh_from_db()
    assert pruefung.termin == zeit.heute() + timedelta(days=14)


# --- Eltern --------------------------------------------------------------------------------


def test_eltern_sehen_liste_und_plan_nur_lesend(eltern_client, pruefung, kind_a):
    html = eltern_client.get(url("eltern_pruefungen")).content.decode()
    assert kind_a.anzeigename in html and "Mein Test" in html
    assert url("eltern_pruefung", pruefung.pk) in html
    detail = eltern_client.get(url("eltern_pruefung", pruefung.pk)).content.decode()
    assert "data-pruefung-plan" in detail and "Termin ändern" in detail
    # kein Eingriff in den Plan: keine Start-, Ziel- oder Weglassen-Formulare
    for name in ("pruefung_ziel", "pruefung_neu_planen", "pruefung_abbrechen"):
        assert url(name, pruefung.pk) not in detail
    assert "Los geht" not in detail


def test_eltern_hinweis_bei_realitaetscheck(eltern_client, kind_a, fach, uhr):
    gross = thema_mit(fach, 600, "Riesig")
    p = plan_services.pruefung_anlegen(
        kind_a, fach, "Zu viel", zeit.heute() + timedelta(days=5), themen=[gross]
    )
    html = eltern_client.get(url("eltern_pruefungen")).content.decode()
    assert "data-pruefung-problem" in html
    detail = eltern_client.get(url("eltern_pruefung", p.pk)).content.decode()
    assert "data-pruefung-problem" in detail and "keinen vollen Plan" in detail


def test_eltern_aendern_termin_und_loeschen(eltern_client, pruefung):
    seite = url("eltern_pruefung_termin", pruefung.pk)
    assert eltern_client.post(seite, {"termin": termin(30)}).status_code == 302
    pruefung.refresh_from_db()
    assert pruefung.termin == zeit.heute() + timedelta(days=30) and pruefung.plan_ok
    schlecht = eltern_client.post(seite, {"termin": "2000-01-01"})
    assert schlecht.status_code == 400 and 'role="alert"' in schlecht.content.decode()
    assert eltern_client.post(seite, {"termin": "kaputt"}).status_code == 400
    assert eltern_client.post(url("eltern_pruefung_loeschen", pruefung.pk)).status_code == 302
    assert not Pruefung.objects.filter(pk=pruefung.pk).exists()
    assert eltern_client.get(url("eltern_pruefung", pruefung.pk)).status_code == 404
    assert eltern_client.post(seite, {"termin": termin(30)}).status_code == 404
    assert eltern_client.post(url("eltern_pruefung_loeschen", pruefung.pk)).status_code == 404


def test_eltern_seite_hat_link(eltern_client):
    assert url("eltern_pruefungen") in eltern_client.get(url("eltern")).content.decode()
