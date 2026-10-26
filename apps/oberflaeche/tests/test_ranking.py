"""Familien-Ranking (AP30): Modi, Umschalter, Tablet, Kinder-Seite, Rechte."""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.oberflaeche import ranking
from apps.spielregeln.models import Wochenauswertung

from .conftest import gutschrift


def modus_setzen(wert):
    einstellungen.setzen("oberflaeche.ranking_modus", wert, akteur=None)


def held_anlegen(kind, uhr):
    w = IsoWoche.von(zeit.jetzt()).vorherige()
    Wochenauswertung.objects.create(
        kind=kind,
        iso_jahr=w.jahr,
        iso_woche=w.woche,
        montag=w.montag,
        aktiv=True,
        neutral=False,
        pausentage=0,
        xp_woche=180,
        wochenserie_danach=2,
        aktive_wochen_gesamt=2,
        zuwachs_relativ="0.800",
        held_der_woche=True,
        finalisiert_am=zeit.jetzt() - timedelta(days=1),
    )


def tablet(client):
    return client.get(reverse("oberflaeche:tablet_teil")).content.decode()


def test_standard_ist_schaufenster(client, anna, ben):
    html = tablet(client)
    assert 'data-ranking-modus="schaufenster"' in html
    assert "Anna" in html and "Ben" in html and "Common" in html
    assert "letzter Platz" not in html.lower()


def test_ohne_kinder_leerzustand(client, db):
    assert "Noch kein Ranking" in tablet(client)


def test_schaufenster_zeigt_avatare_serie_und_rohpunkte_nachrangig(client, anna, ben, mama):
    gutschrift(anna, 40, mama)
    html = tablet(client)
    assert html.count('<li class="rk-karte') == 2
    assert 'class="avatar-bild avatar-bild--riesig"' in html
    assert "Serie" in html and "40 Punkte diese Woche" in html


def test_modus_schalter_wirkt_auf_tablet(eltern_client, client, anna, ben, mama, uhr):
    held_anlegen(ben, uhr)
    antwort = eltern_client.post(reverse("oberflaeche:ranking_modus"), {"modus": "held"})
    assert antwort.status_code == 302
    assert einstellungen.wert("oberflaeche.ranking_modus") == "held"
    from django.test import Client

    html = tablet(Client())
    assert 'data-ranking-modus="held"' in html and "Held der letzten Woche" in html
    assert "Ben" in html and "data-held" in html
    eltern_client.post(reverse("oberflaeche:ranking_modus"), {"modus": "rohpunkte"})
    html = tablet(Client())
    assert 'data-ranking-modus="rohpunkte"' in html and "<table" in html


def test_held_modus_ohne_held_ist_freundlich(client, anna):
    modus_setzen("held")
    html = tablet(client)
    assert "Noch kein Held" in html and "letzter" not in html.lower().replace("letzten", "")


def test_rohpunkte_tabelle_sortiert_nach_woche(client, anna, ben, mama):
    modus_setzen("rohpunkte")
    gutschrift(ben, 70, mama)
    gutschrift(anna, 20, mama)
    html = tablet(client)
    html = html[html.index("data-ranking-modus") :]
    assert html.index("Ben") < html.index("Anna")
    assert "70 XP" in html and "Gesamt" in html


def test_ungueltiger_modus_wird_ignoriert(eltern_client, anna):
    eltern_client.post(reverse("oberflaeche:ranking_modus"), {"modus": "quatsch"})
    assert einstellungen.wert("oberflaeche.ranking_modus") == "schaufenster"
    assert ranking.modus() == "schaufenster"


def test_kind_darf_modus_nicht_umschalten(kind_client, anna):
    antwort = kind_client.post(reverse("oberflaeche:ranking_modus"), {"modus": "held"})
    assert antwort.status_code in (302, 403)
    assert einstellungen.wert("oberflaeche.ranking_modus") == "schaufenster"


def test_anonym_darf_modus_nicht_umschalten(client, anna):
    client.post(reverse("oberflaeche:ranking_modus"), {"modus": "held"})
    assert einstellungen.wert("oberflaeche.ranking_modus") == "schaufenster"


def test_kind_sieht_familie_aber_keine_eltern_daten(kind_client, anna, ben, uhr):
    held_anlegen(ben, uhr)
    html = kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    assert "<h2>Familie</h2>" in html and "Ben" in html
    assert "Zuwachs gegenüber" not in html and "data-eltern-ranking" not in html
    assert reverse("oberflaeche:ranking_modus") not in html
    assert "+80 %" not in html


def test_eltern_sehen_umschalter_und_zuwaechse(eltern_client, anna, ben, uhr):
    held_anlegen(ben, uhr)
    html = eltern_client.get(reverse("oberflaeche:eltern_dungeon")).content.decode()
    assert "data-eltern-ranking" in html and "data-zuwaechse" in html
    assert "+80 %" in html and reverse("oberflaeche:ranking_modus") in html


def test_eltern_sind_nicht_im_ranking(client, anna, mama):
    assert "Mama" not in tablet(client)


@pytest.mark.parametrize("modus", ranking.RANKING_MODI)
def test_alle_modi_rendern_auf_kind_seite(kind_client, anna, ben, modus):
    modus_setzen(modus)
    assert kind_client.get(reverse("oberflaeche:kind_heim")).status_code == 200
