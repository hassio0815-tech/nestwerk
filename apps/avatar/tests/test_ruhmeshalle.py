"""P3-A: Ruhmeshalle (Entscheidung 33): Freischaltung, nichts geht verloren, Idempotenz,
Snapshot, Abzeichen, Rollen."""

import itertools
from datetime import UTC, datetime

import pytest
from django.test import Client
from django.urls import reverse

from apps.avatar import ruhmeshalle, services
from apps.avatar.models import Avatar, BesitzStatus, ModBesitz, ModDefinition, Thema
from apps.avatar.models import RuhmeshallenEintrag as Eintrag
from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen
from apps.kern.models import AuditEintrag
from apps.konten.tests.conftest import angemeldet
from apps.punkte import selectors as punkte
from apps.punkte import services as punkte_services
from apps.punkte.models import Art, Buchung
from apps.spielregeln import services as spielregeln
from apps.spielregeln.models import AbzeichenVerleihung

pytestmark = pytest.mark.django_db

_zaehler = itertools.count()
MONTAG = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
SLOTS = ("kopf", "koerper", "ruecken", "hand", "begleiter", "hintergrund")


def gutschrift(kind, n):
    return punkte_services.buchen(
        kind,
        Art.AUFGABE,
        n,
        schluessel=f"halle:{next(_zaehler)}",
        quelle_modul="aufgaben",
        von=None,
    )


def mod(thema, slot, seltenheit=1):
    return ModDefinition.objects.get(
        thema__schluessel=thema, slot__schluessel=slot, seltenheit=seltenheit
    )


def ausbauen(kind, uhr, slots=SLOTS, anlegen=True):
    einstellungen.setzen("avatar.max_zaehlende_mods_woche", 6, akteur=None)
    for slot in slots:
        services.mod_kaufen(kind, mod("ritter", slot))
    uhr.weiter(days=8)
    services.mods_fertigstellen()
    if anlegen:
        for slot in slots:
            services.mod_anlegen(kind, mod("ritter", slot))


@pytest.fixture
def kind(anna, uhr):
    uhr.jetzt = MONTAG
    services.avatar_waehlen(anna, "ritter", {})
    gutschrift(anna, 5000)
    return anna


@pytest.fixture
def held(kind, uhr):
    ausbauen(kind, uhr)
    return kind


def bau_start(kind):
    return ruhmeshalle.bereitschaft(kind).bau_start


# --- Freischaltung ---------------------------------------------------------------------------


def test_nicht_bereit_unter_ausbaustufe_6(kind, uhr):
    ausbauen(kind, uhr, SLOTS[:5])
    assert not ruhmeshalle.bereitschaft(kind).bereit
    with pytest.raises(services.ModFehler, match="ab Ausbaustufe 6"):
        services.in_ruhmeshalle_stellen(kind, "pirat", bau_start=bau_start(kind))
    assert not Eintrag.objects.exists()
    assert Avatar.objects.get(pk=kind.pk).thema.schluessel == "ritter"


def test_schwelle_ist_einstellung(kind, uhr):
    ausbauen(kind, uhr, SLOTS[:4])
    einstellungen.setzen("avatar.ruhmeshalle_ausbaustufe", 4, akteur=None)
    assert ruhmeshalle.bereitschaft(kind).bereit
    eintrag, neu = services.in_ruhmeshalle_stellen(kind, "pirat", bau_start=bau_start(kind))
    assert neu and eintrag.anzahl_mods == 4


def test_gesperrt_solange_bauauftrag_im_thema_laeuft(kind, uhr, kind_client):
    """AP36: laufender Bau würde sonst im alten Thema fertig -> klar gesperrt."""
    held = kind
    ausbauen(held, uhr, SLOTS[:5])
    einstellungen.setzen("avatar.ruhmeshalle_ausbaustufe", 5, akteur=None)
    services.mod_kaufen(held, mod("ritter", "hintergrund"))
    stand = ruhmeshalle.bereitschaft(held)
    assert stand.ausgebaut and stand.bau_laeuft == 1 and not stand.bereit
    with pytest.raises(services.ModFehler, match="Warte, bis dein Bauauftrag fertig ist"):
        services.in_ruhmeshalle_stellen(held, "pirat", bau_start=stand.bau_start)
    assert not Eintrag.objects.exists()
    assert Avatar.objects.get(pk=held.pk).thema.schluessel == "ritter"
    seite = kind_client.get(reverse("avatar:halle_kind")).content.decode()
    assert "Warte, bis dein Bauauftrag fertig ist" in seite
    assert reverse("avatar:halle_stellen") not in seite

    uhr.weiter(days=8)
    services.mods_fertigstellen()
    assert ruhmeshalle.bereitschaft(held).bereit
    _, neu = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    assert neu


def test_nur_kinder(held, mama):
    with pytest.raises(services.ModFehler):
        services.in_ruhmeshalle_stellen(mama, "pirat", bau_start="")


# --- Nichts geht verloren --------------------------------------------------------------------


def test_held_einfrieren_nichts_geht_verloren(held, uhr):
    kind = held
    xp, guthaben = punkte.xp(kind), punkte.guthaben(kind)
    buchungen = Buchung.objects.count()
    vorher = services.svg_fuer(kind)[1]
    start = bau_start(kind)
    uhr.weiter(days=3)

    eintrag, neu = services.in_ruhmeshalle_stellen(kind, "pirat", bau_start=start)

    assert neu
    avatar = Avatar.objects.get(pk=kind.pk)
    assert avatar.thema.schluessel == "pirat"
    assert avatar.angelegt == {}
    assert avatar.thema_gewaehlt_am == uhr.jetzt
    assert ruhmeshalle.bereitschaft(kind).aktuell == 0
    # Punkte, XP, Buchungen unverändert; Mods nicht "verloren", sondern eingefroren
    assert (punkte.xp(kind), punkte.guthaben(kind), Buchung.objects.count()) == (
        xp,
        guthaben,
        buchungen,
    )
    assert not ModBesitz.objects.filter(status=BesitzStatus.VERLOREN).exists()
    assert ModBesitz.objects.filter(status=BesitzStatus.EINGEFROREN).count() == 6
    # Eintrag
    assert eintrag.thema.schluessel == "ritter"
    assert eintrag.rang_stufe == 1 and eintrag.rang_selten
    assert eintrag.anzahl_mods == 6 and set(eintrag.mods) == set(SLOTS)
    assert eintrag.bauzeit_wochen == 2 and eintrag.aufgaben_anzahl == 1
    assert ruhmeshalle.svg_von(eintrag) == vorher
    # Audit + Ereignisse (Kind-Pop-up, Eltern-Info), Kein Themenwechsel-Ereignis
    assert AuditEintrag.objects.filter(aktion="avatar.ruhmeshalle_eintrag").count() == 1
    assert Ereignis.objects.filter(typ_id="ruhmeshalle.held").count() == 1
    assert Ereignis.objects.filter(typ_id="ruhmeshalle.eltern").count() == 1
    assert not Ereignis.objects.filter(typ_id="thema.gewechselt").exists()


def test_eingefrorene_mods_zaehlen_im_selben_thema_nicht_wieder(held):
    kind = held
    services.in_ruhmeshalle_stellen(kind, "ritter", bau_start=bau_start(kind))
    assert ruhmeshalle.bereitschaft(kind).aktuell == 0
    assert not ruhmeshalle.bereitschaft(kind).bereit


# --- Idempotenz ------------------------------------------------------------------------------


def test_doppelklick_erzeugt_einen_eintrag(held):
    start = bau_start(held)
    erster, neu1 = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=start)
    zweiter, neu2 = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=start)
    assert neu1 and not neu2 and erster.pk == zweiter.pk
    assert Eintrag.objects.count() == 1
    assert Ereignis.objects.filter(typ_id="ruhmeshalle.held").count() == 1
    assert AuditEintrag.objects.filter(aktion="avatar.ruhmeshalle_eintrag").count() == 1
    assert Avatar.objects.get(pk=held.pk).thema.schluessel == "pirat"


def test_veralteter_dialog_ohne_eintrag_wird_abgelehnt(held):
    with pytest.raises(services.ModFehler, match="geändert"):
        services.in_ruhmeshalle_stellen(held, "pirat", bau_start="2020-01-01T00:00:00+00:00")


# --- Snapshot --------------------------------------------------------------------------------


def test_snapshot_rendert_deterministisch_und_unabhaengig_vom_thema(held):
    eintrag, _ = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    bild = ruhmeshalle.svg_von(eintrag)
    assert bild.startswith("<svg") and ruhmeshalle.svg_von(Eintrag.objects.get()) == bild
    # Das Thema und der Mod werden später geändert: das Heldenbild bleibt gleich
    thema = Thema.objects.get(schluessel="ritter")
    thema.palette = {**thema.palette, "haupt": "#000000"}
    thema.save()
    ModDefinition.objects.filter(thema=thema).update(bauplan={"teile": []})
    assert ruhmeshalle.svg_von(Eintrag.objects.get()) == bild


def test_eintrag_ist_unveraenderlich(held):
    eintrag, _ = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    eintrag.rang_stufe = 6
    with pytest.raises(ValueError):
        eintrag.save()
    with pytest.raises(ValueError):
        eintrag.save(update_fields=["rang_stufe"])
    with pytest.raises(ValueError):
        eintrag.delete()
    assert Eintrag.objects.get().rang_stufe == 1


# --- Widmung ---------------------------------------------------------------------------------


def test_widmung_nur_eltern_mit_audit(held, mama):
    eintrag, _ = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    with pytest.raises(services.ModFehler):
        services.widmung_setzen(eintrag, "Selbst geschrieben", von=held)
    with pytest.raises(services.ModFehler, match="140"):
        services.widmung_setzen(eintrag, "x" * 141, von=mama)
    services.widmung_setzen(eintrag, "  Für unseren tapferen  Ritter ", von=mama)
    eintrag.refresh_from_db()
    assert eintrag.widmung == "Für unseren tapferen Ritter" and eintrag.widmung_von == mama
    services.widmung_setzen(eintrag, "Neu", von=mama)
    assert AuditEintrag.objects.filter(aktion="avatar.ruhmeshalle_widmung").count() == 2
    assert Eintrag.objects.get().widmung == "Neu"


# --- Abzeichen -------------------------------------------------------------------------------


def eintrag_direkt(kind, thema, rang=1):
    t = Thema.objects.get(schluessel=thema)
    return Eintrag.objects.create(
        kind=kind,
        thema=t,
        thema_daten=t.als_dict(),
        figur={"haut": "haut3", "haar": "haar2", "frisur": "kurz"},
        rang_stufe=rang,
        rang_name="x",
        rang_selten="common",
        themenstart=MONTAG.replace(day=1 + next(_zaehler) % 28, minute=next(_zaehler) % 60),
        bauzeit_wochen=1,
        anzahl_mods=6,
        aufgaben_anzahl=0,
    )


def abzeichen(kind):
    spielregeln.abzeichen_pruefen(kind)
    return set(
        AbzeichenVerleihung.objects.filter(kind=kind).values_list(
            "abzeichen__schluessel", flat=True
        )
    )


def test_startwerte_der_abzeichen():
    from apps.spielregeln.models import AbzeichenDefinition

    d = {a.schluessel: a for a in AbzeichenDefinition.objects.filter(gruppe="ruhmeshalle")}
    assert {k: (v.metrik, v.schwelle) for k, v in d.items()} == {
        "erster-held": ("ruhmeshalle_eintraege", 1),
        "heldentrio": ("ruhmeshalle_eintraege", 3),
        "sammler": ("ruhmeshalle_themen", 10),
        "legende": ("ruhmeshalle_hoechster_rang", 6),
    }


def test_erster_held_nach_dem_stellen(held):
    assert "erster-held" not in abzeichen(held)
    services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    verdient = {v.abzeichen.schluessel for v in AbzeichenVerleihung.objects.filter(kind=held)}
    assert "erster-held" in verdient  # schon durch die Prüfung nach dem Einfrieren


def test_heldentrio_sammler_legende(kind):
    erste = ["ritter", "pirat"]
    for t in erste:
        eintrag_direkt(kind, t)
    v = abzeichen(kind)
    assert "erster-held" in v and "heldentrio" not in v
    eintrag_direkt(kind, "ritter")  # gleiches Thema zählt für das Trio, nicht für den Sammler
    v = abzeichen(kind)
    assert "heldentrio" in v and "sammler" not in v and "legende" not in v
    for t in Thema.objects.filter(nur_eltern=False).values_list("schluessel", flat=True):
        if t not in erste:
            eintrag_direkt(kind, t)
    assert ruhmeshalle.metrik_themen(kind) == Thema.objects.filter(nur_eltern=False).count()
    eintrag_direkt(kind, "ritter", rang=6)
    v = abzeichen(kind)
    assert "legende" in v
    assert Thema.objects.filter(nur_eltern=False).count() == 10
    assert "sammler" in v


# --- Rollen und Oberfläche -------------------------------------------------------------------


def test_kind_sieht_nur_eigene_helden(held, ben, kind_client):
    eintrag_direkt(held, "pirat")
    ruhmeshalle.mit_bild(Eintrag.objects.all())
    antwort = kind_client.get(reverse("avatar:halle_kind"))
    assert antwort.status_code == 200
    assert antwort.content.decode().count('id="eintrag-') == 1
    fremd = angemeldet(Client(), ben)
    html = fremd.get(reverse("avatar:halle_kind")).content.decode()
    assert 'id="eintrag-' not in html and "Noch kein Held" in html


def test_stellen_dialog_und_post(held, kind_client):
    url = reverse("avatar:halle_stellen")
    html = kind_client.get(url + "?thema=pirat").content.decode()
    assert "Deinen Helden verewigen" in html and "verlierst nichts" in html
    start = bau_start(held)
    antwort = kind_client.post(url, {"thema": "pirat", "bau_start": start})
    assert antwort.status_code == 302 and antwort["Location"].startswith("/kind/ruhmeshalle/")
    zweite = kind_client.post(url, {"thema": "pirat", "bau_start": start})  # Doppelklick
    assert zweite.status_code == 302
    assert Eintrag.objects.count() == 1


def test_dialog_ohne_freischaltung_leitet_um(kind, kind_client):
    antwort = kind_client.get(reverse("avatar:halle_stellen"))
    assert antwort.status_code == 302


def test_widmung_view_nur_eltern(held, kind_client, eltern_client):
    eintrag, _ = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    url = reverse("avatar:halle_widmung", args=[eintrag.pk])
    assert kind_client.post(url, {"widmung": "Hallo"}).status_code in (302, 403)
    assert Eintrag.objects.get().widmung == ""
    assert eltern_client.post(url, {"widmung": "Hallo"}).status_code == 302
    assert Eintrag.objects.get().widmung == "Hallo"
    assert eltern_client.post(url, {"widmung": "y" * 200}).status_code == 400
    assert "Hallo" in eltern_client.get(reverse("avatar:halle_eltern")).content.decode()
    assert kind_client.get(reverse("avatar:halle_eltern")).status_code in (302, 403)


def test_tablet_kachel_zeigt_anzahl_helden(held, mama):
    tablet = reverse("oberflaeche:tablet_teil")
    assert "in der Ruhmeshalle" not in Client().get(tablet).content.decode()
    eintrag, _ = services.in_ruhmeshalle_stellen(held, "pirat", bau_start=bau_start(held))
    services.widmung_setzen(eintrag, "Für Anna", von=mama)
    html = Client().get(tablet).content.decode()
    assert "1 Held in der Ruhmeshalle" in html
    eintrag_direkt(held, "pirat")
    assert "2 Helden in der Ruhmeshalle" in Client().get(tablet).content.decode()
