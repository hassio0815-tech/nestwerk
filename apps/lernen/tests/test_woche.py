"""Etappe 7: Beteiligung, Wochen-Titel, Familienansicht, Eltern-Wochenbild (SPEC 21.9, 21.10)."""

from datetime import date, datetime, timedelta

import pytest
from django.urls import reverse

from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen, zeit
from apps.kern.registry import ELTERN, KIND, TABLET, kacheln
from apps.konten import services as konten_services
from apps.konten.tests.conftest import PIN
from apps.lernen import selectors, woche_selectors, woche_services, woche_texte
from apps.lernen.models import (
    Ergebnis,
    Fach,
    Frage,
    Lernpause,
    Lernsitzung,
    Lerntag,
    Pruefung,
    Thema,
    TutorGespraech,
    Versuch,
)
from apps.lernen.woche_selectors import Wochenbild
from apps.punkte.models import Buchung
from apps.spielregeln.models import AbzeichenVerleihung

MONTAG = date(2026, 11, 2)  # Montag der laufenden Woche
VORWOCHE = MONTAG - timedelta(days=7)
MITTWOCH = MONTAG + timedelta(days=2)


@pytest.fixture
def kind_c(db):
    return konten_services.kind_anlegen("Testkind C", PIN)


def tag(kind, datum, *, mindest=True, erreicht=True, ziel=20):
    return Lerntag.objects.create(
        kind=kind,
        datum=datum,
        sekunden=ziel * 60 if erreicht else 360,
        ziel_minuten=ziel,
        mindesttag=mindest,
        erreicht=erreicht,
    )


_fragen = {}


def _frage(thema, nr):
    return _fragen.setdefault(
        (thema.pk, nr), Frage.objects.create(thema=thema, frage=f"f{nr}", antwort=f"a{nr}")
    )


@pytest.fixture(autouse=True)
def _frisch():
    _fragen.clear()


@pytest.fixture
def themen(db):
    f = Fach.objects.create(schluessel="fachx", name="Fach X")
    return (
        Thema.objects.create(fach=f, name="Thema Eins"),
        Thema.objects.create(fach=f, name="Thema Zwei"),
    )


def antworten(kind, tag_, thema, folge, *, hilfe=0):
    """``folge``: Liste von (Frage-Nr., Ergebnis), in dieser Reihenfolge am Tag ``tag_``."""
    beginn = zeit.tag_beginn(tag_) + timedelta(hours=15)
    sitzung = Lernsitzung.objects.create(kind=kind, beginn=beginn, thema=thema, fach=thema.fach)
    for nr, ergebnis in folge:
        v = Versuch.objects.create(
            sitzung=sitzung,
            frage=_frage(thema, nr),
            richtung="de_en",
            ergebnis=ergebnis,
            hilfestufe=hilfe,
        )
        Versuch.objects.filter(pk=v.pk).update(erstellt=beginn)
    return sitzung


def richtig_falsch(richtig, falsch, start=0):
    return [(start + i, Ergebnis.RICHTIG) for i in range(richtig)] + [
        (start + richtig + i, Ergebnis.NOCH_NICHT) for i in range(falsch)
    ]


def namen(titel):
    return {t.schluessel: sorted(k.anzeigename for k in t.kinder) for t in titel}


@pytest.fixture
def klein(db):
    """Kleine Mindestmengen, damit Tests mit wenigen Zeilen auskommen."""
    einstellungen.setzen("lernen.titel_min_versuche", 4, akteur=None)
    einstellungen.setzen("lernen.titel_min_fehler", 2, akteur=None)


# --- Beteiligung (Metrik) -------------------------------------------------------------------


def test_metrik_lern_beteiligung_zaehlt_tage_mit_eigenem_ziel(kind_a, kind_b):
    tag(kind_a, MONTAG, ziel=10)
    tag(kind_a, MONTAG + timedelta(days=1), erreicht=False)
    tag(kind_b, MONTAG, ziel=40)
    assert selectors.lern_beteiligung(kind_a) == 1
    assert selectors.lern_beteiligung(kind_b) == 1  # nicht die Minuten zählen, sondern das Ziel


def test_metrik_und_provider_sind_registriert(db):
    from apps.kern import registry

    assert registry.metrik("lern_beteiligung").modul == "lernen"
    assert registry.provider_vorhanden("metrik.lern_beteiligung")
    assert registry.metrik("tage_geuebt").einheit == "Tage"


def test_metrik_wirkt_in_der_abzeichen_engine(kind_a):
    """Ohne Änderung an spielregeln: eine Regel auf die Metrik wird ausgewertet."""
    from apps.spielregeln import abzeichen
    from apps.spielregeln.models import AbzeichenDefinition

    AbzeichenDefinition.objects.create(
        schluessel="test_beteiligung",
        name="Test",
        metrik="lern_beteiligung",
        vergleich=">=",
        schwelle=1,
    )
    assert abzeichen.pruefen(kind_a, melden=False).verliehen == []
    tag(kind_a, MONTAG)
    assert len(abzeichen.pruefen(kind_a, melden=False).verliehen) == 1


# --- Wochen-Titel ---------------------------------------------------------------------------


def test_uebungsmeister_gleichstand_teilt_den_titel(kind_a, kind_b, kind_c):
    for d in range(3):
        tag(kind_a, VORWOCHE + timedelta(days=d))
        tag(kind_b, VORWOCHE + timedelta(days=d))
    tag(kind_c, VORWOCHE)
    erg = namen(woche_selectors.titel_berechnen([kind_a, kind_b, kind_c], VORWOCHE))
    assert erg == {"uebungsmeister": ["Testkind A", "Testkind B"]}


def test_nur_ein_kind_mit_aktivitaet_keine_titel(kind_a, kind_b):
    for d in range(4):
        tag(kind_a, VORWOCHE + timedelta(days=d))
    assert woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE) == []


def test_ohne_aktivitaet_keine_titel(kind_a, kind_b):
    assert woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE) == []
    assert woche_selectors.titel_berechnen([], VORWOCHE) == []


def test_tag_ohne_erreichtes_ziel_ergibt_keinen_uebungsmeister(kind_a, kind_b):
    tag(kind_a, VORWOCHE, erreicht=False)
    tag(kind_b, VORWOCHE, erreicht=False)
    assert woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE) == []


def test_unterschiedliche_ziele_sind_fair(kind_a, kind_b):
    """A hat ein kleines, B ein großes Ziel. Zählt das eigene Ziel, nicht die Minuten, gewinnt
    B nicht durch Menge: A erreicht sein Ziel an drei Tagen, B (mehr Minuten) an einem."""
    for d in range(3):
        tag(kind_a, VORWOCHE + timedelta(days=d), ziel=5)
    tag(kind_b, VORWOCHE, ziel=45)
    for d in (1, 2):
        tag(kind_b, VORWOCHE + timedelta(days=d), erreicht=False, ziel=45)
    assert namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE)) == {
        "uebungsmeister": ["Testkind A"]
    }


def test_aufsteiger_nur_mit_vorwochendaten(kind_a, kind_b, themen, klein):
    t1, _t2 = themen
    for k in (kind_a, kind_b):
        tag(k, VORWOCHE)
        antworten(k, VORWOCHE, t1, richtig_falsch(4, 4))
    # Diese Woche (die Woche vor VORWOCHE hat keine Daten): kein Aufsteiger
    frueher = VORWOCHE - timedelta(days=7)
    assert woche_selectors.titel_berechnen([kind_a, kind_b], frueher) == []
    ohne = namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE))
    assert "aufsteiger" not in ohne


def test_aufsteiger_weniger_hilfe_mehr_treffer(kind_a, kind_b, themen, klein):
    t1, _t2 = themen
    for k in (kind_a, kind_b):
        tag(k, VORWOCHE - timedelta(days=7))
        tag(k, VORWOCHE)
        antworten(k, VORWOCHE - timedelta(days=7), t1, richtig_falsch(2, 4), hilfe=1)
    antworten(kind_a, VORWOCHE, t1, richtig_falsch(5, 1), hilfe=0)  # deutlich besser
    antworten(kind_b, VORWOCHE, t1, richtig_falsch(2, 4), hilfe=1)  # unverändert
    erg = namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE))
    assert erg["aufsteiger"] == ["Testkind A"]


def test_aufsteiger_braucht_genug_antworten(kind_a, kind_b, themen):
    t1, _t2 = themen  # Standard: mindestens 8 Antworten
    for k in (kind_a, kind_b):
        tag(k, VORWOCHE - timedelta(days=7))
        tag(k, VORWOCHE)
    antworten(kind_a, VORWOCHE - timedelta(days=7), t1, richtig_falsch(1, 3), hilfe=1)
    antworten(kind_a, VORWOCHE, t1, richtig_falsch(4, 0))
    assert "aufsteiger" not in namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE))


def test_durchbeisser_zaehlt_selbst_geklaerte_fehler_relativ(kind_a, kind_b, themen, klein):
    t1, _t2 = themen
    for k in (kind_a, kind_b):
        tag(k, VORWOCHE)
    # A: zwei Fehler, beide später ohne Hilfe richtig -> 100 %
    antworten(kind_a, VORWOCHE, t1, [(1, "noch_nicht"), (2, "noch_nicht"), (1, "richtig")])
    antworten(kind_a, VORWOCHE + timedelta(days=1), t1, [(2, "richtig")])
    # B: viele Fehler, einer geklärt -> 25 % (mehr Rohmenge zählt nicht)
    antworten(
        kind_b,
        VORWOCHE,
        t1,
        [(i, "noch_nicht") for i in range(1, 5)] + [(1, "richtig")],
    )
    erg = namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE))
    assert erg["durchbeisser"] == ["Testkind A"]


def test_durchbeisser_hilfe_zaehlt_nicht_als_selbst(kind_a, kind_b, themen, klein):
    t1, _t2 = themen
    for k in (kind_a, kind_b):
        tag(k, VORWOCHE)
    antworten(kind_a, VORWOCHE, t1, [(1, "noch_nicht"), (2, "noch_nicht")])
    antworten(kind_a, VORWOCHE, t1, [(1, "richtig"), (2, "richtig")], hilfe=2)
    assert "durchbeisser" not in namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE))


def test_entdecker_neues_thema_nicht_in_der_allerersten_woche(kind_a, kind_b, themen):
    t1, t2 = themen
    for k in (kind_a, kind_b):
        tag(k, VORWOCHE)
    antworten(kind_a, VORWOCHE, t1, richtig_falsch(2, 0))
    antworten(kind_b, VORWOCHE, t1, richtig_falsch(2, 0))
    # Erste Woche: alles neu, daher kein Entdecker
    assert "entdecker" not in namen(woche_selectors.titel_berechnen([kind_a, kind_b], VORWOCHE))
    # Eine Woche später: A beginnt ein neues Thema, B bleibt beim alten
    spaeter = VORWOCHE + timedelta(days=7)
    for k in (kind_a, kind_b):
        tag(k, spaeter)
    antworten(kind_a, spaeter, t2, richtig_falsch(2, 0))
    antworten(kind_b, spaeter, t1, richtig_falsch(2, 0))
    erg = namen(woche_selectors.titel_berechnen([kind_a, kind_b], spaeter))
    assert erg["entdecker"] == ["Testkind A"]


def test_titel_bringen_keine_punkte_und_keine_meldung(kind_a, kind_b):
    for d in range(3):
        tag(kind_a, VORWOCHE + timedelta(days=d))
        tag(kind_b, VORWOCHE + timedelta(days=d))
    buchungen = Buchung.objects.count()
    verleihungen = AbzeichenVerleihung.objects.count()
    ereignisse = Ereignis.objects.count()
    titel = woche_selectors.titel_vorwoche([kind_a, kind_b], MITTWOCH)
    assert titel  # es gibt Titel
    assert Buchung.objects.count() == buchungen
    assert AbzeichenVerleihung.objects.count() == verleihungen
    assert Ereignis.objects.count() == ereignisse


def test_titel_abschalten(kind_a, kind_b):
    for d in range(2):
        tag(kind_a, VORWOCHE + timedelta(days=d))
        tag(kind_b, VORWOCHE + timedelta(days=d))
    assert woche_selectors.titel_vorwoche([kind_a, kind_b], MITTWOCH)
    woche_services.titel_umschalten(False, akteur=None)
    assert woche_selectors.titel_anzeigen() is False
    assert woche_selectors.titel_vorwoche([kind_a, kind_b], MITTWOCH) == []
    woche_services.titel_umschalten(True, akteur=None)
    assert woche_selectors.titel_vorwoche([kind_a, kind_b], MITTWOCH)


def test_titeltexte_haben_name_und_beschreibung(db):
    for schluessel in woche_texte.titel_schluessel():
        assert woche_texte.titel_name(schluessel)
        assert woche_texte.titel_beschreibung(schluessel)
    assert woche_texte.titel_name("uebungsmeister") == "Übungsmeister"


# --- Familienansicht: Übungswoche und Familienziel ------------------------------------------


def test_uebungswoche_zeigt_nur_wer_geuebt_hat(kind_a, kind_b):
    tag(kind_a, MONTAG)
    tag(kind_a, MONTAG + timedelta(days=2))
    tag(kind_b, MONTAG, mindest=False, erreicht=False)  # unter dem Mindesttag
    zeilen = woche_selectors.uebungswoche([kind_b, kind_a], MITTWOCH)
    assert [z.kind for z in zeilen] == [kind_a]
    assert [geuebt for _datum, geuebt in zeilen[0].tage] == [
        True,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert woche_selectors.uebungswoche([kind_b], MITTWOCH) == []


def test_familienziel_alle_ueben_an_n_tagen(kind_a, kind_b):
    einstellungen.setzen("lernen.familienziel_tage", 2, akteur=None)
    assert woche_selectors.familienziel([], MITTWOCH) is None
    tag(kind_a, MONTAG)
    tag(kind_a, MONTAG + timedelta(days=1))
    z = woche_selectors.familienziel([kind_a, kind_b], MITTWOCH)
    assert (z.tage, z.teilnehmer, z.erfuellt, z.soll, z.geschafft) == (2, 2, 1, 4, 2)
    assert z.prozent == 50 and not z.erreicht
    tag(kind_b, MONTAG)
    tag(kind_b, MONTAG + timedelta(days=2))
    z = woche_selectors.familienziel([kind_a, kind_b], MITTWOCH)
    assert z.erreicht and z.prozent == 100


def test_familienziel_standard_ist_vier_tage(kind_a):
    assert einstellungen.wert("lernen.familienziel_tage") == 4
    assert woche_selectors.familienziel([kind_a], MITTWOCH).tage == 4


def test_familienziel_pausentage_senken_den_bedarf(kind_a, kind_b):
    einstellungen.setzen("lernen.familienziel_tage", 4, akteur=None)
    Lernpause.objects.create(kind=kind_b, von=MONTAG, bis=MONTAG + timedelta(days=6))
    tag(kind_a, MONTAG)
    z = woche_selectors.familienziel([kind_a, kind_b], MITTWOCH)
    assert z.teilnehmer == 1  # B ist die ganze Woche geschont
    Lernpause.objects.filter(kind=kind_b).update(bis=MONTAG + timedelta(days=1))
    z = woche_selectors.familienziel([kind_a, kind_b], MITTWOCH)
    assert (z.teilnehmer, z.soll) == (2, 4 + 2)  # B braucht nur noch 2 Tage


def test_familienziel_ferien_schalter_schont_den_rest_der_woche(kind_a):
    einstellungen.setzen("lernen.ferien_schalter", True, akteur=None)
    # Mittwoch: Mi bis So (5 Tage) sind geschont -> nichts verlangt
    assert woche_selectors.familienziel([kind_a], MITTWOCH) is None


def test_kachel_ist_fuer_kind_und_tablet_registriert_nicht_fuer_eltern(db):
    assert "lernen.woche" in {k.schluessel for k in kacheln(KIND)}
    assert "lernen.woche" in {k.schluessel for k in kacheln(TABLET)}
    assert "lernen.woche" not in {k.schluessel for k in kacheln(ELTERN)}


def test_kind_ansicht_zeigt_beteiligung_ohne_zahlen_rangliste(kind_client, kind_a, kind_b):
    heute = zeit.heute()
    montag = heute - timedelta(days=heute.weekday())
    tag(kind_b, montag)  # nur Geschwister B hat geübt
    html = kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    assert 'data-kachel="lernen-woche"' in html
    assert "Testkind B" in html  # Beteiligung ist erlaubt
    assert "hat nicht geübt" not in html
    assert "Testkind A" not in html.split("data-woche-beteiligung")[1].split("</ul>")[0]


def test_kind_ansicht_zeigt_keine_lerninhalte_der_geschwister(kind_client, kind_a, kind_b, themen):
    t1, _t2 = themen
    heute = zeit.heute()
    antworten(kind_b, heute, t1, richtig_falsch(1, 5))
    tag(kind_b, heute)
    html = kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    for geheim in ("Thema Eins", "Fach X", "Fehler", "Hilfe"):
        assert geheim not in html


def test_tablet_zeigt_die_uebungswoche(client, kind_a, kind_b):
    heute = zeit.heute()
    tag(kind_a, heute)
    html = client.get("/tablet/").content.decode()
    assert 'data-kachel="lernen-woche"' in html
    assert "Testkind A" in html.split("data-woche-beteiligung")[1]


def test_kachel_zeigt_titel_der_vorwoche_nur_wenn_an(client, kind_a, kind_b):
    heute = zeit.heute()
    vor = heute - timedelta(days=heute.weekday() + 7)
    for k in (kind_a, kind_b):
        tag(k, vor)
    html = client.get("/tablet/").content.decode()
    assert "data-woche-titel" in html and "Übungsmeister" in html
    woche_services.titel_umschalten(False, akteur=None)
    html = client.get("/tablet/").content.decode()
    assert "data-woche-titel" not in html and "Übungsmeister" not in html


def test_kachel_ohne_aktivitaet_fuehrt_niemanden_vor(client, kind_a, kind_b):
    html = client.get("/tablet/").content.decode()
    assert 'data-kachel="lernen-woche"' in html
    assert "Testkind" not in html.split('data-kachel="lernen-woche"')[1].split("</article>")[0]


# --- Eltern-Wochenbild ----------------------------------------------------------------------


def test_wochenbild_tage_hilfe_verlauf_und_schwaechen(kind_a, themen):
    t1, _t2 = themen
    tag(kind_a, MONTAG)
    tag(kind_a, MONTAG + timedelta(days=1), erreicht=False)
    antworten(kind_a, VORWOCHE, t1, richtig_falsch(3, 1), hilfe=1)
    antworten(kind_a, MONTAG, t1, richtig_falsch(2, 6), hilfe=0)
    b = woche_selectors.wochenbild(kind_a, MITTWOCH)
    assert (b.tage_geuebt, b.tage_ziel, b.soll_tage) == (2, 1, 3)
    assert b.antworten == 8 and b.hilfe_prozent == 0
    assert [p.hilfe for p in b.verlauf][-2:] == [100, 0]
    assert b.hilfe_tendenz == "sinkt"
    assert [(s.fach, s.thema, s.fehler) for s in b.schwaechen] == [("Fach X", "Thema Eins", 6)]
    texte = [v.text for v in b.vorschlaege]
    assert any("Thema Eins" in t and "Plane 10 Minuten Thema Eins ein" in t for t in texte)


def test_wochenbild_ohne_daten_ist_leer_und_ruhig(kind_a):
    b = woche_selectors.wochenbild(kind_a, MONTAG + timedelta(days=1))
    assert b.antworten == 0 and b.hilfe_prozent is None and b.hilfe_tendenz == ""
    assert b.verlauf and all(p.hilfe is None for p in b.verlauf)
    assert b.vorschlaege == []  # Dienstag: noch kein Hinweis


def test_wochenbild_selbsteinschaetzung_meldungen_pruefung(kind_a, themen):
    t1, _t2 = themen
    for i in range(2):
        s = antworten(kind_a, MONTAG, t1, richtig_falsch(4, 0, start=10 * i))
        s.erwartung, s.versuche, s.richtig = "weniges", 4, 4
        s.selbsteinschaetzung = "zu_leicht"
        s.ende = s.beginn + timedelta(minutes=5)
        s.save()
    Pruefung.objects.create(
        kind=kind_a,
        fach=t1.fach,
        titel="Test Eins",
        termin=MITTWOCH + timedelta(days=3),
        status="aktiv",
        plan_ok=False,
    )
    b = woche_selectors.wochenbild(kind_a, MITTWOCH)
    assert b.einschaetzung == {"mehr": 2}
    assert [(m.fach, m.art, m.anzahl) for m in b.meldungen] == [("Fach X", "zu_leicht", 2)]
    assert [(p.titel, p.tage_bis, p.plan_ok) for p in b.pruefungen] == [("Test Eins", 3, False)]
    schluessel = {v.schluessel for v in b.vorschlaege}
    assert {"traut_sich_zu_wenig", "meldung_zu_leicht", "pruefung_ohne_plan"} <= schluessel


def test_wochenbild_tutor_hohe_stufe(kind_a):
    beginn = zeit.tag_beginn(MONTAG) + timedelta(hours=16)
    for _ in range(2):
        TutorGespraech.objects.create(
            kind=kind_a, beginn=beginn, letzte_aktivitaet=beginn, hilfestufe=5
        )
    TutorGespraech.objects.create(
        kind=kind_a, beginn=beginn, letzte_aktivitaet=beginn, hilfestufe=1
    )
    b = woche_selectors.wochenbild(kind_a, MITTWOCH)
    assert b.tutor_hoch == 2
    assert "tutor_hohe_stufe" in {v.schluessel for v in b.vorschlaege}


# --- Vorschlags-Regeln (rein, mit gebautem Wochenbild) ---------------------------------------


def bild(kind, **felder):
    return Wochenbild(kind=kind, montag=MONTAG, **felder)


def keys(b, heute=MITTWOCH):
    return [v.schluessel for v in woche_selectors.vorschlaege(b, heute)]


def test_regel_wochenziel_geschafft(kind_a):
    assert keys(bild(kind_a, tage_geuebt=3, soll_tage=3)) == ["wochenziel_geschafft"]


def test_regel_kein_uebungstag_erst_ab_donnerstag(kind_a):
    b = bild(kind_a, soll_tage=3)
    assert keys(b, MONTAG + timedelta(days=2)) == []
    assert keys(b, MONTAG + timedelta(days=3)) == ["kein_uebungstag"]


def test_regel_weniger_tage_erst_nach_der_woche(kind_a):
    b = bild(kind_a, tage_geuebt=1, soll_tage=3)
    assert keys(b, MITTWOCH) == []
    nach = MONTAG + timedelta(days=8)
    v = woche_selectors.vorschlaege(b, nach)
    assert [(x.schluessel, x.parameter) for x in v] == [("weniger_tage", {"tage": 1, "soll": 3})]


def test_regel_geschonte_woche_verlangt_nichts(kind_a):
    assert keys(bild(kind_a, soll_tage=0), MONTAG + timedelta(days=8)) == []


def test_regel_viel_hilfe_und_weniger_hilfe(kind_a):
    assert keys(bild(kind_a, hilfe_prozent=60)) == ["viel_hilfe"]
    assert keys(bild(kind_a, hilfe_prozent=10, hilfe_tendenz="sinkt")) == ["weniger_hilfe"]
    assert keys(bild(kind_a, hilfe_prozent=10, hilfe_tendenz="steigt")) == []


def test_regel_schwaeche_nennt_thema_und_minuten(kind_a):
    from apps.lernen.woche_selectors import Schwaeche

    b = bild(kind_a, schwaechen=[Schwaeche("Mathe", "Bruchrechnen", 5, 8)] * 3)
    v = woche_selectors.vorschlaege(b, MITTWOCH)
    assert len(v) == 2  # höchstens zwei Schwächen
    assert v[0].parameter == {"fach": "Mathe", "thema": "Bruchrechnen", "minuten": 10}
    assert v[0].text == "Im Fach Mathe fiel Bruchrechnen schwer. Plane 10 Minuten Bruchrechnen ein."


def test_regel_selbsteinschaetzung(kind_a):
    assert keys(bild(kind_a, einschaetzung={"weniger": 2})) == ["zu_optimistisch"]
    assert keys(bild(kind_a, einschaetzung={"mehr": 3})) == ["traut_sich_zu_wenig"]
    assert keys(bild(kind_a, einschaetzung={"mehr": 1, "weniger": 1})) == []


def test_regel_meldungen_brauchen_ein_fach(kind_a):
    from apps.lernen.woche_selectors import Meldung

    b = bild(kind_a, meldungen=[Meldung("Mathe", "zu_schwer", 2), Meldung("", "zu_leicht", 1)])
    assert keys(b) == ["meldung_zu_schwer"]


def test_regel_pruefung_knapp(kind_a):
    from apps.lernen.woche_selectors import PruefungHinweis

    bald = date(2026, 11, 6)
    b = bild(
        kind_a,
        pruefungen=[
            PruefungHinweis("Eins", "Mathe", bald, 3, True, 20),
            PruefungHinweis("Zwei", "Mathe", bald, 3, True, 90),
            PruefungHinweis("Drei", "Mathe", bald + timedelta(days=9), 12, True, 0),
        ],
    )
    v = woche_selectors.vorschlaege(b, MITTWOCH)
    assert [(x.schluessel, x.parameter["titel"]) for x in v] == [("pruefung_knapp", "Eins")]


def test_vorschlaege_sind_begrenzt_und_ohne_bewertung(kind_a):
    from apps.lernen.woche_selectors import Schwaeche

    b = bild(
        kind_a,
        tage_geuebt=3,
        soll_tage=3,
        hilfe_prozent=90,
        tutor_hoch=3,
        einschaetzung={"weniger": 5, "mehr": 5},
        schwaechen=[Schwaeche("A", "B", 9, 10), Schwaeche("C", "D", 9, 10)],
    )
    assert len(woche_selectors.vorschlaege(b, MITTWOCH)) <= woche_selectors.VORSCHLAEGE_MAX
    for schluessel in woche_texte.vorschlag_schluessel():
        text = woche_texte._VORSCHLAEGE[schluessel].lower()
        assert "note" not in text and "schlecht" not in text and "versag" not in text


def test_vorschlag_text_ohne_parameter(db):
    v = woche_texte.Vorschlag("viel_hilfe")
    assert v.text == woche_texte._VORSCHLAEGE["viel_hilfe"] == v.msgid


def test_alle_vorschlagstexte_sind_ins_englische_uebersetzt(db):
    from django.utils import translation

    with translation.override("en"):
        for schluessel in woche_texte.vorschlag_schluessel():
            msgid = woche_texte._VORSCHLAEGE[schluessel]
            assert woche_texte.Vorschlag(schluessel).msgid == msgid
            from django.utils.translation import gettext

            assert gettext(msgid) != msgid
        for schluessel in woche_texte.titel_schluessel():
            assert woche_texte.titel_name(schluessel) != woche_texte._TITEL[schluessel][0] or (
                schluessel in {"aufsteiger"}
            )


# --- Ansichten und Rollenschutz -------------------------------------------------------------


def test_eltern_wochenbild_seite(eltern_client, kind_a, kind_b, themen):
    t1, _t2 = themen
    heute = zeit.heute()
    tag(kind_a, heute)
    antworten(kind_a, heute, t1, richtig_falsch(1, 6))
    html = eltern_client.get(reverse("lernen:eltern_woche")).content.decode()
    assert "Testkind A" in html and "Testkind B" in html
    assert "data-woche-vorschlaege" in html
    assert "Thema Eins" in html
    voraus = eltern_client.get(reverse("lernen:eltern_woche") + "?woche=vor")
    assert voraus.status_code == 200 and "Diese Woche" in voraus.content.decode()


def test_eltern_wochenbild_hat_keinen_vergleich(eltern_client, kind_a, kind_b):
    html = eltern_client.get(reverse("lernen:eltern_woche")).content.decode().lower()
    for wort in ("rang", "platz ", "besser als", "ranking"):
        assert wort not in html


def test_titel_schalter_der_eltern(eltern_client, kind_a):
    url = reverse("lernen:eltern_titel_schalter")
    assert eltern_client.post(url, {"an": "0"}).status_code == 302
    assert einstellungen.wert("lernen.titel_anzeigen") is False
    html = eltern_client.get(reverse("lernen:eltern_woche")).content.decode()
    assert 'data-titel-schalter="aus"' in html
    eltern_client.post(url, {"an": "1"})
    assert einstellungen.wert("lernen.titel_anzeigen") is True


def test_eltern_seite_verlinkt_das_wochenbild(eltern_client, kind_a):
    html = eltern_client.get(reverse("lernen:eltern")).content.decode()
    assert reverse("lernen:eltern_woche") in html


@pytest.mark.parametrize("name", ["eltern_woche", "eltern_titel_schalter"])
def test_kind_darf_die_eltern_seiten_nicht_oeffnen(kind_client, name):
    url = reverse(f"lernen:{name}")
    assert kind_client.get(url).status_code in (403, 405)
    assert kind_client.post(url, {"an": "0"}).status_code == 403
    assert einstellungen.wert("lernen.titel_anzeigen") is True


@pytest.mark.parametrize("name", ["eltern_woche", "eltern_titel_schalter"])
def test_ohne_anmeldung_keine_eltern_seite(client, name):
    antwort = client.post(reverse(f"lernen:{name}"), {"an": "0"})
    assert antwort.status_code in (302, 401, 403)
    assert einstellungen.wert("lernen.titel_anzeigen") is True


def test_startwerte_sind_gesetzt(db):
    assert einstellungen.wert("lernen.titel_anzeigen") is True
    assert einstellungen.wert("lernen.familienziel_tage") == 4
    for schluessel in (
        "lernen.titel_min_versuche",
        "lernen.titel_min_fehler",
        "lernen.woche_tendenz_prozent",
        "lernen.woche_schwaeche_fehler",
        "lernen.woche_schwaeche_prozent",
        "lernen.woche_hilfe_hoch_prozent",
        "lernen.woche_pruefung_tage",
    ):
        assert einstellungen.wert(schluessel) > 0


def test_tagesziel_erreicht_loest_abzeichen_pruefung_aus(kind_a, monkeypatch):
    """Die neue Metrik wird geprüft, wenn das eigene Tagesziel erreicht wird."""
    from apps.lernen import services

    aufrufe = []
    monkeypatch.setattr(services.spielregeln, "abzeichen_pruefen", aufrufe.append)
    jetzt = datetime.combine(MITTWOCH, datetime.min.time()).astimezone() + timedelta(hours=12)
    einstellungen.setzen("lernen.tagesziel_minuten", 1, akteur=None)
    einstellungen.setzen("lernen.mindesttag_minuten", 1, akteur=None)
    sitzung = Lernsitzung.objects.create(kind=kind_a, beginn=jetzt - timedelta(seconds=100))
    sitzung.letzte_aktivitaet = jetzt - timedelta(seconds=100)
    sitzung.save()
    einstellungen.setzen("lernen.leerlauf_sekunden", 300, akteur=None)
    assert services._zeit_buchen(sitzung, jetzt) is True
    assert aufrufe == [kind_a]


def test_modul_titel_deckt_alle_einstellungsmodule_ab():
    """Sonst steht in der Einrichtung "Oberflaeche" (capitalize) und in EN nichts übersetzt."""
    from apps.einrichtung.uebersicht import MODUL_TITEL

    for modul in ("avatar", "ereignisse", "familienziel", "lernen", "oberflaeche", "sondertag"):
        assert modul in MODUL_TITEL
