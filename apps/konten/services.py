"""Schreibende Operationen von konten. Alle Änderungen laufen hier durch und werden
protokolliert (nie mit PIN oder Passwort). ``von`` ist der handelnde Elternteil; ohne Angabe
gilt der angemeldete Benutzer der Anfrage (``kern.audit``-Kontext)."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.kern import audit

from . import sperre
from . import wappen as wappen_katalog
from .backends import PIN_MUSTER
from .models import (
    AnmeldeVersuch,
    Benutzer,
    ElternProfil,
    ElternZugang,
    Geraet,
    GeraeteTyp,
    KindProfil,
    Rolle,
)

PASSWORT_MINDESTLAENGE = 8
VERSUCHE_AUFBEWAHRUNG = timedelta(days=30)


def _pin_pruefen(pin):
    if not PIN_MUSTER.match(str(pin)):
        raise ValidationError(_("Die PIN besteht aus genau 4 Ziffern."))


def _freies_wappen(ausser=None):
    belegt = Benutzer.objects.filter(rolle=Rolle.ELTERN, aktiv=True).exclude(wappen="")
    if ausser is not None:
        belegt = belegt.exclude(pk=ausser.pk)
    return wappen_katalog.zufaellig(belegt.values_list("wappen", flat=True))


def eltern_anlegen(
    anzeigename,
    *,
    rolle_label="andere",
    email="",
    reihenfolge=0,
    wappen="",
    wappen_rolle="",
    wappen_rolle_eigen="",
):
    """Ohne ``wappen`` wird zufällig eines vergeben (möglichst anders als bei den anderen Eltern)."""
    with transaction.atomic():
        benutzer = Benutzer(
            anzeigename=anzeigename,
            rolle=Rolle.ELTERN,
            reihenfolge=reihenfolge,
            wappen=wappen or _freies_wappen(),
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
    wappen=None,
    wappen_rolle=None,
    wappen_rolle_eigen=None,
):
    """Ändert Name, Rolle (Mama/Papa/andere), E-Mail und optional das Wappen eines Elternteils."""
    with transaction.atomic():
        benutzer.anzeigename = anzeigename
        felder = ["anzeigename"]
        if wappen is not None or not benutzer.wappen:
            benutzer.wappen = wappen or _freies_wappen(ausser=benutzer)
            felder.append("wappen")
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


def wappen_setzen(benutzer, schluessel=None, rolle=None, eigen=None):
    """Eltern wählen Wappen und/oder Rolle (``None`` = unverändert; Katalog-Prüfung)."""
    felder = []
    if schluessel is not None:
        if schluessel not in wappen_katalog.NACH_SCHLUESSEL:
            raise ValidationError(_("Unbekanntes Wappen."))
        benutzer.wappen = schluessel
        felder.append("wappen")
    if rolle is not None:
        benutzer.wappen_rolle = rolle
        felder.append("wappen_rolle")
    if eigen is not None:
        benutzer.wappen_rolle_eigen = eigen.strip()
        felder.append("wappen_rolle_eigen")
    benutzer.full_clean(exclude=["password", "anzeigename"])
    benutzer.save(update_fields=felder)
    audit.protokollieren(
        "konten.wappen_gesetzt", objekt=benutzer, details={"wappen": benutzer.wappen}
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
