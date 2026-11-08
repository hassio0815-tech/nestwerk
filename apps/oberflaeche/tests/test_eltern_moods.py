"""Moods der Eltern (früher Wappen): Katalog, Wahl in den Einstellungen, Anzeige, eigene Moods,
Trennung von den Kinder-Moods, Datenmigration."""

import pytest
from django.apps import apps as django_apps
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.konten import moods, selectors, services
from apps.konten.models import Benutzer, MoodAusgeblendet, MoodEigen
from apps.konten.tests.conftest import kind_anmelden

ALTE_WAPPEN = {
    "hausdrache": ("🐉", "Hausdrache", "Bewacht den Kühlschrank"),
    "rudelchef": ("🦁", "Rudelchef", "Hat das letzte Wort … meistens"),
    "kuechenchef": ("🍳", "Küchenchef", "Heute gibt's, was auf den Tisch kommt"),
    "familientaxi": ("🚕", "Familien-Taxi", "24/7 im Einsatz"),
    "bank": ("🏦", "Bank of Mama/Papa", "Kein Dispo!"),
    "grillmeister": ("🔥", "Grillmeister", "Fasst die Zange nicht ab"),
    "nachteule": ("🦉", "Nachteule", "Sieht alles, auch nach 22 Uhr"),
    "sockenfinder": ("🧦", "Sockenfinder", "Kennt jeden verlorenen Socken"),
    "burgherr": ("🛡️", "Burgherr/Burgfrau", "Hüter des Nests"),
}


def u(name, *args):
    return reverse(f"oberflaeche:{name}", args=args)


@pytest.fixture
def kind_client(db, anna):
    c = Client()
    kind_anmelden(c, anna)
    return c


# --- Katalog ------------------------------------------------------------------------------------


def test_eltern_katalog_hat_alte_wappen_und_geek():
    assert len(moods.KATALOG_ELTERN) == 10
    for schluessel, (emoji, titel, spruch) in ALTE_WAPPEN.items():
        m = moods.info(schluessel, moods.ELTERN)
        assert (m.emoji, str(m.titel), str(m.spruch)) == (emoji, titel, spruch)
    geek = moods.info("geek", moods.ELTERN)
    assert geek.emoji == "🤓" and str(geek.titel) == "Geek"
    assert str(geek.spruch) == "Hat für alles ein Kabel"
    with translation.override("en"):
        assert str(geek.spruch) == "Has a cable for everything"


def test_kataloge_sind_getrennt_und_schluessel_ueberschneidungsfrei():
    kind_keys = {m.schluessel for m in moods.KATALOG}
    eltern_keys = {m.schluessel for m in moods.KATALOG_ELTERN}
    assert not kind_keys & eltern_keys
    assert moods.info("hausdrache") is None
    assert moods.info("faultier", moods.ELTERN) is None
    assert {s for s, _t, _g in selectors.mood_auswahl(moods.ELTERN)} == eltern_keys
    assert not {s for s, _t, _g in selectors.mood_auswahl(moods.KIND)} & eltern_keys


def test_eltern_moods_sind_uebersetzt():
    m = moods.info("hausdrache", moods.ELTERN)
    assert str(m.titel) == "Hausdrache"
    with translation.override("en"):
        assert str(m.titel) == "House Dragon"
        assert str(m.spruch) == "Guards the fridge"
        assert "Bank of Mum and Dad" in {str(x.titel) for x in moods.KATALOG_ELTERN}


def test_zufallsmood_unterschiedlich_bei_zwei_eltern(db):
    for _ in range(15):
        Benutzer.objects.all().delete()
        a = services.eltern_anlegen("A", rolle_label="mama")
        b = services.eltern_anlegen("B", rolle_label="papa")
        assert a.mood in moods.NACH_SCHLUESSEL_ELTERN
        assert b.mood in moods.NACH_SCHLUESSEL_ELTERN
        assert a.mood != b.mood


# --- Wahl in den Einstellungen --------------------------------------------------------------------


def test_mood_aendern_ueber_einstellungen(eltern_client, mama):
    url = u("mood")
    antwort = eltern_client.post(url, {"mood": "grillmeister"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200
    assert "Gespeichert" in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.mood == "grillmeister"
    antwort = eltern_client.post(url, {"mood": "gibtsnicht"}, HTTP_HX_REQUEST="true")
    assert "Diesen Mood gibt es nicht" in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.mood == "grillmeister"
    eltern_client.post(url, {"mood": "geek"}, HTTP_HX_REQUEST="true")
    mama.refresh_from_db()
    assert mama.mood == "geek"


def test_eltern_koennen_keinen_kinder_mood_waehlen(eltern_client, mama):
    services.eltern_mood_setzen(mama, "nachteule")
    antwort = eltern_client.post(u("mood"), {"mood": "faultier"}, HTTP_HX_REQUEST="true")
    assert "Diesen Mood gibt es nicht" in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.mood == "nachteule"


def test_einstellungen_zeigen_auswahl_wie_bei_kindern(eltern_client, mama):
    services.eltern_mood_setzen(mama, "hausdrache")
    html = eltern_client.get(u("einstellungen")).content.decode()
    assert "Mein Mood und meine Rolle" in html and "Wappen" not in html
    assert "<optgroup" in html and 'value="geek"' in html and "🤓 Geek" in html
    assert "Bewacht den Kühlschrank" in html  # Spruch des gewählten Moods
    assert 'value="faultier"' not in html  # keine Kinder-Moods


def test_kind_sieht_keine_eltern_moods(kind_client, anna):
    html = kind_client.get(u("kind_einstellungen")).content.decode()
    assert 'value="faultier"' in html
    assert 'value="hausdrache"' not in html and 'value="geek"' not in html


def test_kind_darf_keinen_eltern_mood_setzen(kind_client, anna):
    from django.core.exceptions import ValidationError

    antwort = kind_client.post(u("kind_mood"), {"mood": "hausdrache"})
    assert antwort.status_code == 422
    anna.refresh_from_db()
    assert anna.mood == ""
    with pytest.raises(ValidationError):
        services.mood_setzen(anna, "geek")
    # Auch ein (manipulierter) Eltern-Schlüssel am Kind wird nicht angezeigt
    Benutzer.objects.filter(pk=anna.pk).update(mood="hausdrache")
    anna.refresh_from_db()
    assert selectors.mood_text(anna) == ""
    assert anna.mood_info is None


def test_eltern_mood_setzen_nur_fuer_eltern(anna):
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.eltern_mood_setzen(anna, "geek")


# --- Anzeige ------------------------------------------------------------------------------------


def test_login_kachel_und_dashboard_zeigen_mood(client, eltern_client, mama):
    services.eltern_mood_setzen(mama, "hausdrache")
    start = client.__class__().get(reverse("konten:start")).content.decode()
    assert "🐉" in start and "Hausdrache" in start
    assert "🐉 Hausdrache" not in start  # Emoji nur im Ring, nicht doppelt im Text
    heim = eltern_client.get(u("eltern_heim")).content.decode()
    assert "🐉 Hausdrache" in heim


def test_familie_zeigt_eltern_mood(eltern_client, mama):
    services.eltern_mood_setzen(mama, "geek")
    html = eltern_client.get(u("familie")).content.decode()
    assert "🤓 Geek" in html


def test_name_mit_mood_fuer_kinder_texte(mama):
    services.eltern_mood_setzen(mama, "nachteule")
    assert mama.name_mit_mood == f"{mama.anzeigename} (🦉 Nachteule)"


def test_rolle_setzen_ueberschreiben_und_fallback(client, eltern_client, mama):
    url = u("mood")
    services.eltern_mood_setzen(mama, "hausdrache")
    assert mama.name_mit_mood == f"{mama.anzeigename} (🐉 Hausdrache)"
    heim = eltern_client.get(u("eltern_heim")).content.decode()
    assert f"Hallo {mama.anzeigename}!" in heim and "🐉 Hausdrache" in heim
    eltern_client.post(
        url,
        {"mood": "hausdrache", "wappen_rolle": "mum", "wappen_rolle_eigen": ""},
        HTTP_HX_REQUEST="true",
    )
    mama.refresh_from_db()
    assert mama.rolle_anzeige == "Mum"
    assert mama.name_mit_mood == "Mum (🐉 Hausdrache)"
    heim = eltern_client.get(u("eltern_heim")).content.decode()
    assert "Hallo" in heim and "Mum" in heim and "🐉 Hausdrache" in heim
    start = client.__class__().get(reverse("konten:start")).content.decode()
    assert "Mum" in start
    eltern_client.post(
        url,
        {"mood": "hausdrache", "wappen_rolle": "mum", "wappen_rolle_eigen": " Mami "},
        HTTP_HX_REQUEST="true",
    )
    mama.refresh_from_db()
    assert mama.wappen_rolle_eigen == "Mami" and mama.name_mit_mood == "Mami (🐉 Hausdrache)"
    antwort = eltern_client.post(url, {"wappen_rolle_eigen": "x" * 16}, HTTP_HX_REQUEST="true")
    assert 'role="alert"' in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.wappen_rolle_eigen == "Mami"


def test_bestehende_eltern_haben_leere_rolle(db):
    b = services.eltern_anlegen("Opa")
    assert b.wappen_rolle == "" and b.wappen_rolle_eigen == "" and b.rolle_name == "Opa"


def test_wizard_speichert_rolle_und_mood(db):
    from apps.einrichtung import services as ei

    daten = {}
    for i, n in ((1, "Eva"), (2, "Tom")):
        daten.update(
            {
                f"eltern{i}_name": n,
                f"eltern{i}_rolle": "andere",
                f"eltern{i}_email": f"{n}@x.de",
                f"eltern{i}_mood": "geek" if i == 1 else "",
                f"eltern{i}_wappen_rolle": "dad" if i == 2 else "",
                f"eltern{i}_wappen_rolle_eigen": "Mami" if i == 1 else "",
            }
        )
    ei.eltern_speichern(daten)
    e, t = Benutzer.objects.get(anzeigename="Eva"), Benutzer.objects.get(anzeigename="Tom")
    assert e.rolle_anzeige == "Mami" and t.rolle_anzeige == "Dad"
    assert e.mood == "geek" and t.mood in moods.NACH_SCHLUESSEL_ELTERN and t.mood != "geek"


# --- Eigene Eltern-Moods und Ausblenden ---------------------------------------------------------


def test_eigenen_eltern_mood_anlegen_waehlen_und_entfernen(eltern_client, mama):
    antwort = eltern_client.post(
        u("eltern_mood_neu"), {"text": "Kaffeejunkie", "zielgruppe": "eltern"}
    )
    assert antwort.status_code == 302
    eigen = MoodEigen.objects.get(text="Kaffeejunkie")
    assert eigen.zielgruppe == moods.ELTERN
    # nur für Eltern wählbar
    assert eigen.schluessel in {s for s, _t, _g in selectors.mood_auswahl(moods.ELTERN)}
    assert eigen.schluessel not in {s for s, _t, _g in selectors.mood_auswahl(moods.KIND)}
    html = eltern_client.get(u("einstellungen")).content.decode()
    assert "⭐ Kaffeejunkie" in html
    eltern_client.post(u("mood"), {"mood": eigen.schluessel}, HTTP_HX_REQUEST="true")
    mama.refresh_from_db()
    assert mama.mood == eigen.schluessel and mama.mood_info.anzeige == "⭐ Kaffeejunkie"
    heim = eltern_client.get(u("eltern_heim")).content.decode()
    assert "⭐ Kaffeejunkie" in heim
    # entfernen: Mood verschwindet aus Auswahl und Anzeige
    eltern_client.post(u("eltern_mood_entfernen", eigen.pk))
    mama.refresh_from_db()
    assert mama.mood_info is None


def test_eigener_mood_standard_ist_kind_und_texte_sind_je_zielgruppe_eindeutig(eltern_client):
    eltern_client.post(u("eltern_mood_neu"), {"text": "Doppelt"})
    assert MoodEigen.objects.get(text="Doppelt").zielgruppe == moods.KIND
    # gleicher Text bei den Eltern ist erlaubt (getrennte Kataloge) ...
    eltern_client.post(u("eltern_mood_neu"), {"text": "Doppelt", "zielgruppe": "eltern"})
    assert MoodEigen.objects.filter(text="Doppelt").count() == 2
    # ... aber nicht zweimal in derselben Zielgruppe, und nicht wie ein Katalog-Mood
    antwort = eltern_client.post(u("eltern_mood_neu"), {"text": "doppelt", "zielgruppe": "eltern"})
    assert antwort.status_code == 422
    antwort = eltern_client.post(u("eltern_mood_neu"), {"text": "geek", "zielgruppe": "eltern"})
    assert antwort.status_code == 422
    antwort = eltern_client.post(u("eltern_mood_neu"), {"text": "Hausdrache"})  # bei Kindern frei
    assert antwort.status_code == 302


def test_eltern_mood_ausblenden_betrifft_nur_eltern(eltern_client, mama):
    eltern_client.post(u("eltern_mood_katalog", "geek"), {"ausblenden": "1"})
    assert MoodAusgeblendet.objects.filter(schluessel="geek").exists()
    assert "geek" not in {s for s, _t, _g in selectors.mood_auswahl(moods.ELTERN)}
    antwort = eltern_client.post(u("mood"), {"mood": "geek"}, HTTP_HX_REQUEST="true")
    assert "Diesen Mood gibt es nicht" in antwort.content.decode()
    # Kinder-Auswahl unverändert
    assert len(selectors.mood_auswahl(moods.KIND)) == len(moods.KATALOG)
    eltern_client.post(u("eltern_mood_katalog", "geek"))
    assert "geek" in {s for s, _t, _g in selectors.mood_auswahl(moods.ELTERN)}


def test_moods_seite_hat_zwei_abschnitte(eltern_client):
    html = eltern_client.get(u("eltern_moods")).content.decode()
    assert 'data-zielgruppe="kind"' in html and 'data-zielgruppe="eltern"' in html
    assert "Moods für Kinder" in html and "Moods für Eltern" in html
    assert "🤓 Geek" in html and "Faultier-Modus" in html


def test_kind_vorschlag_gilt_nur_fuer_kinder(eltern_client, kind_client, anna):
    kind_client.post(u("kind_mood_vorschlag"), {"text": "Sofa-Ninja"})
    from apps.konten.models import MoodVorschlag

    v = MoodVorschlag.objects.get(text="Sofa-Ninja")
    eltern_client.post(u("eltern_mood_zulassen", v.pk))
    assert MoodEigen.objects.get(text="Sofa-Ninja").zielgruppe == moods.KIND
    assert not [t for _s, t, _g in selectors.mood_auswahl(moods.ELTERN) if "Sofa-Ninja" in t]


# --- Datenmigration -------------------------------------------------------------------------------


def test_heutige_wappen_schluessel_gelten_weiter(db):
    for schluessel in ALTE_WAPPEN:
        b = services.eltern_anlegen(f"E-{schluessel}", mood=schluessel)
        b.refresh_from_db()
        assert b.mood_info.titel == ALTE_WAPPEN[schluessel][1]
    felder = {f.name for f in django_apps.get_model("konten", "Benutzer")._meta.get_fields()}
    assert "mood" in felder and "wappen" not in felder


def test_eltern_aendern_laesst_kein_mood_unveraendert(mama):
    mama.mood = ""
    mama.save(update_fields=["mood"])
    services.eltern_aendern(mama, "Mama", rolle_label="mama", email="")
    mama.refresh_from_db()
    assert mama.mood == ""
    services.eltern_mood_setzen(mama, "hausdrache")
    services.eltern_aendern(mama, "Mama", rolle_label="mama", email="")
    mama.refresh_from_db()
    assert mama.mood == "hausdrache"


def test_ausgeblendeter_eltern_mood_wird_nicht_angezeigt(mama):
    services.eltern_mood_setzen(mama, "hausdrache")
    assert mama.mood_info is not None
    MoodAusgeblendet.objects.create(schluessel="hausdrache")
    assert mama.mood_info is None


def test_kaputter_eigen_schluessel_wirft_nicht(mama):
    for kaputt in ("eigen-", "eigen-abc", "eigen-1x", "eigen-\u0663"):
        mama.mood = kaputt
        assert mama.mood_info is None
