"""AP27: God-Mode-Zyklen, Mod-Sets (6 Mods je Zyklus) und die zugehörigen Metriken."""

import itertools
from datetime import UTC, date, datetime, timedelta

import pytest

from apps.avatar import godmode, mods, services
from apps.avatar.models import ModBesitz, ModDefinition, ModSet
from apps.avatar.registry import SELTENHEITEN  # noqa: F401  (Registry geladen)
from apps.kern import einstellungen
from apps.kern import registry as kern_registry
from apps.punkte import services as punkte_services
from apps.punkte.models import Art
from apps.spielregeln import services as spielregeln
from apps.spielregeln.models import Rang, RangAufstieg

pytestmark = pytest.mark.django_db

_zaehler = itertools.count()
MONTAG = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)  # ISO-Woche 2026-W44


def gutschrift(kind, n):
    return punkte_services.buchen(
        kind, Art.AUFGABE, n, schluessel=f"gm:{next(_zaehler)}", quelle_modul="aufgaben", von=None
    )


def godmode_geben(kind, am=MONTAG):
    for rang in Rang.objects.filter(stufe__gt=1):
        RangAufstieg.objects.get_or_create(
            kind=kind,
            rang=rang,
            defaults={
                "erreicht_am": am,
                "xp_bei_aufstieg": 0,
                "aktive_wochen_bei_aufstieg": 0,
                "schwelle_bei_aufstieg": 0,
            },
        )


def aktiv_in_wochen(kind, anzahl, ab=date(2026, 11, 2)):
    """Je eine Aktivität in ``anzahl`` aufeinanderfolgenden Wochen ab ``ab`` (Montag)."""
    from django.db import transaction

    for i in range(anzahl):
        with transaction.atomic():
            spielregeln.aktivitaet_erfassen(
                kind, ab + timedelta(weeks=i), modul="t", referenz=f"gm{next(_zaehler)}"
            )


@pytest.fixture
def kind(anna, uhr):
    uhr.jetzt = MONTAG
    einstellungen.setzen("avatar.godmode_zyklus_aktivwochen", 4, akteur=None)
    einstellungen.setzen("allgemein.go_live_datum", date(2026, 10, 19), akteur=None)
    services.avatar_waehlen(anna, "ritter", {})
    gutschrift(anna, 10000)
    return anna


def test_set_aus_seltenheit_6_mit_varianten(kind):
    thema = ModDefinition.objects.get(schluessel="ritter-kopf-6").thema
    s1 = godmode.set_sicherstellen(thema, 1)
    assert godmode.set_sicherstellen(thema, 1) == s1  # idempotent
    mods_ = list(s1.mods.select_related("slot"))
    assert len(mods_) == 6
    assert {m.slot.schluessel for m in mods_} == {
        "kopf",
        "koerper",
        "ruecken",
        "hand",
        "begleiter",
        "hintergrund",
    }
    assert all(m.seltenheit == 6 and m.preis is None for m in mods_)  # God-Mode-Preis (250)
    basis = ModDefinition.objects.get(schluessel="ritter-kopf-6")
    variante = s1.mods.get(slot__schluessel="kopf")
    assert variante.schluessel == "ritter-kopf-6-set1"
    assert variante.bauplan != basis.bauplan
    assert variante.name.endswith("· Set 1")
    from apps.avatar.generator import bauplaene

    plan = {
        "schluessel": variante.schluessel,
        "name": variante.name,
        "thema": "ritter",
        "slot": "kopf",
        "seltenheit": 6,
        "teile": variante.bauplan["teile"],
    }
    assert bauplaene.bauplan_pruefen(plan) == []
    s2 = godmode.set_sicherstellen(thema, 2)
    assert s2.mods.get(slot__schluessel="kopf").bauplan != variante.bauplan
    assert ModSet.objects.filter(thema=thema).count() == 2


def test_zyklus_zaehlt_aktive_wochen_nach_aufstieg(kind, uhr):
    assert godmode.zyklus(kind).godmode is False
    godmode_geben(kind)
    aktiv_in_wochen(kind, 1, ab=date(2026, 10, 26))  # Aufstiegswoche zählt nicht
    aktiv_in_wochen(kind, 6)
    uhr.jetzt = datetime(2026, 12, 20, 10, 0, tzinfo=UTC)
    z = godmode.zyklus(kind)
    assert (z.aktivwochen, z.laenge, z.aktuell, z.geschafft) == (6, 4, 2, 1)
    assert z.freigeschaltet(2) and not z.freigeschaltet(3)
    assert godmode.metrik_zyklus_bereiche(kind) == {
        "zyklus-1": (1, "Zyklus 1"),
        "zyklus-2": (0, "Zyklus 2"),
    }


def test_shop_zeigt_freigeschaltete_sets_und_kauf_zaehlt_getrennt(kind, uhr):
    assert all(g.set_nummer is None for g in mods.shop(kind))
    godmode_geben(kind)
    gruppen = mods.shop(kind)
    sets = [g for g in gruppen if g.set_nummer]
    assert [g.set_nummer for g in sets] == [1]
    assert [k.konditionen.preis for k in sets[0].karten] == [250] * 6
    # God-Mode-Gruppe der Seltenheit 6 enthält keine Set-Mods (keine doppelten Slots)
    sechs = next(g for g in gruppen if g.stufe == 6 and g.set_nummer is None)
    assert len(sechs.karten) == 6
    set_mod = sets[0].karten[0].mod
    besitz = mods.kaufen(kind, set_mod)
    mods._fertig_setzen(besitz.pk, MONTAG)
    stufe = mods.ausbaustufe(kind)
    assert stufe.je_set == {1: 1}
    assert stufe.je_seltenheit[6] == 0
    assert godmode.metrik_set_bereiche(kind) == {"zyklus-1": (1, "Set 1")}


def test_set_kauf_erst_nach_freischaltung(kind, uhr):
    godmode_geben(kind)
    thema = ModDefinition.objects.get(schluessel="ritter-kopf-6").thema
    s2 = godmode.set_sicherstellen(thema, 2)
    with pytest.raises(mods.ModFehler, match="noch nicht freigeschaltet"):
        mods.kaufen(kind, s2.mods.first())


def test_metriken_registriert_und_set_vollstaendig(kind, uhr):
    for name in ("godmode_aktivwochen", "godmode_zyklus", "godmode_set_vollstaendig"):
        assert kern_registry.metrik(name).modul == "avatar"
    assert kern_registry.provider_vorhanden("metrik.godmode_set_vollstaendig.bereiche")
    godmode_geben(kind)
    s1 = godmode.set_sicherstellen(ModDefinition.objects.get(schluessel="ritter-kopf-6").thema, 1)
    for i, m in enumerate(s1.mods.all()):
        b = ModBesitz.objects.create(
            kind=kind,
            mod=m,
            preis_bezahlt=0,
            bauzeit_stunden=0,
            buchung=gutschrift(kind, 1),
            gekauft_am=MONTAG,
            fertig_geplant_am=MONTAG,
            fertig_am=MONTAG,
            status="fertig",
            zaehlt_ab_iso_jahr=2026,
            zaehlt_ab_iso_woche=38 + i,
        )
        assert b.pk
    assert godmode.metrik_set_vollstaendig(kind) == 1
    assert godmode.metrik_set_bereiche(kind) == {"zyklus-1": (6, "Set 1")}
