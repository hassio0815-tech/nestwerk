import pytest
from django.urls import reverse

from apps.belohnung import services
from apps.belohnung.models import Belohnung, Einloeseantrag, Status
from apps.kern import einstellungen
from apps.punkte.models import Art, Buchung

from .conftest import gutschrift

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def test_kind_sieht_kacheln_guthaben_und_nur_eigene_antraege(kind_client, anna, ben, suesses):
    gutschrift(anna, 50)
    gutschrift(ben, 50)
    services.antrag_stellen(anna, suesses)
    ben_antrag = services.antrag_stellen(ben, suesses)
    antwort = kind_client.get(reverse("belohnung:kind"))
    html = antwort.content.decode()
    assert antwort.status_code == 200
    assert "Testsüßes" in html and "30 Punkte" in html
    assert html.count('class="karte"') == 1  # nur Annas Antrag
    assert antwort.context["verfuegbar"] == 20
    assert [a.kind for a in antwort.context["antraege"]] == [anna]
    assert ben_antrag.pk not in [a.pk for a in antwort.context["antraege"]]


def test_zu_teure_kachel_ist_gesperrt(kind_client, anna, suesses):
    gutschrift(anna, 10)
    html = kind_client.get(reverse("belohnung:kind")).content.decode()
    assert "disabled" in html and "Noch 20 Punkte" in html


def test_beantragen_per_htmx_und_fehler(kind_client, anna, suesses):
    gutschrift(anna, 50)
    url = reverse("belohnung:beantragen", args=[suesses.pk])
    ok = kind_client.post(url, **HX)
    assert ok.status_code == 200 and "Antrag für" in ok.content.decode()
    nein = kind_client.post(url, **HX)  # nur 20 verfügbar
    assert "fehlen dir noch 10 Punkte" in nein.content.decode()
    assert Einloeseantrag.objects.count() == 1


def test_fremden_antrag_nicht_zurueckziehen(kind_client, ben, suesses):
    gutschrift(ben, 50)
    fremd = services.antrag_stellen(ben, suesses)
    antwort = kind_client.post(reverse("belohnung:zurueckziehen", args=[fremd.pk]))
    assert antwort.status_code == 404
    fremd.refresh_from_db()
    assert fremd.status == Status.OFFEN


def test_eigenen_antrag_zurueckziehen(kind_client, anna, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    kind_client.post(reverse("belohnung:zurueckziehen", args=[antrag.pk]), **HX)
    antrag.refresh_from_db()
    assert antrag.status == Status.ZURUECKGEZOGEN


def test_eltern_urls_sind_fuer_kinder_gesperrt(kind_client, anna, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    for name, args in [
        ("belohnung:antraege", []),
        ("belohnung:katalog", []),
        ("belohnung:neu", []),
        ("belohnung:bestaetigen", [antrag.pk]),
        ("belohnung:ablehnen", [antrag.pk]),
    ]:
        url = reverse(name, args=args)
        assert kind_client.get(url).status_code in (403, 405), name
        assert kind_client.post(url).status_code == 403, name
    assert not Buchung.objects.filter(art=Art.EINLOESUNG).exists()


def test_kind_urls_sind_fuer_eltern_gesperrt(eltern_client):
    assert eltern_client.get(reverse("belohnung:kind")).status_code == 403


def test_eltern_bestaetigen_doppelklick_bucht_einmal(eltern_client, anna, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    seite = eltern_client.get(reverse("belohnung:antraege"))
    assert "Anna: Testsüßes" in seite.content.decode()
    url = reverse("belohnung:bestaetigen", args=[antrag.pk])
    assert eltern_client.post(url, **HX).status_code == 200
    assert eltern_client.post(url, **HX).status_code == 200
    assert Buchung.objects.filter(art=Art.EINLOESUNG).count() == 1


def test_eltern_ablehnen_mit_grund(eltern_client, anna, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    eltern_client.post(
        reverse("belohnung:ablehnen", args=[antrag.pk]), {"grund": "Erst Hausaufgaben"}, **HX
    )
    antrag.refresh_from_db()
    assert (antrag.status, antrag.ablehnungsgrund) == (Status.ABGELEHNT, "Erst Hausaufgaben")
    assert not Buchung.objects.filter(art=Art.EINLOESUNG).exists()


def test_katalog_anlegen_bearbeiten_deaktivieren(eltern_client, kategorien):
    liste = eltern_client.get(reverse("belohnung:katalog"))
    assert liste.status_code == 200
    antwort = eltern_client.post(
        reverse("belohnung:neu"),
        {
            "titel": "Kino",
            "kategorie": kategorien["Süßes"].pk,
            "preis_punkte": 120,
            "symbol": "stern",
            "reihenfolge": 9,
            "aktiv": "on",
        },
    )
    assert antwort.status_code == 302
    kino = Belohnung.objects.get(titel="Kino")
    assert kino.geldwert_cent is None
    eltern_client.post(
        reverse("belohnung:bearbeiten", args=[kino.pk]),
        {
            "titel": "Kino groß",
            "kategorie": kategorien["Süßes"].pk,
            "preis_punkte": 150,
            "symbol": "",
            "reihenfolge": 9,
            "aktiv": "on",
        },
    )
    kino.refresh_from_db()
    assert (kino.titel, kino.preis_punkte) == ("Kino groß", 150)
    eltern_client.post(reverse("belohnung:aktiv", args=[kino.pk]), {"aktiv": "0"}, **HX)
    kino.refresh_from_db()
    assert kino.aktiv is False


def test_taschengeld_braucht_betrag_andere_nicht(eltern_client, kategorien):
    daten = {"titel": "Geld", "preis_punkte": 30, "symbol": "", "reihenfolge": 1, "aktiv": "on"}
    ohne = eltern_client.post(
        reverse("belohnung:neu"), {**daten, "kategorie": kategorien["Taschengeld"].pk}
    )
    assert ohne.status_code == 200 and "braucht einen Betrag" in ohne.content.decode()
    mit = eltern_client.post(
        reverse("belohnung:neu"),
        {**daten, "kategorie": kategorien["Taschengeld"].pk, "betrag": "2,50"},
    )
    assert mit.status_code == 302
    assert Belohnung.objects.get(titel="Geld").geldwert_cent == 250
    falsch = eltern_client.post(
        reverse("belohnung:neu"),
        {**daten, "titel": "Falsch", "kategorie": kategorien["Süßes"].pk, "betrag": "1"},
    )
    assert falsch.status_code == 200 and not Belohnung.objects.filter(titel="Falsch").exists()


def test_limit_einstellen(eltern_client, anna):
    eltern_client.post(reverse("belohnung:limit"), {"betrag": "12,50"})
    assert einstellungen.wert("belohnung.taschengeld_limit_cent") == 1250
    prefix = f"k{anna.pk.hex[:8]}"
    eltern_client.post(reverse("belohnung:kind_limit", args=[anna.pk]), {f"{prefix}-betrag": "3"})
    from apps.belohnung import selectors

    assert selectors.limit_cent(anna) == 300
    eltern_client.post(reverse("belohnung:kind_limit", args=[anna.pk]), {f"{prefix}-betrag": ""})
    assert selectors.limit_cent(anna) == 1250
    assert eltern_client.get(reverse("belohnung:katalog")).status_code == 200


def test_nicht_angemeldet_wird_umgeleitet(client):
    assert client.get(reverse("belohnung:kind")).status_code == 302
    assert client.get(reverse("belohnung:antraege")).status_code == 302
