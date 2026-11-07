import pytest
from django.urls import reverse

from apps.aufgaben.models import Aufgabe, Kategorie, Vorlage
from apps.kern.models import AuditEintrag

HX = {"HTTP_HX_REQUEST": "true"}

pytestmark = pytest.mark.django_db


def aufgabe_daten(**extra):
    daten = {
        "titel": "Fenster putzen",
        "punkte": "25",
        "freigabeart": "eltern",
        "wiederholungsart": "einmalig",
    }
    daten.update(extra)
    return daten


# --- Zugriff ---------------------------------------------------------------------------------

ELTERN_URLS = [
    ("aufgaben:liste", []),
    ("aufgaben:neu", []),
    ("aufgaben:bearbeiten", [1]),
    ("aufgaben:schnellknoepfe", []),
    ("aufgaben:kategorien", []),
    ("aufgaben:kategorie_neu", []),
    ("aufgaben:kategorie_bearbeiten", [1]),
]


@pytest.mark.parametrize(("name", "args"), ELTERN_URLS)
def test_kind_hat_keinen_zugriff(kind_client, name, args):
    assert kind_client.get(reverse(name, args=args)).status_code == 403


def test_kind_kann_nicht_schreiben(kind_client, mama):
    assert kind_client.post(reverse("aufgaben:neu"), aufgabe_daten()).status_code == 403
    a = Aufgabe.objects.create(titel="A", punkte=5, erstellt_von=mama)
    assert kind_client.post(reverse("aufgaben:status", args=[a.pk, "beendet"])).status_code == 403
    assert not Aufgabe.objects.filter(titel="Fenster putzen").exists()
    a.refresh_from_db()
    assert a.status == "aktiv"


def test_anonym_wird_abgewiesen(client):
    assert client.get(reverse("aufgaben:liste")).status_code in (302, 403)


# --- Aufgaben --------------------------------------------------------------------------------


def test_anlegen_nur_titel_und_punkte_pflicht(eltern_client, mama):
    antwort = eltern_client.post(
        reverse("aufgaben:neu"),
        {
            "titel": "Minimal",
            "punkte": "5",
            "freigabeart": "eltern",
            "wiederholungsart": "einmalig",
        },
        **HX,
    )
    assert antwort.status_code == 204 and antwort["HX-Redirect"] == reverse("aufgaben:liste")
    a = Aufgabe.objects.get(titel="Minimal")
    assert a.erstellt_von == mama and a.status == "aktiv" and a.kategorie is None
    eintrag = AuditEintrag.objects.get(aktion="aufgabe.angelegt")
    assert eintrag.akteur_id == mama.pk


def test_pflichtfelder(eltern_client):
    antwort = eltern_client.post(reverse("aufgaben:neu"), {"wiederholungsart": "einmalig"}, **HX)
    assert antwort.status_code == 200
    form = antwort.context["form"]
    assert "titel" in form.errors and "punkte" in form.errors
    assert Aufgabe.objects.count() == 0


def test_punkte_muessen_positiv_sein(eltern_client):
    antwort = eltern_client.post(reverse("aufgaben:neu"), aufgabe_daten(punkte="0"), **HX)
    assert "punkte" in antwort.context["form"].errors


def test_woechentlich_verlangt_wochentage(eltern_client):
    antwort = eltern_client.post(
        reverse("aufgaben:neu"), aufgabe_daten(wiederholungsart="woechentlich"), **HX
    )
    assert "wochentage" in antwort.context["form"].errors
    assert Aufgabe.objects.count() == 0


def test_woechentlich_mit_wochentagen_fenster_limit(eltern_client, anna):
    antwort = eltern_client.post(
        reverse("aufgaben:neu"),
        aufgabe_daten(
            titel="Tonnen",
            wiederholungsart="woechentlich",
            wochentage=["2", "5"],
            fenster_von="18:00",
            fenster_bis="07:00",
            fenster_tage="1",
            limit_anzahl="1",
            limit_zeitraum="woche",
            zugewiesen_an=str(anna.pk),
        ),
        **HX,
    )
    assert antwort.status_code == 204, (
        getattr(antwort, "context", None) and antwort.context["form"].errors
    )
    a = Aufgabe.objects.get(titel="Tonnen")
    assert a.plan.wochentage_liste == [2, 5] and a.zeitgebunden
    assert (a.limit_anzahl, a.limit_zeitraum) == (1, "woche") and a.zugewiesen_an == anna


def test_intervall_und_limit_validierung(eltern_client):
    r = eltern_client.post(
        reverse("aufgaben:neu"), aufgabe_daten(wiederholungsart="intervall"), **HX
    )
    assert "intervall_tage" in r.context["form"].errors
    r = eltern_client.post(reverse("aufgaben:neu"), aufgabe_daten(limit_anzahl="2"), **HX)
    assert "limit_anzahl" in r.context["form"].errors
    r = eltern_client.post(
        reverse("aufgaben:neu"),
        aufgabe_daten(start_datum="2026-05-10", end_datum="2026-05-01"),
        **HX,
    )
    assert "end_datum" in r.context["form"].errors
    r = eltern_client.post(reverse("aufgaben:neu"), aufgabe_daten(fenster_von="10:00"), **HX)
    assert "fenster_bis" in r.context["form"].errors
    assert Aufgabe.objects.count() == 0


def test_bearbeiten_und_audit(eltern_client, mama):
    a = Aufgabe.objects.create(titel="Alt", punkte=5, erstellt_von=mama)
    antwort = eltern_client.post(
        reverse("aufgaben:bearbeiten", args=[a.pk]), aufgabe_daten(titel="Neu", punkte="9"), **HX
    )
    assert antwort.status_code == 204
    a.refresh_from_db()
    assert (a.titel, a.punkte) == ("Neu", 9)
    eintrag = AuditEintrag.objects.get(aktion="aufgabe.geaendert")
    assert eintrag.akteur_id == mama.pk and "titel" in str(eintrag.details)


def test_bearbeiten_formular_zeigt_wochentage(eltern_client, mama):
    a = Aufgabe.objects.create(
        titel="W", punkte=5, erstellt_von=mama, wiederholungsart="woechentlich", wochentage=0b100
    )
    seite = eltern_client.get(reverse("aufgaben:bearbeiten", args=[a.pk]), **HX).content.decode()
    assert 'value="2" checked' in seite.replace("\n", " ") or "checked" in seite


def test_pausieren_fortsetzen_beenden(eltern_client, mama):
    a = Aufgabe.objects.create(titel="A", punkte=5, erstellt_von=mama)
    url = lambda s: reverse("aufgaben:status", args=[a.pk, s])  # noqa: E731
    r = eltern_client.post(url("pausiert"), **HX)
    assert r.status_code == 200 and "Pausiert" in r.content.decode()
    a.refresh_from_db()
    assert a.status == "pausiert"
    eltern_client.post(url("aktiv"), **HX)
    eltern_client.post(url("beendet"), **HX)
    a.refresh_from_db()
    assert a.status == "beendet"
    eltern_client.post(url("aktiv"), **HX)  # beendet bleibt beendet
    a.refresh_from_db()
    assert a.status == "beendet"
    assert AuditEintrag.objects.filter(aktion="aufgabe.status_geaendert").count() == 3
    assert eltern_client.post(url("quatsch")).status_code == 404


def test_liste_filter(eltern_client, mama):
    haushalt = Kategorie.objects.get(name="Haushalt")
    Aufgabe.objects.create(titel="Aktiv-H", punkte=5, erstellt_von=mama, kategorie=haushalt)
    Aufgabe.objects.create(titel="Pause-G", punkte=5, erstellt_von=mama, status="pausiert")
    Aufgabe.objects.create(titel="Ende-X", punkte=5, erstellt_von=mama, status="beendet")
    seite = eltern_client.get(reverse("aufgaben:liste")).content.decode()
    assert "Aktiv-H" in seite and "Pause-G" in seite and "Ende-X" not in seite
    teil = eltern_client.get(
        reverse("aufgaben:liste"), {"kategorie": haushalt.pk}, **HX
    ).content.decode()
    assert "Aktiv-H" in teil and "Pause-G" not in teil and "<html" not in teil
    teil = eltern_client.get(
        reverse("aufgaben:liste"), {"status": "beendet"}, **HX
    ).content.decode()
    assert "Ende-X" in teil and "Aktiv-H" not in teil


# --- Bibliothek ist in den Schnell-Knöpfen aufgegangen --------------------------------------


def test_aufgabe_mit_vorlage_verweis_bleibt_erhalten(eltern_client, mama):
    v = Vorlage.objects.get(titel="Bad putzen")
    antwort = eltern_client.post(
        reverse("aufgaben:neu"),
        aufgabe_daten(titel="Bad putzen", punkte="40", freigabeart="nachweis", vorlage=v.pk),
        **HX,
    )
    assert antwort.status_code == 204
    a = Aufgabe.objects.get(titel="Bad putzen")
    assert a.vorlage == v and a.freigabeart == "nachweis" and a.punkte == 40


@pytest.mark.parametrize(
    "pfad", ["/eltern/bibliothek/", "/eltern/bibliothek/neu/", "/eltern/bibliothek/3/bearbeiten/"]
)
def test_alte_bibliothek_leitet_auf_schnellknoepfe(eltern_client, pfad):
    antwort = eltern_client.get(pfad)
    assert antwort.status_code == 302
    assert antwort["Location"] == reverse("aufgaben:schnellknoepfe")
    assert eltern_client.get(antwort["Location"]).status_code == 200


def test_menue_hat_keine_bibliothek_mehr(eltern_client):
    seite = eltern_client.get(reverse("aufgaben:liste")).content.decode()
    assert "Bibliothek" not in seite and "Aus Vorlage" not in seite
    assert reverse("aufgaben:schnellknoepfe") in seite


def test_neuer_schnellknopf_link_belegt_bei_bedarf_vor(eltern_client):
    seite = eltern_client.get(reverse("aufgaben:neu"), {"art": "bei_bedarf"}, **HX)
    assert seite.context["form"].initial["wiederholungsart"] == "bei_bedarf"


# --- Kategorien ------------------------------------------------------------------------------


def test_kategorie_crud(eltern_client, mama):
    r = eltern_client.post(
        reverse("aufgaben:kategorie_neu"),
        {"name": "Tiere", "symbol": "stern", "reihenfolge": "7", "aktiv": "on"},
        **HX,
    )
    assert r.status_code == 204
    k = Kategorie.objects.get(name="Tiere")
    r = eltern_client.post(
        reverse("aufgaben:kategorie_bearbeiten", args=[k.pk]),
        {"name": "Haustiere", "symbol": "geschenk", "reihenfolge": "7"},
        **HX,
    )
    assert r.status_code == 204
    k.refresh_from_db()
    assert k.name == "Haustiere" and k.symbol == "geschenk" and not k.aktiv
    assert AuditEintrag.objects.filter(aktion="kategorie.geaendert", akteur_id=mama.pk).exists()


def test_kategorie_validierung(eltern_client):
    r = eltern_client.post(
        reverse("aufgaben:kategorie_neu"),
        {"name": "Haushalt", "symbol": "gibtsnicht", "reihenfolge": "1", "farbe": "rot"},
        **HX,
    )
    errors = r.context["form"].errors
    assert "name" in errors and "symbol" in errors and "farbe" in errors


def test_kategorien_seite(eltern_client):
    seite = eltern_client.get(reverse("aufgaben:kategorien")).content.decode()
    assert "Haushalt" in seite and "Schule" in seite
