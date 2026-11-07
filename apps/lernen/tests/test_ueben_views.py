"""Seiten: Rollenschutz, Ablauf per HTMX, Eltern-Seite, Kachel."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.kern import zeit
from apps.lernen import services
from apps.lernen.models import Erwartung, Fach, Frage, Lernpause, Lernsitzung, Lerntag, Lernziel

HX = {"HTTP_HX_REQUEST": "true"}


def los(client, fach, thema=None, **extra):
    was = f"thema:{thema.pk}" if thema else f"fach:{fach.pk}"
    daten = {"was": was, "intensitaet": "aufwaermen", "vorhaben": "neu", "strategie": "laut"}
    daten.update(extra)
    return client.post(reverse("lernen:los"), daten)


def sitzung_von(antwort):
    return Lernsitzung.objects.get(pk=int(antwort["Location"].rstrip("/").split("/")[-1]))


# --- Zugriff -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["lernen:start", "lernen:eltern"],
)
def test_ohne_anmeldung_umgeleitet(db, name):
    assert Client().get(reverse(name)).status_code in (302, 401)


def test_eltern_duerfen_nicht_ueben(eltern_client, kind_a, fach):
    assert eltern_client.get(reverse("lernen:start")).status_code == 403
    assert eltern_client.post(reverse("lernen:los"), {"was": f"fach:{fach.pk}"}).status_code == 403
    s = services.sitzung_starten(kind_a, fach)
    assert eltern_client.get(reverse("lernen:sitzung", args=[s.pk])).status_code == 403


def test_kinder_sehen_keine_eltern_seite(kind_client):
    assert kind_client.get(reverse("lernen:eltern")).status_code == 403
    assert kind_client.post(reverse("lernen:pause_neu"), {}).status_code == 403


def test_fremde_sitzung_ist_404(kind_a, kind_b, fach, kind_client):
    s = services.sitzung_starten(kind_b, fach)
    for name in ("sitzung", "antwort", "hilfe", "loesung", "beenden", "rueckschau"):
        url = reverse(f"lernen:{name}", args=[s.pk])
        antwort = kind_client.post(url) if name != "sitzung" else kind_client.get(url)
        assert antwort.status_code == 404, name


def test_aktionen_nur_per_post(kind_client, kind_a, fach):
    s = services.sitzung_starten(kind_a, fach)
    assert kind_client.get(reverse("lernen:antwort", args=[s.pk])).status_code == 405
    assert kind_client.get(reverse("lernen:los")).status_code == 405


# --- Startseite --------------------------------------------------------------------------------


def test_startseite(kind_client, fach):
    antwort = kind_client.get(reverse("lernen:start"))
    assert antwort.status_code == 200
    html = antwort.content.decode()
    assert "Testsprache" in html and "Tiere" in html
    assert 'name="vorhaben"' in html and 'name="strategie"' in html and 'name="erwartung"' in html
    assert "data-lernen-vorschlag" not in html


def test_startseite_ohne_fragen(kind_client, db):
    from apps.kern import einstellungen
    from apps.lernen.mathe.registry import schluessel_alle

    Frage.objects.all().delete()
    # die Mathe-Themen haben Generatoren; ohne Rechenarten gibt es auch dort nichts zu üben
    einstellungen.setzen("lernen.mathe_rechenarten_aus", list(schluessel_alle()), akteur=None)
    assert (
        "Es gibt noch nichts zum Üben" in kind_client.get(reverse("lernen:start")).content.decode()
    )


def test_startseite_mit_offener_sitzung_und_serie(kind_client, kind_a, fach):
    s = services.sitzung_starten(kind_a, fach)
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert reverse("lernen:sitzung", args=[s.pk]) in html
    assert "Du hast noch eine Runde offen" in html


def test_startseite_zeigt_gesenktes_ziel_ohne_vorwurf(kind_client, kind_a, fach):
    heute = zeit.heute()
    Lernziel.objects.create(kind=kind_a, ziel_minuten=20, seit=heute - timedelta(days=5))
    html = kind_client.get(reverse("lernen:start")).content.decode()
    assert "Tagesziel ist jetzt 15 Minuten" in html
    assert "verpasst" not in html and "versagt" not in html


def test_vorschlag_annehmen_und_lassen(kind_client, kind_a, db):
    Lernziel.objects.create(kind=kind_a, ziel_minuten=10, vorschlag_minuten=15, seit=zeit.heute())
    assert "data-lernen-vorschlag" in kind_client.get(reverse("lernen:start")).content.decode()
    kind_client.post(reverse("lernen:ziel_vorschlag", args=["annehmen"]))
    assert Lernziel.objects.get(kind=kind_a).ziel_minuten == 15
    assert kind_client.post(reverse("lernen:ziel_vorschlag", args=["quatsch"])).status_code == 404
    Lernziel.objects.filter(kind=kind_a).update(vorschlag_minuten=20)
    kind_client.post(reverse("lernen:ziel_vorschlag", args=["lassen"]))
    z = Lernziel.objects.get(kind=kind_a)
    assert (z.ziel_minuten, z.vorschlag_minuten) == (15, None)


def test_schontag_text(kind_client, kind_a, db):
    Lernpause.objects.create(kind=kind_a, von=zeit.heute(), bis=zeit.heute())
    assert "Schontag" in kind_client.get(reverse("lernen:start")).content.decode()


# --- Üben --------------------------------------------------------------------------------------


def test_ganzer_ablauf_per_htmx(kind_client, kind_a, fach, uhr):
    antwort = los(kind_client, fach, erwartung="vieles")
    assert antwort.status_code == 302
    s = sitzung_von(antwort)
    assert (s.intensitaet, s.vorhaben, s.strategie, s.erwartung) == (
        "aufwaermen",
        "neu",
        "laut",
        "vieles",
    )
    url = reverse("lernen:sitzung", args=[s.pk])
    seite = kind_client.get(url).content.decode()
    assert "<html" in seite and 'id="lern-bereich"' in seite and "data-lernen-frage" in seite
    assert "Dein Plan: Ich sage es laut" in seite
    teil = kind_client.get(url, **HX).content.decode()
    assert "<html" not in teil and "data-lernen-frage" in teil

    for _i in range(5):  # Aufwärmen: fünf Fragen
        s.refresh_from_db()
        loesung = services.frage_stellen(s).loesung
        feedback = kind_client.post(
            reverse("lernen:antwort", args=[s.pk]), {"eingabe": loesung}, **HX
        ).content.decode()
        assert (
            "Richtig, gut gemerkt" in feedback and 'data-lernen-zustand="rueckmeldung"' in feedback
        )
        uhr.weiter(seconds=5)
        kind_client.get(url, **HX)
    # Danach: Rückschau
    rueck = kind_client.get(url, **HX).content.decode()
    assert 'data-lernen-zustand="rueckschau"' in rueck and "Was war schwer?" in rueck
    fertig = kind_client.post(
        reverse("lernen:rueckschau", args=[s.pk]),
        {"schwer": "Schreibweise", "geholfen": "Aufschreiben", "einschaetzung": "passend"},
        **HX,
    ).content.decode()
    assert 'data-lernen-zustand="fertig"' in fertig and "data-lernen-vergleich" in fertig
    s.refresh_from_db()
    assert s.rueckschau_schwer == "Schreibweise" and s.versuche == 5


def test_vergleich_der_einschaetzung_wird_gezeigt(kind_client, kind_a, fach):
    s = services.sitzung_starten(kind_a, fach, erwartung=Erwartung.WENIGES)
    s.versuche, s.richtig = 4, 4
    s.save()
    services.rueckschau_speichern(s)
    html = kind_client.get(reverse("lernen:sitzung", args=[s.pk])).content.decode()
    assert "Du wusstest mehr, als du erwartet hast" in html


def test_falsche_antwort_zeigt_noch_nicht_und_loesung(kind_client, kind_a, fach):
    s = sitzung_von(los(kind_client, fach))
    loesung = services.frage_stellen(s).loesung
    html = kind_client.post(
        reverse("lernen:antwort", args=[s.pk]), {"eingabe": "zzzzzz"}, **HX
    ).content.decode()
    assert "Noch nicht" in html and loesung in html
    assert "falsch" not in html.lower()


def test_fast_richtig_zeigt_frage_weiter(kind_client, kind_a, fach):
    Frage.objects.filter(thema__fach=fach).exclude(frage="Pferd").delete()
    s = sitzung_von(los(kind_client, fach))
    wort = services.frage_stellen(s).loesung
    html = kind_client.post(
        reverse("lernen:antwort", args=[s.pk]), {"eingabe": wort[1] + wort[0] + wort[2:]}, **HX
    ).content.decode()
    assert "Fast" in html and "data-lernen-frage" in html


def test_hilfe_und_loesung_und_beenden(kind_client, kind_a, fach):
    s = sitzung_von(los(kind_client, fach))
    loesung = services.frage_stellen(s).loesung
    html = kind_client.post(reverse("lernen:hilfe", args=[s.pk]), **HX).content.decode()
    assert "data-lernen-hinweis" in html and loesung not in html
    html = kind_client.post(reverse("lernen:loesung", args=[s.pk]), **HX).content.decode()
    assert loesung in html
    html = kind_client.post(reverse("lernen:beenden", args=[s.pk]), **HX).content.decode()
    assert 'data-lernen-zustand="rueckschau"' in html


def test_ohne_javascript_volle_seite(kind_client, kind_a, fach):
    s = sitzung_von(los(kind_client, fach))
    services.frage_stellen(s)
    antwort = kind_client.post(reverse("lernen:antwort", args=[s.pk]), {"eingabe": "x"})
    assert "<html" in antwort.content.decode()


def test_doppelt_abgeschickt_zeigt_hinweis_statt_fehler(kind_client, kind_a, fach):
    s = sitzung_von(los(kind_client, fach))
    # Keine Frage offen (nie gestellt): Hilfe geht nicht
    html = kind_client.post(reverse("lernen:hilfe", args=[s.pk])).content.decode()
    assert "Es ist keine Frage offen" in html


def test_frust_zeigt_pause_vorschlag(kind_client, kind_a, fach, uhr):
    s = sitzung_von(los(kind_client, fach, intensitaet="herausforderung"))
    html = ""
    for _i in range(3):
        services.frage_stellen(s)
        uhr.weiter(seconds=20)
        html = kind_client.post(
            reverse("lernen:antwort", args=[s.pk]), {"eingabe": "zzzzzz"}, **HX
        ).content.decode()
    assert "data-lernen-pause" in html and "Pause" in html


def test_tagesziel_meldung_in_der_rueckmeldung(kind_client, kind_a, fach, uhr):
    from apps.kern import einstellungen

    einstellungen.setzen("lernen.tagesziel_minuten", 5, akteur=None)
    s = sitzung_von(los(kind_client, fach))
    html = ""
    for _i in range(4):
        loesung = services.frage_stellen(s).loesung
        uhr.weiter(seconds=100)
        html = kind_client.post(
            reverse("lernen:antwort", args=[s.pk]), {"eingabe": loesung}, **HX
        ).content.decode()
        if "Tagesziel geschafft" in html:
            break
    assert "Tagesziel geschafft" in html


def test_ungueltige_auswahl(kind_client, fach):
    for was in ("", "fach:abc", "fach:99999", "thema:99999", "quatsch"):
        antwort = kind_client.post(reverse("lernen:los"), {"was": was})
        assert antwort.status_code == 400
        assert "Bitte wähle aus" in antwort.content.decode()
    antwort = kind_client.post(
        reverse("lernen:los"), {"was": f"fach:{fach.pk}", "intensitaet": "x"}
    )
    assert antwort.status_code == 400


def test_nur_fach_mit_fragen_wird_angeboten(kind_client, kind_a, fach):
    leer = Fach.objects.create(schluessel="leeresfach", name="Leeres Fach")
    assert "Leeres Fach" not in kind_client.get(reverse("lernen:start")).content.decode()
    assert kind_client.post(reverse("lernen:los"), {"was": f"fach:{leer.pk}"}).status_code == 400


def test_andere_kinder_fragen_nicht_im_thema(kind_client, kind_a, kind_b, fach):
    from apps.lernen.models import Quelle

    nur_b = Fach.objects.create(schluessel="nurb", name="Nur B")
    thema = nur_b.themen.create(name="Privat", klassenstufe=None)
    Frage.objects.create(thema=thema, frage="a", antwort="b", quelle=Quelle.ELTERN, kind=kind_b)
    assert "Nur B" not in kind_client.get(reverse("lernen:start")).content.decode()


# --- Kachel -------------------------------------------------------------------------------------


def test_kachel_auf_dem_kinder_dashboard(kind_client, kind_a, fach):
    html = kind_client.get(reverse("konten:kind_heim")).content.decode()
    assert 'data-kachel="lernen"' in html
    assert reverse("lernen:start") in html


def test_kachel_zeigt_ziel_erreicht_und_serie(kind_client, kind_a, fach):
    heute = zeit.heute()
    Lernziel.objects.create(kind=kind_a, ziel_minuten=20, seit=heute - timedelta(weeks=3))
    montag = heute - timedelta(days=heute.weekday())
    for w in (1, 2):
        for i in range(3):
            Lerntag.objects.create(
                kind=kind_a,
                datum=montag - timedelta(weeks=w) + timedelta(days=i),
                sekunden=1300,
                ziel_minuten=20,
                mindesttag=True,
                erreicht=True,
            )
    Lerntag.objects.create(
        kind=kind_a, datum=heute, sekunden=1300, ziel_minuten=20, mindesttag=True, erreicht=True
    )
    html = kind_client.get(reverse("konten:kind_heim")).content.decode()
    assert "Tagesziel geschafft!" in html and "2 Wochen in Folge" in html


def test_kachel_im_schontag(kind_client, kind_a, fach):
    Lernpause.objects.create(kind=kind_a, von=zeit.heute(), bis=zeit.heute())
    assert "Schontag" in kind_client.get(reverse("konten:kind_heim")).content.decode()


def test_kachel_fuer_eltern_ohne_vergleich(eltern_client, kind_a, kind_b, fach):
    html = eltern_client.get(reverse("konten:eltern_heim")).content.decode()
    assert 'data-kachel="lernen"' in html
    assert "Testkind A" in html and "Testkind B" in html
    assert reverse("lernen:eltern") in html


def test_kachel_kontext_fuer_eltern_ist_leer(mama, rf):
    from apps.lernen import registry

    anfrage = rf.get("/")
    anfrage.user = mama
    assert registry._kind(anfrage) == {}


# --- Eltern --------------------------------------------------------------------------------------


def test_eltern_seite(eltern_client, kind_a, kind_b, fach):
    Lernziel.objects.create(kind=kind_a, ziel_minuten=10, vorschlag_minuten=15, seit=zeit.heute())
    html = eltern_client.get(reverse("lernen:eltern")).content.decode()
    assert "Testkind A" in html and "Testkind B" in html
    assert "Tagesziel auf 15 Minuten" in html
    assert "Keine Pausen eingetragen" in html
    assert "Schonung" in html


def test_pause_eintragen_und_loeschen(eltern_client, kind_a, db):
    heute = zeit.heute()
    antwort = eltern_client.post(
        reverse("lernen:pause_neu"),
        {
            "kind": str(kind_a.pk),
            "von": heute.isoformat(),
            "bis": (heute + timedelta(days=2)).isoformat(),
            "grund": "krank",
        },
    )
    assert antwort.status_code == 302
    p = Lernpause.objects.get()
    assert (p.kind_id, p.grund) == (kind_a.pk, "krank")
    assert "Testkind A" in eltern_client.get(reverse("lernen:eltern")).content.decode()
    eltern_client.post(
        reverse("lernen:pause_neu"),
        {"kind": "", "von": heute.isoformat(), "bis": heute.isoformat(), "grund": "ferien"},
    )
    assert Lernpause.objects.filter(kind__isnull=True).exists()
    assert "Alle Kinder" in eltern_client.get(reverse("lernen:eltern")).content.decode()
    eltern_client.post(reverse("lernen:pause_loeschen", args=[p.pk]))
    assert not Lernpause.objects.filter(pk=p.pk).exists()


@pytest.mark.parametrize(
    "daten",
    [
        {"von": "kaputt", "bis": "2026-10-23"},
        {"von": "2026-10-24", "bis": "2026-10-23"},
        {"von": "2026-10-23", "bis": "2026-10-23", "grund": "egal"},
        {"von": "2026-10-23", "bis": "2026-10-23", "kind": "kein-uuid"},
    ],
)
def test_pause_ungueltig(eltern_client, db, daten):
    antwort = eltern_client.post(reverse("lernen:pause_neu"), daten)
    assert antwort.status_code == 400
    assert not Lernpause.objects.exists()


def test_pause_fuer_unbekanntes_kind_ist_404(eltern_client, db):
    antwort = eltern_client.post(
        reverse("lernen:pause_neu"),
        {"kind": "00000000-0000-0000-0000-000000000000", "von": "2026-10-23", "bis": "2026-10-23"},
    )
    assert antwort.status_code == 404


def test_pause_loeschen_nur_eltern_und_post(eltern_client, kind_client, db):
    p = Lernpause.objects.create(von=date(2026, 10, 1), bis=date(2026, 10, 2))
    assert kind_client.post(reverse("lernen:pause_loeschen", args=[p.pk])).status_code == 403
    assert eltern_client.get(reverse("lernen:pause_loeschen", args=[p.pk])).status_code == 405
    assert eltern_client.post(reverse("lernen:pause_loeschen", args=[9999])).status_code == 404


def test_thema_waehlen(kind_client, kind_a, fach):
    tiere = fach.themen.get(name="Tiere")
    s = sitzung_von(los(kind_client, fach, thema=tiere))
    assert s.thema == tiere
    assert services.frage_stellen(s).frage.thema_id == tiere.pk


def test_kleinkram_aus_etappe_1(kind_a, fach):
    assert "G" in str(services.leistungsstufe_setzen(kind_a, fach, "G", 5))
    assert services.speicher_limit_bytes() == 500 * 1024 * 1024
