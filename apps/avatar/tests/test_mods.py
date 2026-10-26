"""AP26: Mod-Kauf, Bauzeit, Fertigstellung, Ausbaustufe (K4, Zeitbremse), Themenwechsel."""

import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.avatar import mods, selectors, services
from apps.avatar.models import Avatar, BesitzStatus, ModBesitz, ModDefinition
from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen, registry
from apps.kern.models import AuditEintrag
from apps.punkte import selectors as punkte
from apps.punkte import services as punkte_services
from apps.punkte.models import Art, Buchung
from apps.spielregeln.models import Kalibrierung, Rang, RangAufstieg

pytestmark = pytest.mark.django_db

_zaehler = itertools.count()
# Montag 26.10.2026 10:00 Berlin (ISO-Woche 2026-W44)
MONTAG = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def gutschrift(kind, n):
    return punkte_services.buchen(
        kind, Art.AUFGABE, n, schluessel=f"test:{next(_zaehler)}", quelle_modul="aufgaben", von=None
    )


def rang_geben(kind, stufe):
    for rang in Rang.objects.filter(stufe__gt=1, stufe__lte=stufe):
        RangAufstieg.objects.get_or_create(
            kind=kind,
            rang=rang,
            defaults={
                "xp_bei_aufstieg": 0,
                "aktive_wochen_bei_aufstieg": 0,
                "schwelle_bei_aufstieg": 0,
            },
        )


def mod(thema, slot, seltenheit):
    return ModDefinition.objects.get(
        thema__schluessel=thema, slot__schluessel=slot, seltenheit=seltenheit
    )


SLOTS = ("kopf", "koerper", "ruecken", "hand", "begleiter", "hintergrund")


@pytest.fixture
def kind(anna, uhr):
    uhr.jetzt = MONTAG
    services.avatar_waehlen(anna, "ritter", {})
    gutschrift(anna, 5000)
    return anna


# --- Preise ---------------------------------------------------------------------------------


def test_preis_und_bauzeit_aus_rang_standard_mal_faktor(kind):
    m = mod("ritter", "kopf", 1)
    m.preis = m.bauzeit_stunden = None
    m.save()
    k = mods.konditionen(m, kind)
    assert (k.preis, k.bauzeit_stunden) == (40, 48)
    Kalibrierung.objects.filter(kind__isnull=True).update(
        faktor_preis=Decimal("1.13"), faktor_bauzeit=Decimal("0.5")
    )
    k = mods.konditionen(m, kind)
    assert (k.preis, k.bauzeit_stunden) == (45, 24)  # 45,2 -> 45
    m.preis, m.bauzeit_stunden = 100, 10
    m.save()
    assert mods.konditionen(m, kind).preis == 113


# --- Kauf -----------------------------------------------------------------------------------


def test_kauf_bucht_genau_einmal_und_startet_bau(kind, uhr):
    m = mod("ritter", "kopf", 1)
    vorher = punkte.guthaben(kind)
    besitz = services.mod_kaufen(kind, m)
    k = mods.konditionen(m, kind)
    assert besitz.status == BesitzStatus.IM_BAU
    assert besitz.preis_bezahlt == k.preis
    assert besitz.fertig_geplant_am == MONTAG + timedelta(hours=k.bauzeit_stunden)
    assert punkte.guthaben(kind) == vorher - k.preis
    assert punkte.xp(kind) == 5000  # Ausgaben senken XP nie
    assert besitz.buchung.art == Art.MODKAUF
    with pytest.raises(services.ModFehler, match="schon"):
        services.mod_kaufen(kind, m)
    assert Buchung.objects.filter(art=Art.MODKAUF).count() == 1
    assert Ereignis.objects.filter(typ_id="mod.gekauft").count() == 1
    assert AuditEintrag.objects.filter(aktion="avatar.mod_gekauft").count() == 1


def test_kein_ueberziehen_und_reservierungen_zaehlen(anna, uhr):
    uhr.jetzt = MONTAG
    services.avatar_waehlen(anna, "ritter", {})
    gutschrift(anna, 30)
    with pytest.raises(services.ModFehler, match="fehlen dir noch"):
        services.mod_kaufen(anna, mod("ritter", "kopf", 1))
    assert not ModBesitz.objects.exists()
    assert punkte.guthaben(anna) == 30


def test_offene_einloesung_reserviert_guthaben(anna, uhr, monkeypatch):
    uhr.jetzt = MONTAG
    services.avatar_waehlen(anna, "ritter", {})
    gutschrift(anna, 50)
    monkeypatch.setattr(punkte, "reserviert", lambda kind: 20)  # z. B. offener Einlöse-Antrag
    with pytest.raises(services.ModFehler, match="fehlen dir noch 10"):
        services.mod_kaufen(anna, mod("ritter", "kopf", 1))  # 40 > 50 - 20
    assert not Buchung.objects.filter(art=Art.MODKAUF).exists()


def test_rang_sperre(kind):
    with pytest.raises(services.ModFehler, match="ab Rang Uncommon"):
        services.mod_kaufen(kind, mod("ritter", "kopf", 2))
    rang_geben(kind, 2)
    assert services.mod_kaufen(kind, mod("ritter", "kopf", 2)).status == BesitzStatus.IM_BAU


def test_shop_zeigt_gesperrte_mit_rang_und_zustaende(kind):
    services.mod_kaufen(kind, mod("ritter", "kopf", 1))
    gruppen = selectors.shop(kind)
    assert [g.stufe for g in gruppen] == [1, 2, 3, 4, 5, 6]
    assert [g.gesperrt for g in gruppen] == [False, True, True, True, True, True]
    zustaende = {k.mod.slot.schluessel: k.zustand for k in gruppen[0].karten}
    assert zustaende["kopf"] == "im_bau"
    assert zustaende["koerper"] == "kaufbar"
    assert {k.zustand for k in gruppen[3].karten} == {"gesperrt"}


def test_fremdes_thema_nicht_kaufbar(kind):
    with pytest.raises(services.ModFehler, match="anderen Thema"):
        services.mod_kaufen(kind, mod("pirat", "kopf", 1))


# --- Fertigstellung -------------------------------------------------------------------------


def test_fertigstellung_idempotent_mit_catchup(kind, uhr):
    m = mod("ritter", "kopf", 1)
    besitz = services.mod_kaufen(kind, m)
    assert services.mods_fertigstellen()["fertig"] == 0
    uhr.weiter(days=30)  # Job lange ausgefallen
    assert services.mods_fertigstellen()["fertig"] == 1
    assert services.mods_fertigstellen()["fertig"] == 0
    besitz.refresh_from_db()
    assert besitz.status == BesitzStatus.FERTIG
    assert besitz.fertig_am == besitz.fertig_geplant_am  # Soll-Zeitpunkt, nicht Job-Zeitpunkt
    assert (besitz.zaehlt_ab_iso_jahr, besitz.zaehlt_ab_iso_woche) == (2026, 44)
    assert Ereignis.objects.filter(typ_id="mod.fertig").count() == 1
    # leerer Slot -> gleich angelegt
    assert Avatar.objects.get(pk=kind.pk).angelegt == {"kopf": m.schluessel}


def test_job_command_und_crontab(kind, uhr):
    services.mod_kaufen(kind, mod("ritter", "kopf", 1))
    uhr.weiter(days=3)
    call_command("mods_fertigstellen")
    assert ModBesitz.objects.get().status == BesitzStatus.FERTIG


def test_eltern_sofort_fertigstellen_mit_audit(kind, mama):
    besitz = services.mod_kaufen(kind, mod("ritter", "kopf", 1))
    with pytest.raises(services.ModFehler):
        services.bau_sofort_fertigstellen(besitz, von=kind)
    services.bau_sofort_fertigstellen(besitz, von=mama)
    besitz.refresh_from_db()
    assert besitz.status == BesitzStatus.FERTIG
    assert AuditEintrag.objects.filter(aktion="avatar.bau_sofort_fertig").count() == 1
    with pytest.raises(services.ModFehler, match="schon fertig"):
        services.bau_sofort_fertigstellen(besitz, von=mama)


# --- Ausbaustufe ----------------------------------------------------------------------------


def _alle_fertig(kind, uhr, seltenheit, slots=SLOTS, mama=None):
    for slot in slots:
        services.mod_kaufen(kind, mod("ritter", slot, seltenheit))
    uhr.weiter(days=8)
    services.mods_fertigstellen()


def test_zeitbremse_ein_zaehlender_mod_pro_woche(kind, uhr):
    _alle_fertig(kind, uhr, 1, SLOTS[:3])  # alle drei in derselben Woche fertig (W44)
    wochen = sorted((b.zaehlt_ab_iso_jahr, b.zaehlt_ab_iso_woche) for b in ModBesitz.objects.all())
    assert wochen == [(2026, 44), (2026, 45), (2026, 46)]
    # Jetzt Mo W45 + 1 Tag: zwei zählen, einer wartet (Warteschlange, nicht "nie")
    stufe = selectors.ausbaustufe(kind)
    assert stufe.aktuell == 2
    assert len(stufe.wartend) == 1
    uhr.weiter(days=7)
    assert selectors.ausbaustufe(kind).aktuell == 3


def test_zeitbremse_einstellbar(kind, uhr):
    einstellungen.setzen("avatar.max_zaehlende_mods_woche", 3, akteur=None)
    _alle_fertig(kind, uhr, 1, SLOTS[:3])
    assert {b.zaehlt_ab_iso_woche for b in ModBesitz.objects.all()} == {44}


def test_k4_ausbaustufe_je_seltenheit_auch_nach_rangaufstieg(kind, uhr):
    einstellungen.setzen("avatar.max_zaehlende_mods_woche", 6, akteur=None)
    _alle_fertig(kind, uhr, 1, SLOTS[:4])
    rang_geben(kind, 2)  # Rang 2 erreicht, bevor Common voll ist
    stufe = selectors.ausbaustufe(kind)
    assert stufe.rang_stufe == 2
    assert stufe.aktuell == 0
    assert stufe.je_seltenheit[1] == 4  # Besitz zählt weiter (K4)
    _alle_fertig(kind, uhr, 1, SLOTS[4:])
    assert selectors.ausbaustufe(kind).je_seltenheit[1] == 6
    assert registry.fortschritt("metrik.ausbaustufe_seltenheit_1", kind) == 6
    assert registry.fortschritt("metrik.ausbaustufe", kind) == 0
    bereiche = registry.fortschritt("metrik.ausbaustufe.bereiche", kind)
    assert bereiche["seltenheit-1"] == (6, "Common")
    assert bereiche["seltenheit-2"] == (0, "Uncommon")


def test_angelegt_ist_egal_besitz_zaehlt(kind, uhr):
    _alle_fertig(kind, uhr, 1, SLOTS[:1])
    services.slot_leeren(kind, "kopf")
    assert selectors.ausbaustufe(kind).aktuell == 1


def test_metriken_registriert():
    namen = {m.schluessel for m in registry.metriken("avatar")}
    assert {"ausbaustufe", *(f"ausbaustufe_seltenheit_{n}" for n in range(1, 7))} <= namen
    assert registry.provider_vorhanden("metrik.ausbaustufe.bereiche")


# --- Slots ----------------------------------------------------------------------------------


def test_anlegen_nur_eigene_fertige(kind, uhr):
    m = mod("ritter", "koerper", 1)
    with pytest.raises(services.ModFehler):
        services.mod_anlegen(kind, m)
    services.mod_kaufen(kind, m)
    with pytest.raises(services.ModFehler):
        services.mod_anlegen(kind, m)  # noch im Bau
    uhr.weiter(days=5)
    services.mods_fertigstellen()
    services.slot_leeren(kind, "koerper")
    services.mod_anlegen(kind, m)
    assert Avatar.objects.get(pk=kind.pk).angelegt["koerper"] == m.schluessel


# --- Themenwechsel --------------------------------------------------------------------------


def test_themenwechsel_warnung_zahlen_und_wechsel(kind, uhr):
    einstellungen.setzen("avatar.max_zaehlende_mods_woche", 6, akteur=None)
    _alle_fertig(kind, uhr, 1, SLOTS[:2])
    services.mod_kaufen(kind, mod("ritter", "hand", 1))  # noch im Bau
    bezahlt = sum(b.preis_bezahlt for b in ModBesitz.objects.all())
    w = services.themenwechsel_vorschau(kind, "pirat")
    assert (w.verlorene_mods, w.davon_im_bau, w.wert) == (3, 1, bezahlt)
    assert w.ausbaustufe_vorher == 2
    assert (w.mods_bis_meilenstein, w.wochen_mindestens) == (6, 1)
    with pytest.raises(services.ModFehler, match="geändert"):
        services.thema_wechseln(kind, "pirat", pruefwert="pirat:0:0:0")
    guthaben = punkte.guthaben(kind)
    services.thema_wechseln(kind, "pirat", pruefwert=w.pruefwert)
    avatar = Avatar.objects.get(pk=kind.pk)
    assert avatar.thema.schluessel == "pirat"
    assert avatar.angelegt == {}
    assert set(ModBesitz.objects.values_list("status", flat=True)) == {BesitzStatus.VERLOREN}
    assert punkte.guthaben(kind) == guthaben  # keine Erstattung
    stufe = selectors.ausbaustufe(kind)
    assert stufe.aktuell == 0 and stufe.je_seltenheit[1] == 0
    assert registry.fortschritt("metrik.ausbaustufe_seltenheit_1", kind) == 0
    assert AuditEintrag.objects.filter(aktion="avatar.thema_gewechselt").count() == 1
    assert Ereignis.objects.filter(typ_id="thema.gewechselt").count() == 1
    # Bau des alten Themas wird nicht mehr fertig
    uhr.weiter(days=10)
    assert services.mods_fertigstellen()["fertig"] == 0


def test_themenwechsel_zeitbremse_zaehlt_neu_und_rueckkauf_moeglich(kind, uhr):
    m = mod("ritter", "kopf", 1)
    services.mod_kaufen(kind, m)
    w = services.themenwechsel_vorschau(kind, "pirat")
    services.thema_wechseln(kind, "pirat", pruefwert=w.pruefwert)
    w = services.themenwechsel_vorschau(kind, "ritter")
    services.thema_wechseln(kind, "ritter", pruefwert=w.pruefwert)
    besitz = services.mod_kaufen(kind, m)  # neuer Kauf, neuer Idempotenz-Schlüssel
    assert besitz.buchung.idempotenz_schluessel.endswith(":2")
    assert Buchung.objects.filter(art=Art.MODKAUF).count() == 2


def test_themenwechsel_gleiches_thema_abgelehnt(kind):
    with pytest.raises(services.ModFehler, match="schon dein Thema"):
        services.themenwechsel_vorschau(kind, "ritter")


def test_rang_bleibt_nach_themenwechsel(kind):
    rang_geben(kind, 3)
    w = services.themenwechsel_vorschau(kind, "ninja")
    services.thema_wechseln(kind, "ninja", pruefwert=w.pruefwert)
    assert selectors.ausbaustufe(kind).rang_stufe == 3


# --- Texte ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stunden, text",
    [(0, "sofort"), (5, "5 Stunden"), (24, "1 Tag"), (48, "2 Tage"), (36, "2 Tage")],
)
def test_dauer_text(stunden, text):
    assert mods.dauer_text(stunden) == text


def test_rest_text():
    jetzt = MONTAG
    assert mods.rest_text(jetzt + timedelta(days=2), jetzt) == "in 2 Tagen"
    assert mods.rest_text(jetzt + timedelta(hours=5), jetzt) == "in 5 Stunden"
    assert mods.rest_text(jetzt - timedelta(hours=1), jetzt) == "gleich"
