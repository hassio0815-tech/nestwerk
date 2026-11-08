"""Schreibende Operationen von konten. Alle Änderungen laufen hier durch und werden
protokolliert (nie mit PIN oder Passwort). ``von`` ist der handelnde Elternteil; ohne Angabe
gilt der angemeldete Benutzer der Anfrage (``kern.audit``-Kontext)."""

import unicodedata
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.kern import audit, zeit

from . import moods, selectors, sperre
from .backends import PIN_MUSTER
from .models import (
    AnmeldeVersuch,
    Benutzer,
    ElternProfil,
    ElternZugang,
    Geraet,
    GeraeteTyp,
    KindProfil,
    MoodAusgeblendet,
    MoodEigen,
    MoodVorschlag,
    Rolle,
    VorschlagStatus,
)

PASSWORT_MINDESTLAENGE = 8
SPITZNAME_MAX = 20
MOOD_VORSCHLAEGE_OFFEN_MAX = 3
VERSUCHE_AUFBEWAHRUNG = timedelta(days=30)


def _pin_pruefen(pin):
    if not PIN_MUSTER.match(str(pin)):
        raise ValidationError(_("Die PIN besteht aus genau 4 Ziffern."))


def _freier_eltern_mood(ausser=None):
    belegt = Benutzer.objects.filter(rolle=Rolle.ELTERN, aktiv=True).exclude(mood="")
    if ausser is not None:
        belegt = belegt.exclude(pk=ausser.pk)
    return moods.zufaellig_eltern(belegt.values_list("mood", flat=True))


def _eltern_mood_pruefen(schluessel):
    if schluessel not in {s for s, _text, _g in selectors.mood_auswahl(moods.ELTERN)}:
        raise ValidationError(_("Diesen Mood gibt es nicht."))


def eltern_anlegen(
    anzeigename,
    *,
    rolle_label="andere",
    email="",
    reihenfolge=0,
    mood="",
    wappen_rolle="",
    wappen_rolle_eigen="",
):
    """Ohne ``mood`` wird zufällig einer vergeben (möglichst anders als bei den anderen
    Eltern)."""
    if mood:
        _eltern_mood_pruefen(mood)
    with transaction.atomic():
        benutzer = Benutzer(
            anzeigename=anzeigename,
            rolle=Rolle.ELTERN,
            reihenfolge=reihenfolge,
            mood=mood or _freier_eltern_mood(),
            wappen_rolle=wappen_rolle,
            wappen_rolle_eigen=wappen_rolle_eigen.strip(),
        )
        benutzer.set_unusable_password()
        benutzer.full_clean()
        benutzer.save()
        ElternProfil.objects.create(benutzer=benutzer, rolle_label=rolle_label, email=email)
        audit.protokollieren("konten.eltern_angelegt", objekt=benutzer)
    return benutzer


def eltern_aendern(
    benutzer,
    anzeigename,
    *,
    rolle_label,
    email,
    mood=None,
    wappen_rolle=None,
    wappen_rolle_eigen=None,
):
    """Ändert Name, Rolle (Mama/Papa/andere), E-Mail und optional den Mood eines Elternteils."""
    if mood:
        _eltern_mood_pruefen(mood)
    with transaction.atomic():
        benutzer.anzeigename = anzeigename
        felder = ["anzeigename"]
        if mood is not None or not benutzer.mood:
            benutzer.mood = mood or _freier_eltern_mood(ausser=benutzer)
            felder.append("mood")
        if wappen_rolle is not None:
            benutzer.wappen_rolle = wappen_rolle
            felder.append("wappen_rolle")
        if wappen_rolle_eigen is not None:
            benutzer.wappen_rolle_eigen = wappen_rolle_eigen.strip()
            felder.append("wappen_rolle_eigen")
        benutzer.full_clean(exclude=["password"])
        benutzer.save(update_fields=felder)
        profil = benutzer.elternprofil
        profil.rolle_label = rolle_label
        profil.email = email
        profil.full_clean()
        profil.save(update_fields=["rolle_label", "email"])
        audit.protokollieren("konten.eltern_geaendert", objekt=benutzer)


def eltern_mood_setzen(benutzer, schluessel=None, rolle=None, eigen=None):
    """Eltern wählen Mood und/oder Rolle (``None`` = unverändert; Prüfung gegen die Auswahl der
    Eltern, nie gegen die Kinder-Moods)."""
    if benutzer.rolle != Rolle.ELTERN:
        raise PermissionDenied("Nur Eltern wählen einen Eltern-Mood")
    felder = []
    if schluessel is not None:
        if schluessel:
            _eltern_mood_pruefen(schluessel)
        benutzer.mood = schluessel
        felder.append("mood")
    if rolle is not None:
        benutzer.wappen_rolle = rolle
        felder.append("wappen_rolle")
    if eigen is not None:
        benutzer.wappen_rolle_eigen = eigen.strip()
        felder.append("wappen_rolle_eigen")
    benutzer.full_clean(exclude=["password", "anzeigename"])
    benutzer.save(update_fields=felder)
    audit.protokollieren(
        "konten.eltern_mood_gesetzt", objekt=benutzer, details={"mood": benutzer.mood}
    )


def sprache_setzen(benutzer, sprache):
    """Eigene Sprache (``""`` = automatisch, sonst ein Code aus ``settings.LANGUAGES``)."""
    if sprache not in {""} | {code for code, _name in settings.LANGUAGES}:
        raise ValidationError(_("Unbekannte Sprache."))
    benutzer.sprache = sprache
    benutzer.save(update_fields=["sprache"])
    audit.protokollieren("konten.sprache_gesetzt", objekt=benutzer, details={"sprache": sprache})


def kind_umbenennen(kind, anzeigename):
    with transaction.atomic():
        kind.anzeigename = anzeigename
        kind.full_clean(exclude=["password"])
        kind.save(update_fields=["anzeigename"])
        audit.protokollieren("konten.kind_umbenannt", objekt=kind, kind=kind)


def _kurztext(text, maximum, feld):
    """Einfache Prüfung für Freitext von Kindern: Leerraum glätten, Länge, keine Steuerzeichen
    und keine spitzen Klammern (Ausgabe wird zusätzlich von den Templates maskiert)."""
    text = " ".join(str(text or "").split())
    if len(text) > maximum:
        raise ValidationError(
            _("%(feld)s: höchstens %(n)s Zeichen.") % {"feld": feld, "n": maximum}
        )
    if any(unicodedata.category(z).startswith("C") for z in text) or "<" in text or ">" in text:
        raise ValidationError(_("%(feld)s enthält ungültige Zeichen.") % {"feld": feld})
    return text


def kind_selbst_aendern(kind, anzeigename, spitzname):
    """Das Kind ändert seinen Namen (eindeutig, Groß-/Kleinschreibung egal) und Spitznamen."""
    anzeigename = " ".join(str(anzeigename or "").split())
    spitzname = _kurztext(spitzname, SPITZNAME_MAX, _("Spitzname"))
    if not anzeigename:
        raise ValidationError(_("Bitte einen Namen eingeben."))
    if Benutzer.objects.filter(anzeigename__iexact=anzeigename).exclude(pk=kind.pk).exists():
        raise ValidationError(_("Diesen Namen gibt es schon."))
    with transaction.atomic():
        geaendert = [
            feld
            for feld, neu in (("anzeigename", anzeigename), ("spitzname", spitzname))
            if getattr(kind, feld) != neu
        ]
        kind.anzeigename, kind.spitzname = anzeigename, spitzname
        kind.full_clean(exclude=["password"])
        kind.save(update_fields=["anzeigename", "spitzname"])
        if geaendert:
            audit.protokollieren(
                "konten.kind_profil_geaendert",
                akteur=kind,
                objekt=kind,
                kind=kind,
                details={"felder": geaendert},
            )


def kind_anlegen(anzeigename, pin, *, akzentfarben=None, reihenfolge=0):
    _pin_pruefen(pin)
    with transaction.atomic():
        benutzer = Benutzer(
            anzeigename=anzeigename,
            rolle=Rolle.KIND,
            reihenfolge=reihenfolge,
            akzentfarben=akzentfarben or [],
        )
        benutzer.set_unusable_password()
        benutzer.full_clean()
        benutzer.save()
        KindProfil.objects.create(benutzer=benutzer, pin_hash=make_password(str(pin)))
        audit.protokollieren("konten.kind_angelegt", objekt=benutzer, kind=benutzer)
    return benutzer


def pin_setzen(kind, pin, *, von=audit.AKTUELL):
    """Eltern setzen die PIN eines Kindes neu; eine bestehende Sperre wird aufgehoben."""
    _pin_pruefen(pin)
    with transaction.atomic():
        profil = KindProfil.objects.select_for_update().get(benutzer=kind)
        profil.pin_hash = make_password(str(pin))
        profil.save(update_fields=["pin_hash"])
        sperre.kind_zuruecksetzen(profil)
        audit.protokollieren("konten.pin_zurueckgesetzt", akteur=von, objekt=kind, kind=kind)


class PinGesperrt(ValidationError):
    """Zu viele Fehlversuche: Der alte Code wird bis zum Ende der Sperre nicht geprüft."""


def pin_aendern(kind, alte_pin, neue_pin, *, neue_pin2=None):
    """Das Kind ändert seinen Code. Der alte Code ist Pflicht; Fehlversuche zählen wie bei der
    Anmeldung (Zähler und Sperre je Kind, ``sperre``). Der Code selbst wird nie protokolliert."""
    if neue_pin2 is not None and neue_pin != neue_pin2:
        raise ValidationError(_("Die beiden neuen Codes sind verschieden."))
    _pin_pruefen(neue_pin)
    jetzt = zeit.jetzt()
    with transaction.atomic():
        profil = KindProfil.objects.select_for_update().get(benutzer=kind)
        if sperre.kind_gesperrt_bis(profil, jetzt):
            raise PinGesperrt(_("Zu viele Versuche. Der Code ist kurz gesperrt."))
        if PIN_MUSTER.match(str(alte_pin)) and check_password(str(alte_pin), profil.pin_hash):
            profil.pin_hash = make_password(str(neue_pin))
            profil.save(update_fields=["pin_hash"])
            sperre.kind_zuruecksetzen(profil)
            audit.protokollieren("konten.pin_geaendert", akteur=kind, objekt=kind, kind=kind)
            return
        gesperrt = sperre.kind_fehlversuch_erfassen(profil, jetzt)
        audit.protokollieren(
            "konten.pin_aenderung_abgelehnt",
            akteur=kind,
            objekt=kind,
            kind=kind,
            details={"gesperrt": bool(gesperrt)},
        )
    # Zähler und Audit sind gespeichert; erst jetzt den Fehler melden
    if gesperrt:
        raise PinGesperrt(_("Zu viele Versuche. Der Code ist kurz gesperrt."))
    raise ValidationError(_("Der alte Code stimmt nicht."))


def kind_entsperren(kind, *, von=audit.AKTUELL):
    with transaction.atomic():
        profil = KindProfil.objects.select_for_update().get(benutzer=kind)
        sperre.kind_zuruecksetzen(profil)
        audit.protokollieren("konten.kind_entsperrt", akteur=von, objekt=kind, kind=kind)


def akzentfarben_setzen(kind, farben, *, von=audit.AKTUELL):
    kind.akzentfarben = list(farben)
    kind.full_clean(exclude=["password"])
    kind.save(update_fields=["akzentfarben"])
    audit.protokollieren(
        "konten.akzentfarben_geaendert",
        akteur=von,
        objekt=kind,
        kind=kind,
        details={"farben": kind.akzentfarben},
    )


def eltern_passwort_setzen(passwort, *, von=audit.AKTUELL):
    """Setzt das gemeinsame Eltern-Passwort (Argon2). Das Passwort selbst wird nie
    protokolliert."""
    if len(passwort) < PASSWORT_MINDESTLAENGE:
        raise ValidationError(
            _("Das Passwort braucht mindestens %(n)s Zeichen.") % {"n": PASSWORT_MINDESTLAENGE}
        )
    akteur = audit.aktueller_akteur() if von is audit.AKTUELL else von
    with transaction.atomic():
        ElternZugang.objects.update_or_create(
            pk=1,
            defaults={
                "passwort_hash": make_password(passwort),
                "geaendert_am": timezone.now(),
                "geaendert_von": akteur if getattr(akteur, "pk", None) else None,
            },
        )
        audit.protokollieren("konten.passwort_geaendert", akteur=akteur)


def benutzer_deaktivieren(benutzer, *, von=audit.AKTUELL):
    """Benutzer werden deaktiviert, nie gelöscht. Offene Sitzungen enden sofort."""
    with transaction.atomic():
        benutzer.aktiv = False
        benutzer.save(update_fields=["aktiv"])
        audit.protokollieren("konten.deaktiviert", akteur=von, objekt=benutzer)


def geraet_registrieren(bezeichnung, typ, *, registriert_von):
    if typ not in GeraeteTyp.values:
        raise ValidationError(_("Unbekannter Gerätetyp."))
    if registriert_von.rolle != Rolle.ELTERN:
        raise ValidationError(_("Nur Eltern registrieren Geräte."))
    with transaction.atomic():
        geraet = Geraet(bezeichnung=bezeichnung.strip(), typ=typ, registriert_von=registriert_von)
        geraet.full_clean()
        geraet.save()
        audit.protokollieren(
            "konten.geraet_registriert",
            akteur=registriert_von,
            objekt=geraet,
            details={"typ": typ, "bezeichnung": geraet.bezeichnung},
        )
    return geraet


def geraet_widerrufen(geraet, *, von=audit.AKTUELL):
    with transaction.atomic():
        geraet.aktiv = False
        geraet.save(update_fields=["aktiv"])
        audit.protokollieren("konten.geraet_widerrufen", akteur=von, objekt=geraet)


def alte_versuche_loeschen(jetzt=None):
    """Aufbewahrung 30 Tage (DATA_MODEL 2.6). Gibt die Zahl gelöschter Versuche zurück."""
    grenze = (jetzt or timezone.now()) - VERSUCHE_AUFBEWAHRUNG
    return AnmeldeVersuch.objects.filter(zeit__lt=grenze).delete()[0]


def abgelaufene_sitzungen_loeschen():
    SessionStore.clear_expired()


# --- Moods -------------------------------------------------------------------------------------


def _eltern(von):
    akteur = audit.aktueller_akteur() if von is audit.AKTUELL else von
    if akteur is not None and getattr(akteur, "rolle", None) != Rolle.ELTERN:
        raise PermissionDenied("Nur Eltern verwalten Moods")
    return akteur


def mood_setzen(kind, schluessel):
    """Das Kind wählt seinen Mood (``""`` = kein Mood). Nur Moods aus der aktuellen Auswahl der
    Kinder; Eltern-Moods sind nie wählbar."""
    if kind.rolle != Rolle.KIND:
        raise PermissionDenied("Nur Kinder wählen einen Kinder-Mood")
    if schluessel and schluessel not in {
        s for s, _text, _gruppe in selectors.mood_auswahl(moods.KIND)
    }:
        raise ValidationError(_("Diesen Mood gibt es nicht."))
    kind.mood = schluessel
    kind.save(update_fields=["mood"])
    audit.protokollieren(
        "konten.mood_gesetzt", akteur=kind, objekt=kind, kind=kind, details={"mood": schluessel}
    )


def _mood_text_neu(text, zielgruppe=moods.KIND):
    """Geprüfter Text für einen neuen Mood der Zielgruppe; ``ValidationError``, wenn es ihn
    schon gibt."""
    text = _kurztext(text, moods.TEXT_MAX, _("Mood"))
    if not text:
        raise ValidationError(_("Bitte einen Text eingeben."))
    vorhandene = {m.text.lower() for m in map(_uebersetzt, moods.katalog(zielgruppe))}
    vorhandene |= {
        t.lower()
        for t in MoodEigen.objects.filter(zielgruppe=zielgruppe).values_list("text", flat=True)
    }
    if text.lower() in vorhandene:
        raise ValidationError(_("Diesen Mood gibt es schon."))
    return text


def _uebersetzt(mood):
    return moods.Mood(mood.schluessel, mood.emoji, str(mood.text), mood.gruppe, str(mood.spruch))


def mood_vorschlagen(kind, text):
    """Das Kind schlägt einen neuen Mood vor (höchstens 3 offene Vorschläge je Kind)."""
    if kind.rolle != Rolle.KIND:
        raise PermissionDenied("Nur Kinder schlagen Moods vor")
    text = _mood_text_neu(text)
    with transaction.atomic():
        offen = MoodVorschlag.objects.filter(kind=kind, status=VorschlagStatus.OFFEN)
        if offen.count() >= MOOD_VORSCHLAEGE_OFFEN_MAX:
            raise ValidationError(
                _("Du hast schon %(n)s offene Vorschläge. Warte, bis die Eltern entschieden haben.")
                % {"n": MOOD_VORSCHLAEGE_OFFEN_MAX}
            )
        if offen.filter(text__iexact=text).exists():
            raise ValidationError(_("Das hast du schon vorgeschlagen."))
        vorschlag = MoodVorschlag.objects.create(kind=kind, text=text)
        audit.protokollieren(
            "konten.mood_vorgeschlagen",
            akteur=kind,
            objekt=vorschlag,
            kind=kind,
            details={"text": text},
        )
    return vorschlag


def mood_vorschlag_entscheiden(vorschlag, zulassen, *, von=audit.AKTUELL):
    """Eltern lassen einen offenen Vorschlag zu (gilt dann für alle Kinder) oder lehnen ihn ab."""
    akteur = _eltern(von)
    with transaction.atomic():
        vorschlag = MoodVorschlag.objects.select_for_update().get(pk=vorschlag.pk)
        if vorschlag.status != VorschlagStatus.OFFEN:
            raise ValidationError(_("Dieser Vorschlag ist schon entschieden."))
        if zulassen:
            eigen = MoodEigen.objects.filter(
                zielgruppe=moods.KIND, text__iexact=vorschlag.text
            ).first()
            if eigen is None:
                MoodEigen.objects.create(zielgruppe=moods.KIND, text=vorschlag.text)
            elif not eigen.aktiv:
                eigen.aktiv = True
                eigen.save(update_fields=["aktiv"])
        vorschlag.status = VorschlagStatus.ZUGELASSEN if zulassen else VorschlagStatus.ABGELEHNT
        vorschlag.entschieden_von = akteur if isinstance(akteur, Benutzer) else None
        vorschlag.entschieden_am = zeit.jetzt()
        vorschlag.save(update_fields=["status", "entschieden_von", "entschieden_am"])
        audit.protokollieren(
            "konten.mood_vorschlag_entschieden",
            akteur=akteur,
            objekt=vorschlag,
            kind=vorschlag.kind,
            details={"status": vorschlag.status, "text": vorschlag.text},
        )
    return vorschlag


def mood_eigen_anlegen(text, *, zielgruppe=moods.KIND, von=audit.AKTUELL):
    akteur = _eltern(von)
    if zielgruppe not in moods.ZIELGRUPPEN:
        raise ValidationError(_("Diesen Mood gibt es nicht."))
    text = _mood_text_neu(text, zielgruppe)
    with transaction.atomic():
        eigen = MoodEigen.objects.create(zielgruppe=zielgruppe, text=text)
        audit.protokollieren(
            "konten.mood_angelegt",
            akteur=akteur,
            objekt=eigen,
            details={"text": text, "zielgruppe": zielgruppe},
        )
    return eigen


def mood_eigen_entfernen(eigen, *, von=audit.AKTUELL):
    """Nimmt einen eigenen Mood aus der Auswahl (wer ihn hat, zeigt ihn nicht mehr)."""
    akteur = _eltern(von)
    with transaction.atomic():
        eigen.aktiv = False
        eigen.save(update_fields=["aktiv"])
        audit.protokollieren(
            "konten.mood_entfernt", akteur=akteur, objekt=eigen, details={"text": eigen.text}
        )


def mood_katalog_ausblenden(schluessel, ausblenden, *, von=audit.AKTUELL):
    """Blendet einen Katalog-Mood aus (``ausblenden=True``) oder wieder ein."""
    akteur = _eltern(von)
    if schluessel not in moods.NACH_SCHLUESSEL and schluessel not in moods.NACH_SCHLUESSEL_ELTERN:
        raise ValidationError(_("Diesen Mood gibt es nicht."))
    with transaction.atomic():
        if ausblenden:
            MoodAusgeblendet.objects.get_or_create(schluessel=schluessel)
        else:
            MoodAusgeblendet.objects.filter(schluessel=schluessel).delete()
        audit.protokollieren(
            "konten.mood_katalog_geaendert",
            akteur=akteur,
            details={"mood": schluessel, "ausgeblendet": bool(ausblenden)},
        )
