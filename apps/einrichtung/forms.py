"""Formulare der Schritte 1 und 2 sowie 4 bis 6. Keine Passwörter oder PINs im Rückgabe-HTML:
die Felder werden nie vorbelegt."""

import ipaddress
import re
import zoneinfo
from datetime import timedelta
from urllib.parse import urlsplit

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.benachrichtigung.models import SmtpSicherheit
from apps.konten.models import ElternLabel, WappenRolle
from apps.konten.wappen import CHOICES as WAPPEN_CHOICES

PASSWORT_MINDESTLAENGE = 10
HAEUFIGE_PASSWOERTER = {
    "passwort123",
    "password123",
    "passwort1234",
    "familie123",
    "familie1234",
    "1234567890",
    "qwertzuiop",
    "qwertyuiop",
    "0123456789",
    "willkommen1",
}
TRENNER = re.compile(r"[\s,;]+")


def passwort_probleme(passwort, namen=()):
    """Liste deutscher Hinweise, was am Passwort zu schwach ist (leer = ausreichend)."""
    probleme = []
    if len(passwort) < PASSWORT_MINDESTLAENGE:
        probleme.append(_("mindestens %(n)s Zeichen") % {"n": PASSWORT_MINDESTLAENGE})
    if passwort.isdigit():
        probleme.append(_("nicht nur Ziffern"))
    if len(set(passwort.lower())) < 5:
        probleme.append(_("zu wenige verschiedene Zeichen"))
    klassen = sum(
        [
            bool(re.search(r"[a-zäöüß]", passwort)),
            bool(re.search(r"[A-ZÄÖÜ]", passwort)),
            bool(re.search(r"\d", passwort)),
            bool(re.search(r"[^\w\s]|_", passwort)),
        ]
    )
    if klassen < 2:
        probleme.append(_("Buchstaben mit Ziffern oder Sonderzeichen mischen"))
    if passwort.lower() in HAEUFIGE_PASSWOERTER:
        probleme.append(_("zu bekannt"))
    for name in namen:
        if len(name) >= 3 and name.lower() in passwort.lower():
            probleme.append(_("enthält einen Namen aus der Familie"))
            break
    return probleme


def netze_aus_text(text):
    """Zerlegt eine Eingabe (Zeilen, Kommas) in eine Liste; prüft jedes Netz (CIDR oder
    Einzeladresse). Das Netz ``/0`` ist nicht erlaubt (würde alles freigeben)."""
    eintraege = [e for e in TRENNER.split(text or "") if e]
    for eintrag in eintraege:
        try:
            netz = ipaddress.ip_network(eintrag, strict=False)
        except ValueError:
            raise ValidationError(
                _("'%(netz)s' ist kein gültiges Netz (z. B. 192.168.1.0/24 oder 192.168.1.5).")
                % {"netz": eintrag}
            ) from None
        if netz.prefixlen == 0:
            raise ValidationError(
                _("Das Netz /0 würde jede Adresse freigeben und ist nicht erlaubt.")
            )
    return eintraege


class AppNameForm(forms.Form):
    app_name = forms.CharField(label=gettext_lazy("Name der App"), max_length=40, strip=True)


class ElternForm(forms.Form):
    eltern1_name = forms.CharField(label=gettext_lazy("Name"), max_length=40, strip=True)
    eltern1_rolle = forms.ChoiceField(label=gettext_lazy("Rolle"), choices=ElternLabel.choices)
    eltern1_email = forms.EmailField(label=gettext_lazy("E-Mail"))
    eltern1_wappen = forms.ChoiceField(
        label=gettext_lazy("Wappen"), choices=WAPPEN_CHOICES, required=False
    )
    eltern1_wappen_rolle = forms.ChoiceField(
        label=gettext_lazy("Rolle"), choices=WappenRolle.choices, required=False
    )
    eltern1_wappen_rolle_eigen = forms.CharField(
        label=gettext_lazy("Eigene Rolle"), max_length=15, required=False, strip=True
    )
    eltern2_name = forms.CharField(label=gettext_lazy("Name"), max_length=40, strip=True)
    eltern2_rolle = forms.ChoiceField(label=gettext_lazy("Rolle"), choices=ElternLabel.choices)
    eltern2_email = forms.EmailField(label=gettext_lazy("E-Mail"))
    eltern2_wappen = forms.ChoiceField(
        label=gettext_lazy("Wappen"), choices=WAPPEN_CHOICES, required=False
    )
    eltern2_wappen_rolle = forms.ChoiceField(
        label=gettext_lazy("Rolle"), choices=WappenRolle.choices, required=False
    )
    eltern2_wappen_rolle_eigen = forms.CharField(
        label=gettext_lazy("Eigene Rolle"), max_length=15, required=False, strip=True
    )
    passwort = forms.CharField(label=gettext_lazy("Familien-Passwort"), strip=False, required=False)
    passwort2 = forms.CharField(
        label=gettext_lazy("Passwort wiederholen"), strip=False, required=False
    )

    def __init__(self, *args, passwort_pflicht=True, kinder_namen=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.passwort_pflicht = passwort_pflicht
        self.kinder_namen = [n.lower() for n in kinder_namen]

    def clean(self):
        daten = super().clean()
        n1, n2 = daten.get("eltern1_name"), daten.get("eltern2_name")
        if n1 and n2 and n1.lower() == n2.lower():
            self.add_error("eltern2_name", _("Die beiden Namen müssen verschieden sein."))
        for feld in ("eltern1_name", "eltern2_name"):
            name = daten.get(feld)
            if name and name.lower() in self.kinder_namen:
                self.add_error(feld, _("Dieser Name ist schon für ein Kind vergeben."))
        w1, w2 = daten.get("eltern1_wappen"), daten.get("eltern2_wappen")
        if w1 and w1 == w2:
            self.add_error("eltern2_wappen", _("Bitte zwei verschiedene Wappen wählen."))
        r1, r2 = daten.get("eltern1_rolle"), daten.get("eltern2_rolle")
        if r1 and r1 == r2 and r1 != ElternLabel.ANDERE:
            self.add_error("eltern2_rolle", _("Mama und Papa können nur je einmal vorkommen."))
        pw, pw2 = daten.get("passwort", ""), daten.get("passwort2", "")
        if not pw and not pw2:
            if self.passwort_pflicht:
                self.add_error("passwort", _("Bitte ein Familien-Passwort festlegen."))
            return daten
        if pw != pw2:
            self.add_error("passwort2", _("Die beiden Passwörter sind nicht gleich."))
        probleme = passwort_probleme(pw, [n for n in (n1, n2) if n])
        if probleme:
            self.add_error(
                "passwort", _("Zu schwach: %(probleme)s.") % {"probleme": "; ".join(probleme)}
            )
        return daten


class SmtpForm(forms.Form):
    host = forms.CharField(label=gettext_lazy("Server"), max_length=200, strip=True)
    port = forms.IntegerField(label=gettext_lazy("Port"), min_value=1, max_value=65535)
    sicherheit = forms.ChoiceField(
        label=gettext_lazy("Verschlüsselung"), choices=SmtpSicherheit.choices
    )
    benutzername = forms.CharField(label=gettext_lazy("Benutzername"), max_length=200, strip=True)
    passwort = forms.CharField(label=gettext_lazy("Passwort"), strip=False, required=False)
    absender = forms.EmailField(label=gettext_lazy("Absender-Adresse"))
    testadresse = forms.EmailField(label=gettext_lazy("Testmail an"), required=False)

    def __init__(self, *args, passwort_gespeichert=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.passwort_gespeichert = passwort_gespeichert

    def clean(self):
        daten = super().clean()
        if not daten.get("passwort") and not self.passwort_gespeichert:
            self.add_error("passwort", _("Bitte das Passwort des Postfachs eingeben."))
        return daten


class NetzwerkForm(forms.Form):
    basis_url = forms.CharField(label=gettext_lazy("Adresse der App"), max_length=200, strip=True)
    kind_netze = forms.CharField(label=gettext_lazy("Heimnetz für Kinder-Login"), strip=True)
    proxys = forms.CharField(label=gettext_lazy("Vertraute Proxys"), required=False, strip=True)

    def clean_basis_url(self):
        url = self.cleaned_data["basis_url"].rstrip("/")
        teile = urlsplit(url)
        if teile.scheme not in ("http", "https") or not teile.hostname:
            raise ValidationError(_("Bitte eine Adresse wie https://nestwerk.example.org angeben."))
        if teile.path or teile.query or teile.fragment:
            raise ValidationError(
                _("Nur die Adresse ohne Pfad, z. B. https://nestwerk.example.org.")
            )
        return url

    def clean_kind_netze(self):
        netze = netze_aus_text(self.cleaned_data["kind_netze"])
        if not netze:
            raise ValidationError(_("Mindestens ein Netz angeben (z. B. 192.168.0.0/16)."))
        return netze

    def clean_proxys(self):
        return netze_aus_text(self.cleaned_data.get("proxys", ""))


class ZeitForm(forms.Form):
    zeitzone = forms.CharField(label=gettext_lazy("Zeitzone"), max_length=64, strip=True)
    go_live_datum = forms.DateField(label=gettext_lazy("Go-live-Datum"))

    def clean_zeitzone(self):
        zone = self.cleaned_data["zeitzone"]
        if zone not in zoneinfo.available_timezones():
            raise ValidationError(_("Unbekannte Zeitzone (z. B. Europe/Berlin)."))
        return zone

    def clean_go_live_datum(self):
        tag = self.cleaned_data["go_live_datum"]
        heute = timezone.localdate()
        if not heute - timedelta(days=366) <= tag <= heute + timedelta(days=366):
            raise ValidationError(_("Das Datum liegt mehr als ein Jahr von heute entfernt."))
        return tag
