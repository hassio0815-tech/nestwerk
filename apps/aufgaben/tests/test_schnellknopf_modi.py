"""Schnell-Knöpfe: drei Modi (einer für alle / jedes Kind / bestimmtes Kind) und Auswahlfenster."""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.aufgaben import events, schnellknopf, services, wiederholung
from apps.aufgaben.models import (
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    Interesse,
    SchnellknopfModus,
)
from apps.ereignisse.models import Ereignis
from apps.kern import zeit
from apps.kern.models import AuditEintrag
from apps.konten import services as konten

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def knopf(mama):
    def anlegen(titel="Zimmer aufräumen", **felder):
        werte = {
            "titel": titel,
            "punkte": 10,
            "erstellt_von": mama,
            "freigabeart": "eltern",
            "wiederholungsart": wiederholung.BEI_BEDARF,
            "emoji": "🧹",
            "schnellknopf_modus": SchnellknopfModus.JEDES,
        }
        werte.update(felder)
        return Aufgabe.objects.create(**werte)

    return anlegen


def instanzen_von(aufgabe):
    return AufgabenInstanz.objects.filter(aufgabe=aufgabe)


# --- Modus "jedes" ----------------------------------------------------------------------------


def test_jedes_legt_je_kind_eine_reservierte_instanz_an(knopf, anna, ben, mama):
    aufgabe = knopf()
    ergebnis = schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    assert ergebnis.neu and len(ergebnis.angelegt) == 2 and ergebnis.uebersprungen == []
    assert {i.kind for i in instanzen_von(aufgabe)} == {anna, ben}
    for instanz in instanzen_von(aufgabe):
        assert instanz.status == InstanzStatus.RESERVIERT and instanz.reserviert_bis is not None
        assert instanz.punkte_snapshot == 10
    assert Interesse.objects.filter(instanz__aufgabe=aufgabe, status="zugeteilt").count() == 2


def test_jedes_ueberspringt_kinder_mit_laufender_instanz(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    ergebnis = schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    assert [i.kind for i in ergebnis.angelegt] == [ben]
    assert [kind for kind, _grund in ergebnis.uebersprungen] == [anna]
    assert instanzen_von(aufgabe).count() == 2


def test_jedes_zweimal_ist_doppel_schutz(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    zweite = schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    assert not zweite.neu and zweite.angelegt == [] and len(zweite.uebersprungen) == 2
    assert instanzen_von(aufgabe).count() == 2


def test_jedes_nur_erlaubte_kinder(knopf, anna, ben, mama):
    aufgabe = knopf(zugewiesen_an=ben)
    ergebnis = schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    assert [i.kind for i in ergebnis.angelegt] == [ben]


def test_jedes_ueberspringt_kind_mit_erreichtem_limit(knopf, anna, ben, mama):
    aufgabe = knopf(limit_anzahl=1, limit_zeitraum="tag")
    schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    # Anna gibt ab und ist trotzdem wieder dran; Ben hat sein Limit (1 laufende) verbraucht
    AufgabenInstanz.objects.filter(aufgabe=aufgabe, kind=anna).update(
        status=InstanzStatus.BESTAETIGT, gemeldet_am=zeit.jetzt()
    )
    ergebnis = schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    assert ergebnis.angelegt == []
    assert {kind for kind, _ in ergebnis.uebersprungen} == {anna, ben}
    assert instanzen_von(aufgabe).count() == 2  # kein Rest: Savepoint hat die Instanz verworfen


def test_jedes_ohne_aktive_kinder_legt_nichts_an(knopf, mama):
    ergebnis = schnellknopf.druecken(knopf(), von=mama, modus="jedes")
    assert not ergebnis.neu and ergebnis.instanz is None and not AufgabenInstanz.objects.exists()


def test_jedes_nur_eltern(knopf, anna, mama):
    aufgabe = knopf()
    with pytest.raises(services.NichtErlaubt):
        schnellknopf.druecken(aufgabe, von=anna, modus="jedes")
    with pytest.raises(services.NichtErlaubt):
        schnellknopf.druecken(aufgabe, von=None, modus="jedes")  # Tablet
    assert not AufgabenInstanz.objects.exists()


def test_jedes_audit_mit_modus(knopf, anna, mama):
    schnellknopf.druecken(knopf(), von=mama, modus="jedes")
    eintrag = AuditEintrag.objects.filter(aktion="aufgabe.schnellknopf").get()
    assert eintrag.details["modus"] == "jedes"


def test_modus_in_audit_melden_und_ich_machs(knopf, anna, ben, mama):
    schnellknopf.druecken(knopf("A"), von=mama)
    schnellknopf.druecken(knopf("B"), von=mama, kind=anna)
    modi = {
        e.details["titel"]: e.details["modus"]
        for e in AuditEintrag.objects.filter(aktion="aufgabe.schnellknopf")
    }
    assert modi == {"A": "melden", "B": "ich_machs"}


def test_ein_kind_blockiert_in_jedes_nicht_die_anderen(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    ergebnis = schnellknopf.druecken(aufgabe, von=ben, kind=ben)
    assert ergebnis.neu and ergebnis.instanz.kind == ben
    assert instanzen_von(aufgabe).count() == 2


def test_ein_kind_kann_nicht_zweimal_in_jedes(knopf, anna, mama):
    aufgabe = knopf()
    erste = schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    zweite = schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    assert not zweite.neu and zweite.instanz.pk == erste.instanz.pk


def test_einer_blockiert_weiter_alle(knopf, anna, ben, mama):
    aufgabe = knopf(titel="Restmüll", schnellknopf_modus=SchnellknopfModus.EINER)
    erste = schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    zweite = schnellknopf.druecken(aufgabe, von=ben, kind=ben)
    assert not zweite.neu and zweite.instanz.pk == erste.instanz.pk


def test_melden_mit_laufender_kind_instanz_laeuft_schon(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    ergebnis = schnellknopf.druecken(aufgabe, von=mama)
    assert not ergebnis.neu and instanzen_von(aufgabe).count() == 1


def test_eltern_bestimmtes_kind_in_jedes(knopf, anna, ben, mama):
    aufgabe = knopf()
    ergebnis = schnellknopf.druecken(aufgabe, von=mama, kind=ben)
    assert ergebnis.neu and ergebnis.instanz.kind == ben
    assert [i.kind for i in instanzen_von(aufgabe)] == [ben]


def test_knoepfe_laeuft_pro_kind_bei_jedes(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    kachel_anna = schnellknopf.knoepfe(anna)[0]
    kachel_ben = schnellknopf.knoepfe(ben)[0]
    kachel_eltern = schnellknopf.knoepfe(mama)[0]
    assert kachel_anna.laeuft.kind == anna
    assert kachel_ben.laeuft is None  # Ben darf noch
    assert kachel_eltern.laeuft is None  # Eltern dürfen noch (für Ben)
    assert [i.kind for i in kachel_eltern.laufende] == [anna]
    assert kachel_eltern.laufend_anzahl == 1 and kachel_eltern.kinder_anzahl == 2
    schnellknopf.druecken(aufgabe, von=ben, kind=ben)
    assert schnellknopf.knoepfe(mama)[0].laeuft is not None  # alle Kinder dran


def test_knoepfe_einer_laeuft_fuer_alle(knopf, anna, ben, mama):
    aufgabe = knopf(titel="Restmüll", schnellknopf_modus=SchnellknopfModus.EINER)
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    assert schnellknopf.knoepfe(ben)[0].laeuft.kind == anna
    assert schnellknopf.knoepfe(mama)[0].laeuft.kind == anna


# --- Datenbank-Absicherung und Freigeben ------------------------------------------------------


def test_zurueckgeben_zweier_jedes_instanzen_kollidiert_nicht(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    erste = instanzen_von(aufgabe).get(kind=anna)
    zweite = instanzen_von(aufgabe).get(kind=ben)
    services.zurueckgeben(erste, anna)
    services.zurueckgeben(zweite, ben)  # sonst zweite ungebundene laufende Instanz (Unique)
    erste.refresh_from_db()
    zweite.refresh_from_db()
    assert erste.status == InstanzStatus.OFFEN and erste.kind is None
    assert zweite.status == InstanzStatus.NICHT_UEBERNOMMEN
    assert zweite.abgeschlossen_am is not None


def test_eltern_loesen_zweier_jedes_instanzen(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    for instanz in list(instanzen_von(aufgabe)):
        services.reservierung_loesen(instanz, von=mama)
    assert sorted(instanzen_von(aufgabe).values_list("status", flat=True)) == [
        InstanzStatus.NICHT_UEBERNOMMEN,
        InstanzStatus.OFFEN,
    ]


def test_ablauf_zweier_reservierungen_kollidiert_nicht(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    spaeter = zeit.jetzt() + timedelta(days=30)
    ergebnis = services.reservierungen_pruefen(jetzt=spaeter)
    assert ergebnis["abgelaufen"] == 2
    assert sorted(instanzen_von(aufgabe).values_list("status", flat=True)) == [
        InstanzStatus.NICHT_UEBERNOMMEN,
        InstanzStatus.OFFEN,
    ]


def test_anderes_kind_kann_jedes_instanz_nicht_mitbewerben(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    instanz = instanzen_von(aufgabe).get()
    with pytest.raises(services.AblaufFehler):
        services.interesse_zeigen(instanz, ben)
    from apps.aufgaben import selectors

    assert instanz.pk not in [i.pk for i in selectors.kind_offene(ben)]


# --- Sicherheit (Finding A-P3-10) -------------------------------------------------------------


def test_kind_kann_fremd_zugewiesenen_knopf_nicht_melden(knopf, anna, ben):
    aufgabe = knopf(zugewiesen_an=ben, schnellknopf_modus=SchnellknopfModus.EINER)
    with pytest.raises(services.NichtErlaubt):
        schnellknopf.druecken(aufgabe, von=anna)
    assert not AufgabenInstanz.objects.exists()
    # Eigener Knopf, und Tablet (von=None), dürfen melden
    schnellknopf.druecken(aufgabe, von=ben)


# --- Ansichten --------------------------------------------------------------------------------


def post(client, aufgabe, **daten):
    return client.post(
        reverse("aufgaben:schnellknopf_eltern", args=[aufgabe.pk]), daten, **HTMX
    ).content.decode()


def test_view_jedes_meldet_ergebnis(eltern_client, knopf, anna, ben):
    aufgabe = knopf()
    html = post(eltern_client, aufgabe, modus="jedes")
    assert "Anna" in html and "Ben" in html and "reserviert" in html
    assert instanzen_von(aufgabe).count() == 2
    html = post(eltern_client, aufgabe, modus="jedes")
    assert "läuft schon" in html and instanzen_von(aufgabe).count() == 2


def test_view_jedes_zeigt_uebersprungene(eltern_client, knopf, anna, ben):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    html = post(eltern_client, aufgabe, modus="jedes")
    assert "Übersprungen" in html


def test_view_bestimmtes_kind_und_einer(eltern_client, knopf, anna, ben):
    aufgabe = knopf()
    post(eltern_client, aufgabe, modus="ich_machs", kind_id=str(anna.pk))
    assert instanzen_von(aufgabe).get().kind == anna
    einer = knopf("Restmüll", schnellknopf_modus=SchnellknopfModus.EINER)
    post(eltern_client, einer, modus="melden")
    assert instanzen_von(einer).get().kind is None
    assert Ereignis.objects.filter(typ_id=events.SCHNELLKNOPF).count() == 2


def test_view_bestimmtes_kind_ohne_kind_ist_hinweis(eltern_client, knopf, anna):
    aufgabe = knopf()
    html = post(eltern_client, aufgabe, modus="ich_machs")
    assert "Kind" in html and not instanzen_von(aufgabe).exists()


@pytest.mark.parametrize("kind_id", ["abc", "999999", "00000000-0000-0000-0000-000000000000"])
def test_view_ungueltige_kind_id_ist_hinweis_statt_500(eltern_client, knopf, anna, kind_id):
    """Finding A-04: nicht numerisch / unbekannt -> Fehlerhinweis, kein 500."""
    aufgabe = knopf()
    antwort = eltern_client.post(
        reverse("aufgaben:schnellknopf_eltern", args=[aufgabe.pk]), {"kind_id": kind_id}, **HTMX
    )
    assert antwort.status_code == 200 and "gibt es nicht" in antwort.content.decode()
    assert not instanzen_von(aufgabe).exists()


def test_tablet_ungueltige_kind_id_ist_hinweis_statt_500(client, knopf, anna, mama):
    from apps.konten.models import GeraeteTyp
    from apps.konten.tests.conftest import client_fuer

    tablet = konten.geraet_registrieren("Flur-Tablet", GeraeteTyp.KIOSK, registriert_von=mama)
    aufgabe = knopf()
    antwort = client_fuer(tablet).post(
        reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk]),
        {"kind_id": "abc"},
        **HTMX,
    )
    assert antwort.status_code == 200 and "gibt es nicht" in antwort.content.decode()
    assert not instanzen_von(aufgabe).exists()


def test_tablet_darf_nicht_jedes(client, knopf, anna, mama):
    from apps.konten.models import GeraeteTyp
    from apps.konten.tests.conftest import client_fuer

    tablet = konten.geraet_registrieren("Flur-Tablet", GeraeteTyp.KIOSK, registriert_von=mama)
    aufgabe = knopf()
    antwort = client_fuer(tablet).post(
        reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk]),
        {"modus": "jedes"},
        **HTMX,
    )
    assert "nur Eltern" in antwort.content.decode() and not instanzen_von(aufgabe).exists()


def test_kind_kachel_jedes_kind_nur_fuer_sich(kind_client, knopf, anna, ben):
    aufgabe = knopf()
    antwort = kind_client.post(
        reverse("aufgaben:schnellknopf_kind", args=[aufgabe.pk]), {"modus": "jedes"}, **HTMX
    )
    assert antwort.status_code == 200 and "nur Eltern" in antwort.content.decode()
    assert not instanzen_von(aufgabe).exists()
    kind_client.post(
        reverse("aufgaben:schnellknopf_kind", args=[aufgabe.pk]), {"modus": "ich"}, **HTMX
    )
    assert [i.kind for i in instanzen_von(aufgabe)] == [anna]


def test_kind_kachel_fremd_zugewiesen_melden_abgewiesen(kind_client, knopf, anna, ben):
    aufgabe = knopf(zugewiesen_an=ben, schnellknopf_modus=SchnellknopfModus.EINER)
    antwort = kind_client.post(
        reverse("aufgaben:schnellknopf_kind", args=[aufgabe.pk]), {"modus": "melden"}, **HTMX
    )
    assert "anderes Kind" in antwort.content.decode() or "nur für dich" in antwort.content.decode()
    assert not instanzen_von(aufgabe).exists()


def test_eltern_kachel_hat_auswahlfenster_mit_drei_modi(eltern_client, knopf, anna, ben):
    knopf()
    html = eltern_client.get(reverse("aufgaben:schnellknoepfe")).content.decode()
    assert "<dialog" in html and 'value="melden"' in html and 'value="jedes"' in html
    assert 'value="ich_machs"' in html and "Los" in html
    assert 'value="jedes" checked' in html  # Standard-Modus des Knopfs vorbelegt
    assert f'value="{anna.pk}"' in html and f'value="{ben.pk}"' in html


def test_auswahlfenster_einer_vorbelegt(eltern_client, knopf, anna):
    knopf(titel="Restmüll", schnellknopf_modus=SchnellknopfModus.EINER)
    html = eltern_client.get(reverse("aufgaben:schnellknoepfe")).content.decode()
    assert 'value="melden" checked' in html and 'value="jedes" checked' not in html


def test_eltern_kachel_zeigt_wie_viele_laufen(eltern_client, knopf, anna, ben):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    html = eltern_client.get(reverse("aufgaben:schnellknoepfe")).content.decode()
    assert "1 von 2" in html


def test_pause_und_beenden_entfernt_jedes_instanzen_nur_offene(knopf, anna, ben, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=mama, modus="jedes")
    services.aufgabe_status_setzen(aufgabe, "pausiert", von=mama)
    assert instanzen_von(aufgabe).count() == 2  # reservierte bleiben (Begonnenes)
