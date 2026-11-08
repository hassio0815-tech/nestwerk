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

from . import moods

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
        help_text=(
            "Eltern: Dungeon-Bereich (Ränge, Mods, Abzeichen, Ruhmeshalle, Sondertage) zeigen."
        ),
    )
    spitzname = models.CharField(
        max_length=20,
        blank=True,
        help_text="Kind: kurzer Spitzname (optional), ersetzt den Namen in Grüßen.",
    )
    mood = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Gewählter Mood (Katalog-Schlüssel der eigenen Zielgruppe oder eigen-<id>); "
            "leer = kein Mood."
        ),
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
    def zielgruppe(self):
        """Zielgruppe des Mood-Katalogs: ``kind`` oder ``eltern``."""
        return moods.ELTERN if self.rolle == Rolle.ELTERN else moods.KIND

    @property
    def mood_info(self):
        """Mood von Eltern (``emoji``, ``titel``, ``spruch``) oder ``None`` (Kinder, leer).
        Eigene Eltern-Moods (``eigen-<id>``) erscheinen mit ⭐ und ohne Spruch."""
        if self.rolle != Rolle.ELTERN or not self.mood:
            return None
        if self.mood.startswith(moods.EIGEN_PRAEFIX):
            rest = self.mood[len(moods.EIGEN_PRAEFIX) :]
            if not (rest.isascii() and rest.isdigit()):
                return None
            eigen = MoodEigen.objects.filter(
                pk=int(rest), zielgruppe=moods.ELTERN, aktiv=True
            ).first()
            return moods.Mood(self.mood, "⭐", eigen.text, "eigen") if eigen else None
        if MoodAusgeblendet.objects.filter(pk=self.mood).exists():
            return None
        return moods.info(self.mood, moods.ELTERN)

    @property
    def rolle_anzeige(self):
        """Eigene Rolle, sonst gewählte Rolle, sonst leer."""
        return self.wappen_rolle_eigen or self.get_wappen_rolle_display() or ""

    @property
    def rolle_name(self):
        """Großer Name: Rolle, ohne Rolle der Anzeigename."""
        return self.rolle_anzeige or self.anzeigename

    @property
    def name_mit_mood(self):
        """Für Kinder-Texte: ``Mama (🐉 Hausdrache)``; ohne Rolle der Name."""
        m = self.mood_info
        return f"{self.rolle_name} ({m.anzeige})" if m else self.rolle_name

    @property
    def rufname(self):
        """Spitzname, sonst Anzeigename (für Grüße und Kacheln)."""
        return self.spitzname or self.anzeigename

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


class MoodEigen(models.Model):
    """Eigener Mood der Familie: von Eltern ergänzt oder aus einem Vorschlag zugelassen.
    Gilt für alle der ``zielgruppe`` (Kinder bzw. Eltern); ``aktiv=False`` = entfernt (bleibt für
    alte Auswahl erhalten)."""

    zielgruppe = models.CharField(
        max_length=6,
        choices=[(moods.KIND, "Kinder"), (moods.ELTERN, "Eltern")],
        default=moods.KIND,
        db_index=True,
    )
    text = models.CharField(max_length=40)
    aktiv = models.BooleanField(default=True)
    erstellt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Eigener Mood"
        verbose_name_plural = "Eigene Moods"
        ordering = ["text"]
        constraints = [
            models.UniqueConstraint(
                "zielgruppe", Lower("text"), name="konten_moodeigen_zg_text_ci_uniq"
            )
        ]

    def __str__(self):
        return self.text

    @property
    def schluessel(self):
        return f"eigen-{self.pk}"


class MoodAusgeblendet(models.Model):
    """Katalog-Mood (Kinder oder Eltern), den Eltern aus der Auswahl genommen haben. Die Schlüssel
    der beiden Kataloge sind überschneidungsfrei (Test), daher genügt der Schlüssel."""

    schluessel = models.CharField(max_length=30, primary_key=True)

    class Meta:
        verbose_name = "Ausgeblendeter Mood"
        verbose_name_plural = "Ausgeblendete Moods"

    def __str__(self):
        return self.schluessel


class VorschlagStatus(models.TextChoices):
    OFFEN = "offen", _("Offen")
    ZUGELASSEN = "zugelassen", _("Zugelassen")
    ABGELEHNT = "abgelehnt", _("Abgelehnt")


class MoodVorschlag(models.Model):
    """Mood-Vorschlag eines Kindes; Eltern lassen ihn zu (dann gilt er für alle) oder lehnen ab."""

    kind = models.ForeignKey(
        Benutzer,
        on_delete=models.PROTECT,
        related_name="mood_vorschlaege",
        limit_choices_to={"rolle": "kind"},
    )
    text = models.CharField(max_length=40)
    status = models.CharField(
        max_length=12, choices=VorschlagStatus.choices, default=VorschlagStatus.OFFEN, db_index=True
    )
    entschieden_von = models.ForeignKey(
        Benutzer, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    entschieden_am = models.DateTimeField(null=True, blank=True)
    erstellt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Mood-Vorschlag"
        verbose_name_plural = "Mood-Vorschläge"
        ordering = ["erstellt_am", "id"]

    def __str__(self):
        return f"{self.kind}: {self.text} ({self.status})"
