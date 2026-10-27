"""Schreibende Operationen des Assistenten. Jeder Schritt läuft in einer Transaktion und
schreibt nur über die Services der anderen Apps. Passwörter und PINs werden nie protokolliert
und nie in der Session abgelegt: sie gehen direkt in den Hash (konten) bzw. in die
Verschlüsselung (benachrichtigung)."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _

from apps.benachrichtigung import selectors as mail_selectors
from apps.benachrichtigung import services as mail_services
from apps.kern import audit, einstellungen
from apps.konten import akzent, wappen
from apps.konten import selectors as konten_selectors
from apps.konten import services as konten_services

from . import zustand
from .einstellungen import LETZTER_SCHRITT


class SchrittFehler(Exception):
    """Fachlicher Fehler eines Schritts (deutsche Meldungen, für das Formular)."""

    def __init__(self, meldungen):
        self.meldungen = list(meldungen)
        super().__init__("; ".join(self.meldungen))


def _meldungen(exc):
    return exc.messages if isinstance(exc, ValidationError) else [str(exc)]


def _setzen(schluessel, wert):
    return einstellungen.setzen(schluessel, wert, akteur=None)


def _schritt_abschliessen(nr):
    """Gibt den nächsten Schritt frei und vermerkt den Zwischenstand."""
    if nr + 1 > zustand.freigegebener_schritt():
        _setzen("einrichtung.schritt", min(nr + 1, LETZTER_SCHRITT))
    audit.protokollieren("einrichtung.schritt_gespeichert", akteur=None, details={"schritt": nr})


# --- Schritt 1: Name ---------------------------------------------------------------------------


def app_name_speichern(name):
    with transaction.atomic():
        _setzen("allgemein.anzeigename", name)
        _setzen("allgemein.sprache", (translation.get_language() or "de")[:2])
        _schritt_abschliessen(1)


def app_name():
    try:
        return einstellungen.wert("allgemein.anzeigename")
    except einstellungen.EinstellungFehlt:
        return "Nestwerk"


# --- Schritt 2: Eltern -------------------------------------------------------------------------


def eltern_speichern(daten):
    """``daten``: bereinigte ``ElternForm``-Werte. Das Passwort ist optional, wenn schon eins
    gesetzt ist."""
    vorhanden = list(konten_selectors.aktive_eltern())
    try:
        with transaction.atomic():
            for i in (1, 2):
                name = daten[f"eltern{i}_name"]
                rolle = daten[f"eltern{i}_rolle"]
                email = daten[f"eltern{i}_email"]
                wappen_wahl = daten.get(f"eltern{i}_wappen") or ""
                if i <= len(vorhanden):
                    konten_services.eltern_aendern(
                        vorhanden[i - 1],
                        name,
                        rolle_label=rolle,
                        email=email,
                        wappen=wappen_wahl or None,
                        wappen_rolle=daten.get(f"eltern{i}_wappen_rolle") or "",
                        wappen_rolle_eigen=daten.get(f"eltern{i}_wappen_rolle_eigen") or "",
                    )
                else:
                    konten_services.eltern_anlegen(
                        name,
                        rolle_label=rolle,
                        email=email,
                        reihenfolge=i,
                        wappen=wappen_wahl,
                        wappen_rolle=daten.get(f"eltern{i}_wappen_rolle") or "",
                        wappen_rolle_eigen=daten.get(f"eltern{i}_wappen_rolle_eigen") or "",
                    )
            if daten.get("passwort"):
                konten_services.eltern_passwort_setzen(daten["passwort"], von=None)
            _schritt_abschliessen(2)
    except ValidationError as exc:
        raise SchrittFehler(_meldungen(exc)) from exc


def eltern_werte():
    """Vorbelegung des Formulars aus der DB (ohne Passwort)."""
    werte = {}
    for i, benutzer in enumerate(konten_selectors.aktive_eltern()[:2], start=1):
        werte[f"eltern{i}_name"] = benutzer.anzeigename
        werte[f"eltern{i}_rolle"] = benutzer.elternprofil.rolle_label
        werte[f"eltern{i}_email"] = benutzer.elternprofil.email
        werte[f"eltern{i}_wappen"] = benutzer.wappen
        werte[f"eltern{i}_wappen_rolle"] = benutzer.wappen_rolle
        werte[f"eltern{i}_wappen_rolle_eigen"] = benutzer.wappen_rolle_eigen
    werte.setdefault("eltern1_rolle", "mama")
    werte.setdefault("eltern2_rolle", "papa")
    # Vorbelegung: zufällig, die beiden Eltern möglichst verschieden
    for i in (1, 2):
        if not werte.get(f"eltern{i}_wappen"):
            belegt = [v for k, v in werte.items() if k.endswith("_wappen") and v]
            werte[f"eltern{i}_wappen"] = wappen.zufaellig(belegt)
    return werte


def passwort_gesetzt():
    return konten_selectors.eltern_passwort_gesetzt()


# --- Schritt 3: Kinder -------------------------------------------------------------------------


@dataclass
class KindZeile:
    nr: int
    kind_id: str
    name: str
    pin: str
    pin2: str
    farbe: str
    fehler: dict

    @property
    def name_feld(self):
        return f"kind-{self.nr}-name"

    @property
    def pin_feld(self):
        return f"kind-{self.nr}-pin"

    @property
    def pin2_feld(self):
        return f"kind-{self.nr}-pin2"

    @property
    def pin_hilfe(self):
        return _("Leer lassen, um die PIN zu behalten.") if self.kind_id else ""


def kinder_zeilen_lesen(daten, anzahl):
    zeilen = []
    for i in range(anzahl):
        zeilen.append(
            KindZeile(
                nr=i,
                kind_id=daten.get(f"kind-{i}-id", "").strip(),
                name=daten.get(f"kind-{i}-name", "").strip(),
                pin=daten.get(f"kind-{i}-pin", ""),
                pin2=daten.get(f"kind-{i}-pin2", ""),
                farbe=daten.get(f"kind-{i}-farbe", "").strip(),
                fehler={},
            )
        )
    return zeilen


def kinder_zeilen_aus_db():
    return [
        KindZeile(
            nr=i,
            kind_id=str(kind.pk),
            name=kind.anzeigename,
            pin="",
            pin2="",
            farbe=_farbname(kind),
            fehler={},
        )
        for i, kind in enumerate(konten_selectors.aktive_kinder())
    ]


def _farbname(kind):
    for farbe in kind.akzentfarben or []:
        name = akzent.hex_zu_name(farbe)
        if name:
            return name
    return ""


def kinder_pruefen(zeilen, eltern_namen=()):
    """Setzt Zeilenfehler. Leere Zeilen (ohne Name und PIN) zählen nicht. Gibt die gültigen,
    nicht leeren Zeilen zurück und eine Liste allgemeiner Fehler."""
    allgemein = []
    aktive = []
    gesehen = {n.lower() for n in eltern_namen}
    bekannte = {str(k.pk): k for k in konten_selectors.aktive_kinder()}
    for z in zeilen:
        if not z.kind_id and not z.name and not z.pin and not z.pin2:
            continue
        if not z.name:
            z.fehler["name"] = _("Bitte einen Namen eingeben.")
        elif len(z.name) > 40:
            z.fehler["name"] = _("Höchstens 40 Zeichen.")
        elif z.name.lower() in gesehen:
            z.fehler["name"] = _("Dieser Name ist schon vergeben.")
        else:
            gesehen.add(z.name.lower())
        bestehend = z.kind_id in bekannte
        if z.kind_id and not bestehend:
            z.fehler["name"] = _("Dieses Kind gibt es nicht mehr. Bitte die Seite neu laden.")
        if z.pin or z.pin2 or not bestehend:
            if not (z.pin.isascii() and z.pin.isdigit() and len(z.pin) == 4):
                z.fehler["pin"] = _("Die PIN besteht aus genau 4 Ziffern.")
            elif z.pin != z.pin2:
                z.fehler["pin2"] = _("Die beiden PINs sind nicht gleich.")
        if z.farbe and z.farbe not in akzent.PALETTE:
            z.fehler["farbe"] = _("Unbekannte Farbe.")
        aktive.append(z)
    if not aktive:
        allgemein.append(_("Bitte mindestens ein Kind eintragen."))
    return aktive, allgemein


def kinder_speichern(zeilen):
    """``zeilen``: geprüfte, nicht leere ``KindZeile``-Objekte."""
    bekannte = {str(k.pk): k for k in konten_selectors.aktive_kinder()}
    try:
        with transaction.atomic():
            for nr, z in enumerate(zeilen, start=1):
                hex_farbe = [akzent.name_zu_hex(z.farbe)] if z.farbe else []
                kind = bekannte.get(z.kind_id)
                if kind is None:
                    konten_services.kind_anlegen(
                        z.name, z.pin, akzentfarben=hex_farbe, reihenfolge=nr
                    )
                    continue
                if kind.anzeigename != z.name:
                    konten_services.kind_umbenennen(kind, z.name)
                if z.pin:
                    konten_services.pin_setzen(kind, z.pin, von=None)
                if list(kind.akzentfarben or []) != hex_farbe:
                    konten_services.akzentfarben_setzen(kind, hex_farbe, von=None)
            _schritt_abschliessen(3)
    except ValidationError as exc:
        raise SchrittFehler(_meldungen(exc)) from exc


# --- Schritt 4: E-Mail-Versand -----------------------------------------------------------------


def smtp_werte():
    konto = mail_selectors.smtp_konto()
    if konto is None:
        return {"port": 587, "sicherheit": "starttls"}
    return {
        "host": konto.host,
        "port": konto.port,
        "sicherheit": konto.sicherheit,
        "benutzername": konto.benutzername,
        "absender": konto.absender,
    }


def smtp_gespeichert():
    return mail_selectors.smtp_konto() is not None


def smtp_speichern(daten, *, testen=False):
    """Speichert das Postfach. Mit ``testen`` zusätzlich Testmail; Ergebnis oder ``None``."""
    try:
        with transaction.atomic():
            mail_services.smtp_speichern(
                host=daten["host"],
                port=daten["port"],
                sicherheit=daten["sicherheit"],
                benutzername=daten["benutzername"],
                absender=daten["absender"],
                passwort=daten.get("passwort") or None,
                von=None,
            )
            _setzen("einrichtung.smtp_uebersprungen", False)
            if not testen:
                _schritt_abschliessen(4)
    except ValidationError as exc:
        raise SchrittFehler(_meldungen(exc)) from exc
    if testen:
        return mail_services.testmail_senden(daten["testadresse"], von=None)
    return None


def smtp_ueberspringen():
    with transaction.atomic():
        _setzen("einrichtung.smtp_uebersprungen", True)
        audit.protokollieren("einrichtung.smtp_uebersprungen", akteur=None)
        _schritt_abschliessen(4)


def smtp_wurde_uebersprungen():
    try:
        return bool(einstellungen.wert("einrichtung.smtp_uebersprungen"))
    except einstellungen.EinstellungFehlt:
        return False


# --- Schritt 5: Netzwerk -----------------------------------------------------------------------


def netzwerk_werte(remote_addr=""):
    from apps.konten.einstellungen import PRIVATE_NETZE

    try:
        proxys = einstellungen.wert("konten.vertraute_proxys")
        netze = einstellungen.wert("konten.kind_netze_cidr")
    except einstellungen.EinstellungFehlt:
        proxys, netze = [], []
    if proxys == PRIVATE_NETZE and remote_addr:
        proxys = [remote_addr]  # erkannte Adresse des Proxys (Nginx Proxy Manager)
    try:
        basis_url = einstellungen.wert("einrichtung.basis_url")
    except einstellungen.EinstellungFehlt:
        basis_url = ""
    return {
        "basis_url": basis_url,
        "kind_netze": "\n".join(netze),
        "proxys": "\n".join(proxys),
    }


def netzwerk_speichern(daten):
    try:
        with transaction.atomic():
            _setzen("einrichtung.basis_url", daten["basis_url"])
            _setzen("konten.kind_netze_cidr", daten["kind_netze"])
            _setzen("konten.vertraute_proxys", daten["proxys"])
            _schritt_abschliessen(5)
    except einstellungen.EinstellungFehler as exc:
        raise SchrittFehler([str(exc)]) from exc


# --- Schritt 6: Zeit ---------------------------------------------------------------------------


def zeit_werte(heute):
    try:
        zone = einstellungen.wert("allgemein.zeitzone")
    except einstellungen.EinstellungFehlt:
        zone = "Europe/Berlin"
    try:
        tag = einstellungen.wert("allgemein.go_live_datum")
    except einstellungen.EinstellungFehlt:
        tag = heute
    return {"zeitzone": zone, "go_live_datum": tag}


def zeit_speichern(daten):
    try:
        with transaction.atomic():
            _setzen("allgemein.zeitzone", daten["zeitzone"])
            _setzen("allgemein.go_live_datum", daten["go_live_datum"])
            _schritt_abschliessen(6)
    except einstellungen.EinstellungFehler as exc:
        raise SchrittFehler([str(exc)]) from exc


# --- Schritt 7: Startwerte ---------------------------------------------------------------------


def startwerte_speichern(aenderungen):
    with transaction.atomic():
        for schluessel, wert in aenderungen.items():
            _setzen(schluessel, wert)
        _schritt_abschliessen(7)


# --- Schritt 8: Abschluss ----------------------------------------------------------------------


def offene_punkte():
    """Was vor dem Abschluss noch fehlt (leer = fertig)."""
    offen = []
    if zustand.freigegebener_schritt() < LETZTER_SCHRITT:
        offen.append(_("Nicht alle Schritte sind durchlaufen."))
    if len(konten_selectors.aktive_eltern()) < 2 or not passwort_gesetzt():
        offen.append(_("Eltern und Familien-Passwort fehlen (Schritt 2)."))
    if not konten_selectors.aktive_kinder().exists():
        offen.append(_("Es ist kein Kind angelegt (Schritt 3)."))
    if not smtp_gespeichert() and not smtp_wurde_uebersprungen():
        offen.append(_("E-Mail-Versand: einrichten oder bewusst überspringen (Schritt 4)."))
    muss = [
        s
        for s in einstellungen.fehlende()
        if not s.startswith("einrichtung.") and s != "allgemein.einrichtung_abgeschlossen"
    ]
    if muss:
        offen.append(_("Einstellungen ohne Wert: %(namen)s.") % {"namen": ", ".join(muss)})
    return offen


def zusammenfassung():
    konto = mail_selectors.smtp_konto()
    return {
        "app_name": app_name(),
        "eltern": [(b.anzeigename, b.elternprofil.email) for b in konten_selectors.aktive_eltern()],
        "kinder": [k.anzeigename for k in konten_selectors.aktive_kinder()],
        "smtp": (
            f"{konto.benutzername}@{konto.host}:{konto.port}"
            + (_(" (getestet)") if konto.zuletzt_getestet_am else _(" (nicht getestet)"))
            if konto
            else ""
        ),
        "smtp_uebersprungen": smtp_wurde_uebersprungen() and konto is None,
        "netzwerk": netzwerk_werte(),
        "zeit": zeit_werte(None),
    }


def abschliessen():
    """Setzt das Abschluss-Flag (danach ist der Assistent gesperrt) und protokolliert."""
    offen = offene_punkte()
    if offen:
        raise SchrittFehler(offen)
    with transaction.atomic():
        _setzen("allgemein.einrichtung_abgeschlossen", True)
        audit.protokollieren(
            "einrichtung.abgeschlossen",
            akteur=None,
            details={
                "eltern": len(konten_selectors.aktive_eltern()),
                "kinder": konten_selectors.aktive_kinder().count(),
                "smtp": "konfiguriert" if smtp_gespeichert() else "uebersprungen",
            },
        )
