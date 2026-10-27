"""Modelle von benachrichtigung (DATA_MODEL 5). Zugriff von außen nur über ``services``,
``selectors``, ``registry`` und ``texte``.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _


class SmtpSicherheit(models.TextChoices):
    STARTTLS = "starttls", _("STARTTLS (Port 587)")
    SSL = "ssl", _("SSL/TLS (Port 465)")
    KEINE = "keine", _("Unverschlüsselt")


class SmtpKonto(models.Model):
    """Singleton (id = 1): Postausgang für den E-Mail-Kanal. Das Passwort liegt nur als
    Fernet-Token in der DB (``benachrichtigung.crypto``), nie im Klartext."""

    id = models.SmallIntegerField(primary_key=True, default=1)
    host = models.CharField(max_length=200)
    port = models.PositiveIntegerField()
    sicherheit = models.CharField(max_length=10, choices=SmtpSicherheit.choices)
    benutzername = models.CharField(max_length=200)
    passwort_verschluesselt = models.TextField()
    absender = models.EmailField()
    zuletzt_getestet_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("SMTP-Konto")
        verbose_name_plural = _("SMTP-Konto")
        constraints = [models.CheckConstraint(condition=Q(id=1), name="benachr_smtp_id1")]

    def __str__(self):
        return f"{self.benutzername}@{self.host}:{self.port}"


class Kanal(models.Model):
    slug = models.CharField(max_length=30, primary_key=True)
    bezeichnung = models.CharField(max_length=60)
    aktiv = models.BooleanField(default=True)
    konfig = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Kanal")
        verbose_name_plural = _("Kanäle")

    def __str__(self):
        return self.slug

    @property
    def anzeigename(self):
        """Deutsche Bezeichnung als Msgid in der aktiven Sprache; geänderte Namen bleiben."""
        return gettext(self.bezeichnung)


class Praeferenz(models.Model):
    """Ausdrückliche Einstellung je Benutzer x Ereignistyp x Kanal. Fehlt die Zeile, gilt der
    Standard aus ``EreignisTyp.standard_kanaele``."""

    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    ereignistyp = models.ForeignKey(
        "ereignisse.EreignisTyp", on_delete=models.CASCADE, related_name="+"
    )
    kanal = models.ForeignKey(Kanal, on_delete=models.CASCADE, related_name="+")
    aktiv = models.BooleanField()

    class Meta:
        verbose_name = _("Präferenz")
        verbose_name_plural = _("Präferenzen")
        constraints = [
            models.UniqueConstraint(
                fields=["benutzer", "ereignistyp", "kanal"], name="benachr_praeferenz_uniq"
            )
        ]

    def __str__(self):
        return f"{self.benutzer_id}: {self.ereignistyp_id}/{self.kanal_id} = {self.aktiv}"


class Ruhezeit(models.Model):
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    von = models.TimeField()
    bis = models.TimeField(help_text=_("Kleiner als 'von' = über Mitternacht"))
    wochentage = models.SmallIntegerField(default=127, help_text=_("Bitmaske Mo=1 … So=64"))
    gilt_fuer_email = models.BooleanField(default=False)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Ruhezeit")
        verbose_name_plural = _("Ruhezeiten")
        constraints = [
            models.CheckConstraint(
                condition=Q(wochentage__gte=1, wochentage__lte=127), name="benachr_ruhe_tage"
            )
        ]

    def __str__(self):
        return f"{self.benutzer}: {self.von:%H:%M}–{self.bis:%H:%M}"


class BenachrichtigungsProfil(models.Model):
    """Zusatzprofil je Elternteil (K13): E-Mail nur bei Entscheidungen."""

    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE, related_name="+"
    )
    mail_nur_entscheidungen = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Benachrichtigungsprofil")
        verbose_name_plural = _("Benachrichtigungsprofile")

    def __str__(self):
        return f"Profil {self.benutzer_id}"


class Benachrichtigung(models.Model):
    """Eintrag der Dashboard-Liste: entsteht je Empfänger und Ereignis immer, unabhängig von
    Kanälen und Ruhezeiten."""

    empfaenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    ereignis = models.ForeignKey("ereignisse.Ereignis", on_delete=models.PROTECT, related_name="+")
    titel = models.CharField(max_length=120)
    text = models.CharField(max_length=400, blank=True, default="")
    link = models.CharField(max_length=200, blank=True, default="")
    erstellt_am = models.DateTimeField(default=timezone.now)
    gelesen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Benachrichtigung")
        verbose_name_plural = _("Benachrichtigungen")
        ordering = ["-erstellt_am", "-id"]
        indexes = [
            models.Index(fields=["empfaenger", "gelesen_am"], name="benachr_empf_gelesen_idx")
        ]
        constraints = [
            models.UniqueConstraint(fields=["empfaenger", "ereignis"], name="benachr_empf_ereignis")
        ]

    def __str__(self):
        return f"{self.empfaenger}: {self.titel}"


class PushAbo(models.Model):
    """Push-Abonnement eines Geräts (Anmeldung und Versand: ``push``). 404/410 vom Push-Dienst
    setzen ``aktiv`` auf False."""

    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    geraet = models.ForeignKey(
        "konten.Geraet", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    endpoint = models.TextField()
    endpoint_hash = models.CharField(max_length=64, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    bezeichnung = models.CharField(max_length=60, blank=True, default="")
    user_agent = models.CharField(max_length=300, blank=True, default="")
    erstellt_am = models.DateTimeField(default=timezone.now)
    zuletzt_ok = models.DateTimeField(null=True, blank=True)
    fehlerzaehler = models.PositiveSmallIntegerField(default=0)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Push-Abo")
        verbose_name_plural = _("Push-Abos")

    def __str__(self):
        return f"{self.benutzer}: {self.bezeichnung or self.endpoint_hash[:8]}"


class ZustellStatus(models.TextChoices):
    OFFEN = "offen", _("offen")
    GESENDET = "gesendet", _("gesendet")
    UNTERDRUECKT_RUHEZEIT = "unterdrueckt_ruhezeit", _("stumm (Ruhezeit)")
    UNTERDRUECKT_PRAEFERENZ = "unterdrueckt_praeferenz", _("abgeschaltet")
    FEHLER = "fehler", _("Fehler (Wiederholung geplant)")
    AUFGEGEBEN = "aufgegeben", _("aufgegeben")
    NICHT_KONFIGURIERT = "nicht_konfiguriert", _("Kanal nicht eingerichtet")


class Zustellung(models.Model):
    benachrichtigung = models.ForeignKey(
        Benachrichtigung, on_delete=models.CASCADE, related_name="zustellungen"
    )
    kanal = models.ForeignKey(Kanal, on_delete=models.PROTECT, related_name="+")
    push_abo = models.ForeignKey(
        PushAbo, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=30, choices=ZustellStatus.choices)
    versuche = models.PositiveSmallIntegerField(default=0)
    naechster_versuch = models.DateTimeField(null=True, blank=True)
    gesendet_am = models.DateTimeField(null=True, blank=True)
    fehler = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = _("Zustellung")
        verbose_name_plural = _("Zustellungen")
        indexes = [
            models.Index(fields=["status", "naechster_versuch"], name="benachr_zust_faellig")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["benachrichtigung", "kanal", "push_abo"], name="benachr_zust_uniq"
            ),
            # NULL ist in SQLite unique-verschieden: eigene Regel für E-Mail/Pop-up
            models.UniqueConstraint(
                fields=["benachrichtigung", "kanal"],
                condition=Q(push_abo__isnull=True),
                name="benachr_zust_ohne_abo_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.benachrichtigung_id}/{self.kanal_id}: {self.status}"


class Popup(models.Model):
    """In-App-Pop-up für Kinder (Kanal ``popup``); wird beim nächsten Laden/Poll angezeigt."""

    empfaenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    benachrichtigung = models.OneToOneField(
        Benachrichtigung, on_delete=models.CASCADE, related_name="popup"
    )
    art = models.CharField(max_length=80, help_text=_("Ereignistyp, steuert die Darstellung"))
    titel = models.CharField(max_length=120)
    text = models.CharField(max_length=400, blank=True, default="")
    erstellt_am = models.DateTimeField(default=timezone.now)
    gesehen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Pop-up")
        verbose_name_plural = _("Pop-ups")
        indexes = [models.Index(fields=["empfaenger", "gesehen_am"], name="benachr_popup_offen")]

    def __str__(self):
        return f"{self.empfaenger_id}: {self.titel}"
