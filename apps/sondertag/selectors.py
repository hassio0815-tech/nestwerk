"""Lesende Schnittstelle von sondertag (AP27): Warteschlange, Fortschritt fürs Kind, Übersicht
für die Eltern. Alles live gerechnet (``services.plan``), nichts wird beim Lesen gespeichert.

Fortschritt zum nächsten Sondertag (ARCHITECTURE 7.9): aus den aktiven Meilenstein-Regeln mit
``belohnungsart = sondertag`` (Bedingungen über ``spielregeln.meilenstein_stand`` bzw. Metriken)
und den Grenzen: Wochen = max(Wochen für fehlende Mods bei N zählenden Mods je Woche, Wochen bis
die Grenzen einen weiteren Sondertag erlauben, offene Wochen im God-Mode-Zyklus).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.kern import einstellungen, zeit
from apps.kern.einstellungen import EinstellungFehler
from apps.kern.registry import UnbekannterEintrag
from apps.kern.sprache import uebersetzt
from apps.konten import selectors as konten
from apps.spielregeln import registry as metriken
from apps.spielregeln import selectors as spielregeln

from . import events, grenzen, services
from .meilensteine_start import GODMODE_SCHLUESSEL
from .models import ANGENOMMEN, BegleitungWunsch, SondertagAnspruch, Status

TAGE_BESTAETIGUNG = 45  # so lange zeigt die Kind-Kachel "Wunsch angenommen"


@dataclass(frozen=True)
class Eintrag:
    """Offener Anspruch mit live gerechnetem Einlösedatum."""

    anspruch: SondertagAnspruch
    einloesbar_ab: date
    position: int  # 0 = vorne in der Warteschlange
    heute: date

    @property
    def einloesbar(self) -> bool:
        return self.position == 0 and self.einloesbar_ab <= self.heute

    @property
    def wunsch_offen(self) -> bool:
        return self.anspruch.status == Status.WUNSCH_OFFEN

    @property
    def tage_bis(self) -> int:
        return max(0, (self.einloesbar_ab - self.heute).days)


def warteschlange(kind, heute: date | None = None) -> list[Eintrag]:
    heute = heute or zeit.heute()
    return [Eintrag(a, ab, i, heute) for i, (a, ab) in enumerate(services.plan(kind, heute))]


def aktueller(kind, heute: date | None = None) -> Eintrag | None:
    liste = warteschlange(kind, heute)
    return liste[0] if liste else None


def historie(kind):
    return (
        SondertagAnspruch.objects.filter(kind=kind, status__in=ANGENOMMEN)
        .select_related("begleitung", "angenommen_von")
        .order_by("-annahme_datum", "-id")
    )


def letzter(kind) -> SondertagAnspruch | None:
    return historie(kind).first()


def naechster_moeglich(kind, heute: date | None = None) -> date:
    """Frühestes Datum, an dem die Grenzen einen weiteren Sondertag erlauben würden (ab heute,
    offene Ansprüche in der Warteschlange eingerechnet)."""
    heute = heute or zeit.heute()
    r = services.regeln()
    daten = services.angenommene_daten(kind) + [
        max(e.einloesbar_ab, heute) for e in warteschlange(kind, heute)
    ]
    return grenzen.einloesbar_ab(heute, daten, r)


def wunsch_erlaubt(eintrag: Eintrag | None) -> bool:
    if eintrag is None or eintrag.position != 0:
        return False
    if eintrag.einloesbar:
        return True
    return bool(einstellungen.wert("sondertag.wunsch_vor_einloesbar_erlaubt"))


def begleitung_optionen() -> list[dict]:
    """Auswahl im Wunsch-Formular: Mama/Papa mit Namen aus ``konten``, dazu "egal"."""
    optionen = []
    for wert in (BegleitungWunsch.MAMA, BegleitungWunsch.PAPA):
        e = services.eltern_mit_label(wert)
        optionen.append({"wert": wert, "label": wert.label, "name": e.anzeigename if e else ""})
    optionen.append({"wert": BegleitungWunsch.EGAL, "label": _("egal"), "name": ""})
    return optionen


def begleitung_text(wunsch: str) -> str:
    return services.begleitung_text(wunsch)


# --- Fortschritt zum nächsten Sondertag -------------------------------------------------------


@dataclass
class Fortschritt:
    """Für die Kind-Kachel. ``art``: ``einloesbar`` | ``wunsch_offen`` | ``verdient`` |
    ``unterwegs`` | ``ab_rang`` | ``keiner``."""

    art: str
    text: str
    eintrag: Eintrag | None = None
    mods_fehlen: int = 0
    wochen_fehlen: int = 0
    mods_ziel: int = 0
    mods_ist: int = 0
    warten: int = 0  # weitere verdiente Sondertage in der Warteschlange
    bestaetigt: SondertagAnspruch | None = None
    weiter: str = ""  # nächster Schritt nach dem offenen Anspruch
    extra: dict = field(default_factory=dict)

    @property
    def prozent(self) -> int:
        if not self.mods_ziel:
            return 0
        return min(100, 100 * self.mods_ist // self.mods_ziel)


def _wert(metrik, kind) -> int | None:
    try:
        return int(metriken.metrik_wert(metrik, kind) or 0)
    except UnbekannterEintrag:
        return None


def _einstellung(schluessel, standard):
    try:
        return einstellungen.wert(schluessel)
    except (EinstellungFehler, UnbekannterEintrag):
        return standard


def noch_text(mods: int, wochen: int) -> str:
    teile = []
    if mods:
        teile.append(ngettext("%(n)s Mod", "%(n)s Mods", mods) % {"n": mods})
    if wochen:
        teile.append(ngettext("%(n)s Woche", "%(n)s Wochen", wochen) % {"n": wochen})
    if not teile:
        return _("Fast geschafft: dein nächster Sondertag kommt gleich!")
    if len(teile) == 2:
        teile = [_("%(a)s und %(b)s") % {"a": teile[0], "b": teile[1]}]
    return _("Noch %(teile)s bis zum Sondertag") % {"teile": teile[0]}


def _rang_namen() -> dict[int, str]:
    return {r.stufe: uebersetzt(r.name) for r in spielregeln.raenge()}


def _kandidat_rang(kind, regel, namen) -> dict | None:
    """Fehlende Mods / fehlender Rang für eine einmalige Regel; ``None`` = schon erreicht."""
    if spielregeln.meilenstein_erreicht(kind, regel.schluessel) is not None:
        return None
    stand = spielregeln.meilenstein_stand(kind, regel.schluessel)
    rang_ziel, mods_fehlen, mods_ziel, mods_ist, unbekannt = 0, 0, 0, 0, False
    for b in stand:
        if b.wert is None:
            unbekannt = True
        elif b.metrik == "rang":
            if not b.erfuellt:
                rang_ziel = b.ziel
        elif not b.erfuellt:
            mods_fehlen += max(0, b.ziel - b.wert)
            mods_ziel += b.ziel
            mods_ist += b.wert
        else:
            mods_ziel += b.ziel
            mods_ist += b.ziel
    if unbekannt:
        return None
    return {
        "regel": regel,
        "rang_ziel": rang_ziel,
        "rang_name": namen.get(rang_ziel, str(rang_ziel)),
        "mods_fehlen": mods_fehlen,
        "mods_ziel": mods_ziel,
        "mods_ist": mods_ist,
        "wochen": 0,
    }


def _kandidat_godmode(kind, regel) -> dict | None:
    """Laufender God-Mode-Zyklus: fehlende Wochen und Mods des aktuellen Sets."""
    aktivwochen = _wert("godmode_aktivwochen", kind)
    namen = _rang_namen()
    if aktivwochen is None or not namen or (_wert("rang", kind) or 0) < max(namen):
        return None
    laenge = max(1, int(_einstellung("avatar.godmode_zyklus_aktivwochen", 26)))
    # frühester noch nicht erreichter Zyklus (ein altes Set kann noch fertig werden)
    erreicht = {f.bereich for f in spielregeln.meilensteine_erreicht(kind, regel.schluessel)}
    zyklus = 1
    while f"zyklus-{zyklus}" in erreicht:
        zyklus += 1
    bereich = f"zyklus-{zyklus}"
    try:
        sets = metriken.metrik_bereiche("godmode_set_vollstaendig", kind) or {}
    except UnbekannterEintrag:
        return None
    ziel = next(
        (
            b.get("wert", 6)
            for b in regel.bedingungen
            if b.get("metrik") == "godmode_set_vollstaendig"
        ),
        6,
    )
    ist = sets.get(bereich, (0, ""))[0]
    return {
        "regel": regel,
        "rang_ziel": 0,
        "rang_name": "",
        "mods_fehlen": max(0, ziel - ist),
        "mods_ziel": ziel,
        "mods_ist": min(ist, ziel),
        "wochen": max(0, zyklus * laenge - aktivwochen),
        "zyklus": zyklus,
    }


def _naechster_schritt(kind, heute: date) -> dict | None:
    regeln = [
        r
        for r in spielregeln.meilenstein_regeln()
        .filter(aktiv=True, belohnungsart=events.BELOHNUNGSART)
        .order_by("reihenfolge", "id")
    ]
    namen = _rang_namen()
    erreichbar, spaeter = [], []
    for regel in regeln:
        if regel.schluessel == GODMODE_SCHLUESSEL or regel.wiederholbar == "bereich":
            k = _kandidat_godmode(kind, regel)
        else:
            k = _kandidat_rang(kind, regel, namen)
        if k is None:
            continue
        (spaeter if k["rang_ziel"] else erreichbar).append(k)
    if erreichbar:
        return min(
            erreichbar, key=lambda k: (k["mods_fehlen"] + k["wochen"], k["regel"].reihenfolge)
        )
    if spaeter:
        return min(spaeter, key=lambda k: (k["rang_ziel"], k["regel"].reihenfolge))
    return None


def _schritt_text(k, kind, heute) -> tuple[str, int]:
    """Text und Wochen für einen Kandidaten (inkl. Zeitbremse und Grenzen)."""
    if k["rang_ziel"]:
        return (
            _(
                "Ab Rang %(rang)s: alle 6 Slots mit %(rang)s-Mods bauen "
                "bringt deinen nächsten Sondertag."
            )
            % {"rang": k["rang_name"]},
            0,
        )
    pro_woche = max(1, int(_einstellung("avatar.max_zaehlende_mods_woche", 1)))
    wochen_mods = math.ceil(k["mods_fehlen"] / pro_woche) if k["mods_fehlen"] else 0
    grenze = naechster_moeglich(kind, heute)
    wochen_grenze = math.ceil(max(0, (grenze - heute).days) / 7)
    wochen = max(wochen_mods, wochen_grenze, k["wochen"])
    return noch_text(k["mods_fehlen"], wochen), wochen


def fortschritt(kind, heute: date | None = None) -> Fortschritt:
    heute = heute or zeit.heute()
    liste = warteschlange(kind, heute)
    bestaetigt = (
        SondertagAnspruch.objects.filter(
            kind=kind,
            status=Status.ANGENOMMEN,
            annahme_datum__gte=date.fromordinal(max(1, heute.toordinal() - TAGE_BESTAETIGUNG)),
        )
        .select_related("begleitung")
        .order_by("-annahme_datum", "-id")
        .first()
    )
    k = _naechster_schritt(kind, heute)
    if liste:
        e = liste[0]
        if e.einloesbar and e.wunsch_offen:
            art, text = "wunsch_offen", _("Dein Wunsch ist bei Mama und Papa. Sie melden sich!")
        elif e.einloesbar:
            art, text = "einloesbar", _("Sondertag verdient! Wünsch dir etwas.")
        elif e.wunsch_offen:
            art = "wunsch_offen"
            text = _("Wunsch gesendet. Verdient, einlösbar ab %(datum)s.") % {
                "datum": services.datum_text(e.einloesbar_ab)
            }
        else:
            art = "verdient"
            text = _("Sondertag verdient, einlösbar ab %(datum)s.") % {
                "datum": services.datum_text(e.einloesbar_ab)
            }
        weiter = ""
        if k is not None:
            weiter = _schritt_text(k, kind, heute)[0]
        return Fortschritt(
            art, text, eintrag=e, warten=len(liste) - 1, bestaetigt=bestaetigt, weiter=weiter
        )
    if k is None:
        return Fortschritt("keiner", _("Alle Sondertage verdient. Stark!"), bestaetigt=bestaetigt)
    text, wochen = _schritt_text(k, kind, heute)
    return Fortschritt(
        "ab_rang" if k["rang_ziel"] else "unterwegs",
        text,
        mods_fehlen=k["mods_fehlen"],
        wochen_fehlen=wochen,
        mods_ziel=k["mods_ziel"],
        mods_ist=k["mods_ist"],
        bestaetigt=bestaetigt,
        extra={"zyklus": k.get("zyklus"), "regel": uebersetzt(k["regel"].name)},
    )


# --- Eltern -----------------------------------------------------------------------------------


def offene_wuensche(heute: date | None = None) -> list[Eintrag]:
    heute = heute or zeit.heute()
    ergebnis = []
    for kind in konten.aktive_kinder():
        ergebnis += [e for e in warteschlange(kind, heute) if e.wunsch_offen]
    return ergebnis


def angenommen_offen():
    """Angenommene Sondertage, die noch nicht stattgefunden haben (Übergabe, erledigt)."""
    return (
        SondertagAnspruch.objects.filter(status=Status.ANGENOMMEN)
        .select_related("kind", "begleitung", "angenommen_von")
        .order_by("annahme_datum", "id")
    )


def zuletzt_mit(kind, eltern) -> list[dict]:
    """Je Elternteil: letzter Sondertag dieses Kindes mit ihm (Übersicht "wer mit wem")."""
    zeilen = []
    for e in eltern:
        letzter_ = historie(kind).filter(begleitung=e).first()
        zeilen.append({"eltern": e, "datum": letzter_.annahme_datum if letzter_ else None})
    return zeilen


def eltern_uebersicht(heute: date | None = None) -> list[dict]:
    """Je aktivem Kind: letzter Sondertag (mit wem), nächster möglicher, Warteschlange."""
    heute = heute or zeit.heute()
    eltern = list(konten.aktive_eltern())
    zeilen = []
    for kind in konten.aktive_kinder():
        liste = warteschlange(kind, heute)
        zeilen.append(
            {
                "kind": kind,
                "letzter": letzter(kind),
                "naechster_moeglich": naechster_moeglich(kind, heute),
                "warteschlange": liste,
                "mit_wem": zuletzt_mit(kind, eltern),
                "historie": list(historie(kind)),
                "fortschritt": fortschritt(kind, heute),
            }
        )
    return zeilen
