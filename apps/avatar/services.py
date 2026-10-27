"""Schreibende und rendernde Schnittstelle von avatar.

- Bild: ``svg_fuer(benutzer)``/``bild_url(benutzer)``, ``vorschau_mit_mod(kind, mod)``.
- Slots: ``slot_belegen(kind, slot, mod)`` (prüft den Besitz NICHT, Kinder-Oberfläche nutzt
  ``mod_anlegen``), ``slot_leeren(kind, slot)``.
- Mods (AP26, Logik in ``mods``): ``mod_kaufen(kind, mod)``, ``mod_anlegen(kind, mod)``,
  ``mods_fertigstellen()`` (Job), ``bau_sofort_fertigstellen(besitz, von=)``,
  ``themenwechsel_vorschau(kind, thema)``, ``thema_wechseln(kind, thema, pruefwert=)``,
  ``mod_standard_aendern(rang, von=, mod_preis=, bauzeit_stunden=)``,
  ``mod_faktoren_setzen(von=, faktor_preis=, faktor_bauzeit=)``. Fehler: ``ModFehler``.
"""

import hashlib
import logging
import unicodedata
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.translation import gettext

from apps.kern import audit, zeit
from apps.spielregeln.services import (  # noqa: F401 (Mod-Standards, AP26)
    mod_faktoren_setzen,
    mod_standard_aendern,
)

from .generator import bibliothek, renderer
from .models import Avatar, ModDefinition, RenderCache, Thema
from .mods import (  # noqa: F401 (öffentliche Mod-API, AP26)
    ModFehler,
    thema_wechseln,
    themenwechsel_vorschau,
)
from .mods import anlegen as mod_anlegen  # noqa: F401
from .mods import fertigstellen as mods_fertigstellen  # noqa: F401
from .mods import kaufen as mod_kaufen  # noqa: F401
from .mods import sofort_fertigstellen as bau_sofort_fertigstellen  # noqa: F401
from .ruhmeshalle import (  # noqa: F401 (Ruhmeshalle, P3-A)
    in_ruhmeshalle_stellen,
    widmung_setzen,
)

logger = logging.getLogger(__name__)

_SPEICHER = {}
_SPEICHER_MAX = 512
NUTZUNG_AUFFRISCHEN = timedelta(days=1)


class AvatarFehler(Exception):
    """Fachlicher Fehler (Meldung ist für Anwender lesbar)."""


# --- Figur -------------------------------------------------------------------------------------


def figur_pruefen(figur, thema=None):
    """Normalisierte Figur (haut, haar, frisur) oder ``AvatarFehler``."""
    lib = bibliothek.figur()
    figur = {**bibliothek.STANDARD_FIGUR, **(figur or {})}
    if figur["haut"] not in lib["hautfarben"]:
        raise AvatarFehler(gettext("Unbekannter Hautton"))
    if figur["haar"] not in lib["haarfarben"]:
        raise AvatarFehler(gettext("Unbekannte Haarfarbe"))
    erlaubt = (thema.figur_varianten if thema else None) or list(lib["frisuren"])
    if figur["frisur"] not in erlaubt:
        raise AvatarFehler(gettext("Unbekannte Frisur"))
    return {k: figur[k] for k in ("haut", "haar", "frisur")}


# --- Rendern mit Cache ---------------------------------------------------------------------------


def _merken(hash_, svg):
    if len(_SPEICHER) >= _SPEICHER_MAX:
        _SPEICHER.clear()
    _SPEICHER[hash_] = svg


def svg_nach_hash(hash_):
    """SVG aus Prozess-Speicher oder ``RenderCache``; ``None`` wenn unbekannt."""
    svg = _SPEICHER.get(hash_)
    if svg is not None:
        return svg
    zeile = RenderCache.objects.filter(pk=hash_).first()
    if zeile is None:
        return None
    jetzt = zeit.jetzt()
    if jetzt - zeile.zuletzt_genutzt > NUTZUNG_AUFFRISCHEN:
        RenderCache.objects.filter(pk=hash_).update(zuletzt_genutzt=jetzt)
    _merken(hash_, zeile.svg)
    return zeile.svg


def zustand_rendern(zustand):
    """``(hash, svg)``; rendert nur bei Cache-Miss und legt das Ergebnis ab."""
    hash_ = renderer.hash_von(zustand)
    svg = svg_nach_hash(hash_)
    if svg is None:
        svg = renderer.rendern(zustand)
        jetzt = zeit.jetzt()
        RenderCache.objects.get_or_create(
            hash=hash_, defaults={"svg": svg, "erstellt_am": jetzt, "zuletzt_genutzt": jetzt}
        )
        _merken(hash_, svg)
    return hash_, svg


def zustand_von(avatar):
    """Render-Eingabe eines Avatars (Thema aus der DB, angelegte Mods)."""
    mods = {}
    if avatar.angelegt:
        gefunden = {
            m.schluessel: m
            for m in ModDefinition.objects.filter(
                schluessel__in=list(avatar.angelegt.values()), aktiv=True
            ).select_related("slot")
        }
        for slot, schluessel in avatar.angelegt.items():
            if schluessel in gefunden:
                mods[slot] = gefunden[schluessel].render_mod()
    return {
        "thema": avatar.thema.schluessel,
        "thema_daten": avatar.thema.als_dict(),
        "figur": avatar.figur,
        "mods": mods,
    }


def _ohne_defekte_mods(avatar, zustand):
    """Ein kaputter Mod darf nicht das ganze Bild kippen: schrittweise ohne ihn rendern."""
    for slot in list(zustand["mods"]):
        versuch = {**zustand, "mods": {k: v for k, v in zustand["mods"].items() if k != slot}}
        try:
            renderer.rendern(zustand | {"mods": {slot: zustand["mods"][slot]}})
        except renderer.RenderFehler:
            logger.warning("Mod im Slot %s von %s nicht renderbar, wird ausgelassen", slot, avatar)
            zustand = versuch
    return zustand


def hash_aktualisieren(avatar):
    """Render-Hash neu berechnen, Bild rendern/ablegen, ``avatar.render_hash`` speichern."""
    zustand = zustand_von(avatar)
    try:
        hash_, svg = zustand_rendern(zustand)
    except renderer.RenderFehler:
        zustand = _ohne_defekte_mods(avatar, zustand)
        hash_, svg = zustand_rendern(zustand)
    if avatar.render_hash != hash_:
        avatar.render_hash = hash_
        Avatar.objects.filter(pk=avatar.pk).update(render_hash=hash_)
    return hash_, svg


def hashes_aktualisieren():
    """Nach Änderungen an Bibliothek/Themen/Mods: alle Avatare neu rendern (wenige Zeilen)."""
    n = 0
    for avatar in Avatar.objects.select_related("thema"):
        hash_aktualisieren(avatar)
        n += 1
    return n


# --- Eltern und Kinder: Bild je Benutzer -------------------------------------------------------


def eltern_zustand(benutzer):
    """Eltern-Figur: gleicher Generator, Thema ``eltern``, keine Mods; Haut/Haar/Frisur stabil
    aus der Benutzer-ID abgeleitet (kein Datenbankeintrag nötig)."""
    z = int.from_bytes(hashlib.sha256(str(benutzer.pk).encode()).digest()[:6], "big")
    return {
        "thema": bibliothek.ELTERN_THEMA,
        "figur": {
            "haut": bibliothek.ELTERN_HAUT[z % len(bibliothek.ELTERN_HAUT)],
            "haar": bibliothek.ELTERN_HAAR[(z // 7) % len(bibliothek.ELTERN_HAAR)],
            "frisur": ("kurz", "struppig", "lang")[(z // 49) % 3],
        },
    }


NEUTRAL = {"thema": bibliothek.ELTERN_THEMA}


def svg_fuer(benutzer):
    """``(hash, svg)`` für einen Benutzer: Eltern-Figur, Kind-Avatar oder (Kind ohne Wahl)
    die neutrale Figur."""
    if benutzer.ist_eltern:
        return zustand_rendern(eltern_zustand(benutzer))
    avatar = Avatar.objects.select_related("thema").filter(pk=benutzer.pk).first()
    if avatar is None:
        return zustand_rendern(NEUTRAL)
    if avatar.render_hash:
        svg = svg_nach_hash(avatar.render_hash)
        if svg is not None:
            return avatar.render_hash, svg
    return hash_aktualisieren(avatar)


def bild_url(benutzer):
    """URL des ausgelieferten SVG (Hash in der URL: ändert sich mit jeder Änderung)."""
    hash_, _ = svg_fuer(benutzer)
    return reverse("avatar:svg", args=[hash_])


def vorschau_svg(thema_schluessel, figur=None, mods=None):
    """SVG ohne Speicherung (Auswahl-Vorschau, Galerie). Nutzt Prozess-Speicher nicht."""
    zustand = {"thema": thema_schluessel, "figur": figur or {}, "mods": mods or {}}
    return renderer.rendern(zustand)


def vorschau_basis(kind):
    """Render-Eingabe des eigenen Avatars (für mehrere ``vorschau_mit_mod``) oder ``None``."""
    avatar = Avatar.objects.select_related("thema").filter(pk=kind.pk).first()
    return zustand_von(avatar) if avatar else None


def vorschau_mit_mod(kind, mod, basis=None):
    """SVG des eigenen Avatars mit ``mod`` im Slot (Shop-Vorschau, ohne Speicherung)."""
    basis = basis or vorschau_basis(kind)
    if basis is None:
        return vorschau_svg(mod.thema.schluessel, mods={mod.slot.schluessel: mod.render_mod()})
    zustand = {**basis, "mods": {**basis["mods"], mod.slot.schluessel: mod.render_mod()}}
    try:
        return renderer.rendern(zustand)
    except renderer.RenderFehler:
        logger.warning("Vorschau für Mod %s nicht renderbar", mod.schluessel)
        return renderer.rendern(basis)


# --- Auswahl und Slots -------------------------------------------------------------------------


@transaction.atomic
def avatar_waehlen(kind, thema_schluessel, figur):
    """Erstwahl von Figur und Thema. Späterer Wechsel: ``thema_wechseln`` (mit Warnung)."""
    if not kind.ist_kind:
        raise AvatarFehler(gettext("Nur Kinder wählen einen Avatar"))
    thema = Thema.objects.filter(schluessel=thema_schluessel, aktiv=True, nur_eltern=False).first()
    if thema is None:
        raise AvatarFehler(gettext("Bitte wähle ein Thema"))
    figur = figur_pruefen(figur, thema)
    try:
        with transaction.atomic():
            avatar = Avatar.objects.create(benutzer=kind, thema=thema, figur=figur)
    except IntegrityError:
        raise AvatarFehler(gettext("Du hast schon einen Avatar")) from None
    hash_aktualisieren(avatar)
    return avatar


@transaction.atomic
def figur_aendern(kind, figur):
    """Hautton, Haare und Frisur ändern (kostet nichts, Thema und Mods bleiben)."""
    avatar = Avatar.objects.select_for_update().select_related("thema").get(pk=kind.pk)
    avatar.figur = figur_pruefen(figur, avatar.thema)
    avatar.save(update_fields=["figur"])
    hash_aktualisieren(avatar)
    return avatar


def _mod(mod):
    if isinstance(mod, ModDefinition):
        return mod
    try:
        return ModDefinition.objects.select_related("slot", "thema").get(schluessel=mod)
    except ModDefinition.DoesNotExist:
        raise AvatarFehler(gettext("Unbekannter Mod")) from None


@transaction.atomic
def slot_belegen(kind, slot, mod):
    """Legt einen (fertigen, vom Aufrufer geprüften) Mod in den Slot. Das Thema des Mods muss
    zum Avatar passen."""
    avatar = Avatar.objects.select_for_update().select_related("thema").get(pk=kind.pk)
    mod = _mod(mod)
    if mod.slot.schluessel != slot:
        raise AvatarFehler(gettext("Der Mod passt nicht in diesen Slot"))
    if mod.thema_id != avatar.thema_id:
        raise AvatarFehler(gettext("Der Mod gehört zu einem anderen Thema"))
    if not mod.aktiv:
        raise AvatarFehler(gettext("Der Mod ist nicht verfügbar"))
    avatar.angelegt = {**avatar.angelegt, slot: mod.schluessel}
    avatar.save(update_fields=["angelegt"])
    hash_aktualisieren(avatar)
    return avatar


@transaction.atomic
def slot_leeren(kind, slot):
    avatar = Avatar.objects.select_for_update().select_related("thema").get(pk=kind.pk)
    avatar.angelegt = {k: v for k, v in avatar.angelegt.items() if k != slot}
    avatar.save(update_fields=["angelegt"])
    hash_aktualisieren(avatar)
    return avatar


# --- Aufräumen ---------------------------------------------------------------------------------


def cache_aufraeumen(tage=30):
    """Löscht Cache-Zeilen, die kein Avatar mehr referenziert und die lange unbenutzt sind
    (für den Job ``aufraeumen``). Gibt die Zahl gelöschter Zeilen zurück."""
    grenze = zeit.jetzt() - timedelta(days=tage)
    verwendet = Avatar.objects.exclude(render_hash="").values_list("render_hash", flat=True)
    zeilen = RenderCache.objects.filter(zuletzt_genutzt__lt=grenze).exclude(hash__in=verwendet)
    anzahl = zeilen.count()
    zeilen.delete()
    _SPEICHER.clear()
    return anzahl


# --- Figurenname ---------------------------------------------------------------------------------

NAME_MAX = 20


def name_bereinigen(roh) -> str:
    """Steuer- und Formatzeichen raus, Leerraum zusammenfassen, trimmen. Zu lang -> Fehler."""
    text = "".join(" " if z.isspace() else z for z in str(roh or ""))
    text = "".join(z for z in text if unicodedata.category(z)[0] != "C")
    text = " ".join(text.split())
    if len(text) > NAME_MAX:
        raise AvatarFehler(
            gettext("Der Name darf höchstens %(max)s Zeichen haben.") % {"max": NAME_MAX}
        )
    return text


def avatar_name_setzen(kind, roh) -> str:
    """Kind benennt seine Figur (leer = Name entfernen). Gibt den gespeicherten Namen zurück."""
    name = name_bereinigen(roh)
    treffer = Avatar.objects.filter(pk=kind.pk).update(name=name)
    if not treffer:
        raise AvatarFehler(gettext("Wähle zuerst deinen Avatar."))
    return name


def avatar_name_zuruecksetzen(kind, *, von) -> bool:
    """Eltern leeren den Namen (Protokoll). ``False``, wenn es nichts zu leeren gab."""
    avatar = Avatar.objects.filter(pk=kind.pk).first()
    if avatar is None or not avatar.name:
        return False
    alt = avatar.name
    Avatar.objects.filter(pk=kind.pk).update(name="")
    audit.protokollieren(
        "avatar.name_zurueckgesetzt", akteur=von, objekt=avatar, kind=kind, details={"alt": alt}
    )
    return True


def avatar_name(benutzer) -> str:
    """Anzeigename der Figur; ohne eigenen Namen der Name des Kindes."""
    name = Avatar.objects.filter(pk=benutzer.pk).values_list("name", flat=True).first()
    return name or benutzer.anzeigename
