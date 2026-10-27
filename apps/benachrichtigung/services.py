"""Schreibende Schnittstelle von benachrichtigung."""

import re
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.kern import audit, einstellungen, zeit
from apps.kern.einstellungen import Typ
from apps.konten.models import Rolle

from . import crypto, mail, registry
from .models import (
    Benachrichtigung,
    BenachrichtigungsProfil,
    Praeferenz,
    Ruhezeit,
    SmtpKonto,
    SmtpSicherheit,
    Zustellung,
)

# --- Einstellungen ---------------------------------------------------------------------------


_HOST_MUSTER = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


def _hosts_pruefen(hosts):
    for host in hosts:
        h = str(host).strip().lower()
        if not _HOST_MUSTER.match(h) or h.replace(".", "").isdigit():
            raise ValidationError(
                _("'%(host)s' ist keine gültige Host-Endung (z. B. push.apple.com)")
                % {"host": host}
            )


def einstellungen_definieren():
    """Einstellungen des Moduls (Startwerte per Datenmigration 0002)."""
    einstellungen.definieren(
        "benachrichtigung.push_ttl_standard_sekunden",
        Typ.GANZZAHL,
        _("Standard-Lebensdauer einer Push-Nachricht"),
        einheit="s",
        minimum=60,
        maximum=2419200,
    )
    einstellungen.definieren(
        "benachrichtigung.zustellung_max_versuche",
        Typ.GANZZAHL,
        _("Max. Versuche je Zustellung"),
        beschreibung=_("Danach gilt die Zustellung als aufgegeben."),
        minimum=1,
        maximum=20,
    )
    einstellungen.definieren(
        "benachrichtigung.aufbewahrung_tage",
        Typ.GANZZAHL,
        _("Aufbewahrung gelesener Benachrichtigungen"),
        einheit=_("Tage"),
        minimum=7,
        maximum=3650,
    )
    einstellungen.definieren(
        "benachrichtigung.aufbewahrung_ungelesen_tage",
        Typ.GANZZAHL,
        _("Aufbewahrung ungelesener Benachrichtigungen"),
        beschreibung=_("Auch ungelesene Benachrichtigungen werden danach gelöscht."),
        einheit=_("Tage"),
        minimum=30,
        maximum=3650,
    )
    einstellungen.definieren(
        "benachrichtigung.zustellung_aufbewahrung_tage",
        Typ.GANZZAHL,
        _("Aufbewahrung der Zustell-Protokolle"),
        beschreibung=_(
            "Protokoll je Kanal (gesendet, stumm, Fehler) wird danach gelöscht; die "
            "Benachrichtigung selbst bleibt nach ihrer eigenen Frist."
        ),
        einheit=_("Tage"),
        minimum=7,
        maximum=3650,
    )
    einstellungen.definieren(
        "benachrichtigung.push_erlaubte_hosts",
        Typ.LISTE,
        _("Erlaubte Push-Dienste (Host-Endungen)"),
        beschreibung=_(
            "Web-Push-Endpunkte werden nur an diese Hosts gesendet (Endung auf "
            "Label-Grenze, z. B. push.apple.com). IP-Adressen und nicht öffentliche Ziele sind "
            "immer gesperrt."
        ),
        element_typ=Typ.TEXT,
        validatoren=(_hosts_pruefen,),
    )


# --- Präferenzen, Ruhezeit, Profil -----------------------------------------------------------


def _kanal_pruefen(kanal_slug):
    registry.kanal(kanal_slug)  # unbekannt -> UnbekannterEintrag


def praeferenz_setzen(benutzer, typ_slug, kanal_slug, aktiv, *, von=audit.AKTUELL):
    """Schaltet einen Kanal für einen Ereignistyp an/aus (Eltern und Kinder; Kinder setzen die
    Eltern)."""
    from apps.ereignisse import selectors as ereignis_selectors

    from .router import kanaele_synchronisieren

    _kanal_pruefen(kanal_slug)
    typ = ereignis_selectors.ereignistyp(typ_slug)
    with transaction.atomic():
        kanaele_synchronisieren()
        zeile, _ = Praeferenz.objects.update_or_create(
            benutzer=benutzer,
            ereignistyp=typ,
            kanal_id=kanal_slug,
            defaults={"aktiv": bool(aktiv)},
        )
        audit.protokollieren(
            "benachrichtigung.praeferenz_gesetzt",
            akteur=von,
            kind=benutzer if benutzer.rolle == Rolle.KIND else None,
            details={
                "benutzer": benutzer.anzeigename,
                "ereignistyp": typ_slug,
                "kanal": kanal_slug,
                "aktiv": bool(aktiv),
            },
        )
    return zeile


def ruhezeit_setzen(
    benutzer,
    *,
    von,
    bis,
    wochentage=127,
    gilt_fuer_email=False,
    aktiv=True,
    akteur=audit.AKTUELL,
):
    """Setzt die Ruhezeit eines Elternteils (ein Fenster; das Modell erlaubt mehrere)."""
    if benutzer.rolle != Rolle.ELTERN:
        raise ValueError("Ruhezeiten gibt es nur für Eltern")
    if not (isinstance(wochentage, int) and 1 <= wochentage <= 127):
        raise ValueError("wochentage: Bitmaske 1–127 erwartet (Mo=1 … So=64)")
    with transaction.atomic():
        zeile = Ruhezeit.objects.filter(benutzer=benutzer).order_by("id").first()
        werte = {
            "von": von,
            "bis": bis,
            "wochentage": wochentage,
            "gilt_fuer_email": bool(gilt_fuer_email),
            "aktiv": bool(aktiv),
        }
        if zeile is None:
            zeile = Ruhezeit.objects.create(benutzer=benutzer, **werte)
        else:
            for name, wert in werte.items():
                setattr(zeile, name, wert)
            zeile.save()
        audit.protokollieren(
            "benachrichtigung.ruhezeit_gesetzt",
            akteur=akteur,
            objekt=zeile,
            details={
                "von": f"{von:%H:%M}",
                "bis": f"{bis:%H:%M}",
                "wochentage": wochentage,
                "email": bool(gilt_fuer_email),
                "aktiv": bool(aktiv),
            },
        )
    return zeile


def ruhezeit_entfernen(benutzer, *, akteur=audit.AKTUELL):
    with transaction.atomic():
        anzahl, _ = Ruhezeit.objects.filter(benutzer=benutzer).delete()
        if anzahl:
            audit.protokollieren(
                "benachrichtigung.ruhezeit_entfernt",
                akteur=akteur,
                details={"benutzer": benutzer.anzeigename},
            )
    return anzahl


def mail_profil_setzen(benutzer, nur_entscheidungen, *, akteur=audit.AKTUELL):
    """Profil "Mail nur bei Entscheidungen" (K13) für einen Elternteil."""
    if benutzer.rolle != Rolle.ELTERN:
        raise ValueError("Das Profil gibt es nur für Eltern")
    with transaction.atomic():
        BenachrichtigungsProfil.objects.update_or_create(
            benutzer=benutzer, defaults={"mail_nur_entscheidungen": bool(nur_entscheidungen)}
        )
        audit.protokollieren(
            "benachrichtigung.mail_profil_gesetzt",
            akteur=akteur,
            details={
                "benutzer": benutzer.anzeigename,
                "nur_entscheidungen": bool(nur_entscheidungen),
            },
        )


# --- Dashboard-Liste -------------------------------------------------------------------------


def als_gelesen(benutzer, benachrichtigung_id):
    return Benachrichtigung.objects.filter(
        pk=benachrichtigung_id, empfaenger=benutzer, gelesen_am__isnull=True
    ).update(gelesen_am=zeit.jetzt())


def alle_als_gelesen(benutzer):
    return Benachrichtigung.objects.filter(empfaenger=benutzer, gelesen_am__isnull=True).update(
        gelesen_am=zeit.jetzt()
    )


def popups_als_gesehen(popups):
    from .models import Popup

    return Popup.objects.filter(pk__in=[p.pk for p in popups], gesehen_am__isnull=True).update(
        gesehen_am=zeit.jetzt()
    )


def aufraeumen(jetzt=None):
    """Löscht gelesene Benachrichtigungen (samt Zustellungen/Pop-ups) nach der Aufbewahrungszeit."""
    return aufbewahrung(jetzt)["benachrichtigungen"]


def aufbewahrung(jetzt=None) -> dict:
    """Job ``benachrichtigungen_aufraeumen`` (B-15, Review AP31), idempotent, alle Fristen sind
    Einstellungen:

    - gelesene Benachrichtigungen nach ``benachrichtigung.aufbewahrung_tage``,
      ungelesene nach ``benachrichtigung.aufbewahrung_ungelesen_tage`` (samt Pop-ups/Zustellungen),
    - Zustellungen nach ``benachrichtigung.zustellung_aufbewahrung_tage``,
    - Ereignisse nach ``ereignisse.aufbewahrung_tage`` (nur verarbeitet/ok und nicht mehr von einer
      Benachrichtigung referenziert),
    - Job-Läufe nach ``allgemein.joblauf_aufbewahrung_tage``.

    Ledger (``punkte``) und Audit-Log werden nie gelöscht."""
    from apps.ereignisse import services as ereignisse
    from apps.kern import jobs

    jetzt = jetzt or zeit.jetzt()
    w = einstellungen.werte(
        "benachrichtigung.aufbewahrung_tage",
        "benachrichtigung.aufbewahrung_ungelesen_tage",
        "benachrichtigung.zustellung_aufbewahrung_tage",
        "allgemein.joblauf_aufbewahrung_tage",
    )

    def vor(schluessel):
        return jetzt - timedelta(days=w[schluessel])

    gelesen, _ = Benachrichtigung.objects.filter(
        gelesen_am__isnull=False, erstellt_am__lt=vor("benachrichtigung.aufbewahrung_tage")
    ).delete()
    ungelesen, _ = Benachrichtigung.objects.filter(
        gelesen_am__isnull=True,
        erstellt_am__lt=vor("benachrichtigung.aufbewahrung_ungelesen_tage"),
    ).delete()
    # Nach der Frist (mind. 7 Tage) sind alle Wiederholungen längst vorbei (Backoff max. 1 h)
    zustellungen, _ = Zustellung.objects.filter(
        benachrichtigung__erstellt_am__lt=vor("benachrichtigung.zustellung_aufbewahrung_tage")
    ).delete()
    ereignis_anzahl = ereignisse.aufraeumen(
        behalten=Benachrichtigung.objects.values("ereignis_id"), jetzt=jetzt
    )
    laeufe = jobs.laeufe_aufraeumen(w["allgemein.joblauf_aufbewahrung_tage"], jetzt=jetzt)
    return {
        "benachrichtigungen": gelesen + ungelesen,
        "zustellungen": zustellungen,
        "ereignisse": ereignis_anzahl,
        "job_laeufe": laeufe,
    }


# --- SMTP und Testmail -----------------------------------------------------------------------


def _smtp_pruefen(host, port, sicherheit, benutzername, absender):
    if not host.strip() or not benutzername.strip():
        raise ValidationError(_("Server und Benutzername sind Pflicht"))
    if not (isinstance(port, int) and 1 <= port <= 65535):
        raise ValidationError(_("Port muss zwischen 1 und 65535 liegen"))
    if sicherheit not in SmtpSicherheit.values:
        raise ValidationError(_("Unbekannte Verschlüsselung"))
    validate_email(absender)


def smtp_speichern(
    *, host, port, sicherheit, benutzername, absender, passwort=None, von=audit.AKTUELL
):
    """Speichert das SMTP-Konto. ``passwort=None`` behält das gespeicherte Passwort (Pflicht
    beim ersten Speichern). Das Passwort wird mit Fernet verschlüsselt; Audit-Log und Logs
    enthalten es nie."""
    _smtp_pruefen(host, port, sicherheit, benutzername, absender)
    with transaction.atomic():
        vorhanden = SmtpKonto.objects.first()
        if passwort:
            token = crypto.verschluesseln(passwort)
        elif vorhanden is not None:
            token = vorhanden.passwort_verschluesselt
        else:
            raise ValidationError(_("Passwort fehlt"))
        konto, _neu = SmtpKonto.objects.update_or_create(
            pk=1,
            defaults={
                "host": host.strip(),
                "port": port,
                "sicherheit": sicherheit,
                "benutzername": benutzername.strip(),
                "passwort_verschluesselt": token,
                "absender": absender,
                # eine Änderung der Zugangsdaten macht den letzten Test ungültig
                "zuletzt_getestet_am": None,
            },
        )
        audit.protokollieren(
            "benachrichtigung.smtp_gespeichert",
            akteur=von,
            objekt=konto,
            details={
                "host": konto.host,
                "port": port,
                "sicherheit": sicherheit,
                "benutzername": konto.benutzername,
                "absender": absender,
                "zugang_neu": bool(passwort),
            },
        )
    return konto


@dataclass(frozen=True)
class TestmailErgebnis:
    ok: bool
    meldung: str


def testmail_senden(empfaenger, *, daten=None, von=audit.AKTUELL):
    """Sendet eine Testmail (Einrichtungs-Assistent, Einstellungen).

    ``daten``: ``mail.SmtpDaten`` zum Testen ungespeicherter Eingaben; ohne Angabe gilt das
    gespeicherte Konto (dann wird ``zuletzt_getestet_am`` gesetzt). Wirft nie die Mail-Ausnahme:
    das Ergebnis trägt eine deutsche, passwortfreie Meldung.
    """
    try:
        validate_email(empfaenger)
    except ValidationError:
        return TestmailErgebnis(False, gettext("Die E-Mail-Adresse ist ungültig."))
    konto = None
    if daten is None:
        konto = SmtpKonto.objects.first()
        if konto is None:
            return TestmailErgebnis(False, gettext("Der Postausgang ist noch nicht eingerichtet."))
        try:
            daten = mail.daten_aus_konto(konto)
        except crypto.SchluesselFehler:
            return TestmailErgebnis(
                False,
                gettext("Das gespeicherte Passwort passt nicht zum Schlüssel. Bitte neu eingeben."),
            )
    try:
        mail.senden(
            daten,
            empfaenger,
            "Nestwerk: " + gettext("Testnachricht"),
            gettext(
                "Das ist eine Testnachricht von Nestwerk.\n\nWenn du sie liest, funktioniert der "
                "E-Mail-Versand."
            ),
        )
    except Exception as exc:
        grund = mail.bereinigen(f"{type(exc).__name__}: {exc}", daten)
        audit.protokollieren(
            "benachrichtigung.testmail_fehlgeschlagen",
            akteur=von,
            details={"host": daten.host, "grund": grund[:300]},
        )
        return TestmailErgebnis(
            False, gettext("Der Versand hat nicht geklappt (%(grund)s).") % {"grund": grund[:200]}
        )
    if konto is not None:
        SmtpKonto.objects.filter(pk=1).update(zuletzt_getestet_am=zeit.jetzt())
    audit.protokollieren(
        "benachrichtigung.testmail_gesendet", akteur=von, details={"host": daten.host}
    )
    return TestmailErgebnis(
        True, gettext("Testnachricht an %(empfaenger)s gesendet.") % {"empfaenger": empfaenger}
    )
