"""Modelle von konten (DATA_MODEL 2). Zugriff von anderen Apps nur über ``services`` und
``selectors`` bzw. die öffentliche API (``zugriff``, ``geraet``); Passwort- und PIN-Hashes
verlassen die App nie.
"""

import re
import uuid

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .wappen import CHOICES as WAPPEN_CHOICES

HEX_FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


class WappenRolle(models.TextChoices):
    MAMA = "mama", "Mama"
    MUM = "mum", "Mum"
    PAPA = "papa", "Papa"
    DAD = "dad", "Dad"


class Rolle(models.TextChoices):
    ELTERN = "eltern", _("Eltern")
    KIND = "kind", _("Kind")


def akzentfarben_pruefen(wert):
    if not isinstance(wert, list) or len(wert) > 3:
        raise ValidationError("Liste mit höchstens 3 Hex-Farben erwartet")
    for farbe in wert:
        if not isinstance(farbe, str) or not HEX_FARBE.match(farbe):
            raise ValidationError(f"Ungültige Farbe {farbe!r} (Format #rrggbb)")


class BenutzerManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, anzeigename):
        return self.get(anzeigename__iexact=anzeigename)


class Benutzer(AbstractBaseUser):
    """Eltern und Kinder. Kein eigenes Passwort: Eltern nutzen ``ElternZugang``, Kinder die PIN.

    Benutzer werden deaktiviert (``aktiv=False``), nie gelöscht.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rolle = models.CharField(max_length=10, choices=Rolle.choices, db_index=True)
    anzeigename = models.CharField(max_length=40, unique=True)
    reihenfolge = models.SmallIntegerField(default=0)
    akzentfarben = models.JSONField(default=list, blank=True, validators=[akzentfarben_pruefen])
    aktiv = models.BooleanField(default=True)
    dungeon_anzeigen = models.BooleanField(
        default=True,
        help_text="Eltern: Dungeon-Bereich (Ränge, Mods, Abzeichen, Ruhmeshalle, Sondertage) zeigen.",
    )
    wappen = models.CharField(
        max_length=20, blank=True, choices=WAPPEN_CHOICES, help_text="Eltern: humorvolles Wappen."
    )
    wappen_rolle = models.CharField(max_length=5, blank=True, choices=WappenRolle.choices)
    wappen_rolle_eigen = models.CharField(
        max_length=15,
        blank=True,
        help_text="Eltern: freie Rolle (z. B. Mami), ersetzt die Auswahl.",
    )
    sprache = models.CharField(
        max_length=5,
        blank=True,
        choices=settings.LANGUAGES,
        help_text="Eigene Sprache; leer = Gerät bzw. Browser entscheidet.",
    )
    erstellt_am = models.DateTimeField(default=timezone.now)

    objects = BenutzerManager()

    USERNAME_FIELD = "anzeigename"
    REQUIRED_FIELDS = ["rolle"]

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"
        ordering = ["reihenfolge", "anzeigename"]
        constraints = [
            models.UniqueConstraint(Lower("anzeigename"), name="konten_benutzer_name_ci_uniq"),
        ]

    def __str__(self):
        return self.anzeigename

    @property
    def is_active(self):
        return self.aktiv

    def _get_session_auth_hash(self, secret=None):
        """Eltern haben kein eigenes Passwort: In die Sitzungs-Prüfsumme geht zusätzlich der
        Hash des gemeinsamen Eltern-Passworts ein. Ein Passwortwechsel beendet damit alle
        bestehenden Eltern-Sitzungen (Review AP19, B-05); die eigene erneuert die View."""
        if self.rolle != Rolle.ELTERN:
            return super()._get_session_auth_hash(secret=secret)
        from django.utils.crypto import salted_hmac

        zugang = ElternZugang.objects.filter(pk=1).values_list("passwort_hash", flat=True).first()
        return salted_hmac(
            "nestwerk.konten.Benutzer.get_session_auth_hash",
            f"{self.password}|{zugang or ''}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    @property
    def wappen_info(self):
        """Wappen (emoji, titel, spruch) oder ``None`` (Kinder, leer)."""
        from .wappen import info

        return info(self.wappen) if self.rolle == Rolle.ELTERN else None

    @property
    def rolle_anzeige(self):
        """Eigene Rolle, sonst gewählte Rolle, sonst leer."""
        return self.wappen_rolle_eigen or self.get_wappen_rolle_display() or ""

    @property
    def wappen_name(self):
        """Großer Wappen-Name: Rolle, ohne Rolle der Anzeigename."""
        return self.rolle_anzeige or self.anzeigename

    @property
    def name_mit_wappen(self):
        """Für Kinder-Texte: ``Mama (🐉 Hausdrache)``; ohne Rolle der Name."""
        w = self.wappen_info
        return f"{self.wappen_name} ({w.emoji} {w.titel})" if w else self.wappen_name

    @property
    def ist_eltern(self):
        return self.rolle == Rolle.ELTERN

    @property
    def ist_kind(self):
        return self.rolle == Rolle.KIND


class ElternLabel(models.TextChoices):
    MAMA = "mama", "Mama"
    PAPA = "papa", "Papa"
    ANDERE = "andere", "Andere"


class ElternProfil(models.Model):
    benutzer = models.OneToOneField(
        Benutzer, primary_key=True, on_delete=models.CASCADE, related_name="elternprofil"
    )
    rolle_label = models.CharField(
        max_length=10, choices=ElternLabel.choices, default=ElternLabel.ANDERE
    )
    email = models.EmailField(blank=True)

    class Meta:
        verbose_name = "Eltern-Profil"
        verbose_name_plural = "Eltern-Profile"
        constraints = [
            models.UniqueConstraint(
                fields=["rolle_label"],
                condition=~models.Q(rolle_label="andere"),
                name="konten_elternprofil_label_uniq",
            )
        ]

    def __str__(self):
        return f"Eltern: {self.benutzer}"


class KindProfil(models.Model):
    benutzer = models.OneToOneField(
        Benutzer, primary_key=True, on_delete=models.CASCADE, related_name="kindprofil"
    )
    pin_hash = models.CharField(max_length=255)
    pin_gesperrt_bis = models.DateTimeField(null=True, blank=True)
    pin_sperrstufe = models.SmallIntegerField(default=0)
    pin_fehlversuche = models.SmallIntegerField(default=0)

    class Meta:
        verbose_name = "Kind-Profil"
        verbose_name_plural = "Kind-Profile"

    def __str__(self):
        return f"Kind: {self.benutzer}"


class ElternZugang(models.Model):
    """Singleton (id = 1): das gemeinsame Eltern-Passwort als Argon2-Hash."""

    id = models.SmallIntegerField(primary_key=True, default=1)
    passwort_hash = models.CharField(max_length=255)
    geaendert_am = models.DateTimeField(default=timezone.now)
    geaendert_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "Eltern-Zugang"
        verbose_name_plural = "Eltern-Zugang"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="konten_zugang_id1")]

    def __str__(self):
        return "Eltern-Zugang"


class GeraeteTyp(models.TextChoices):
    KIOSK = "kiosk", _("Kiosk (Flur-Tablet)")
    PERSOENLICH = "persoenlich", _("Persönlich")


class Geraet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bezeichnung = models.CharField(max_length=60)
    typ = models.CharField(max_length=15, choices=GeraeteTyp.choices)
    registriert_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    registriert_am = models.DateTimeField(default=timezone.now)
    zuletzt_gesehen = models.DateTimeField(null=True, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Gerät"
        verbose_name_plural = "Geräte"
        ordering = ["bezeichnung"]

    def __str__(self):
        return f"{self.bezeichnung} ({self.get_typ_display()})"

    @property
    def ist_kiosk(self):
        return self.typ == GeraeteTyp.KIOSK


class AnmeldeArt(models.TextChoices):
    ELTERN = "eltern", _("Eltern")
    KIND = "kind", _("Kind")


class AnmeldeVersuch(models.Model):
    """Anmeldeversuch (Grundlage des Eltern-Rate-Limits je IP). Aufbewahrung 30 Tage.
    Enthält nie das eingegebene Passwort oder die PIN."""

    zeit = models.DateTimeField(default=timezone.now, db_index=True)
    art = models.CharField(max_length=10, choices=AnmeldeArt.choices)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    geraet = models.ForeignKey(
        Geraet, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    erfolgreich = models.BooleanField()

    class Meta:
        verbose_name = "Anmeldeversuch"
        verbose_name_plural = "Anmeldeversuche"
        indexes = [
            models.Index(fields=["benutzer", "zeit"], name="konten_versuch_benutzer_idx"),
            models.Index(fields=["ip", "zeit"], name="konten_versuch_ip_idx"),
        ]

    def __str__(self):
        return f"{self.zeit:%Y-%m-%d %H:%M} {self.art} {'ok' if self.erfolgreich else 'Fehler'}"
