"""Belohnungskatalog, Einlöseanträge und Taschengeld-Limit (DATA_MODEL 8)."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

TASCHENGELD = "taschengeld"


class Belohnungskategorie(models.Model):
    name = models.CharField(max_length=40, unique=True)
    symbol = models.CharField(max_length=60)
    systemschluessel = models.SlugField(
        blank=True, help_text="Feste Kennung; 'taschengeld' aktiviert die Limit-Logik."
    )
    reihenfolge = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ["reihenfolge", "name"]
        verbose_name = "Belohnungskategorie"
        verbose_name_plural = "Belohnungskategorien"
        constraints = [
            models.UniqueConstraint(
                fields=["systemschluessel"],
                condition=~Q(systemschluessel=""),
                name="belohnung_kategorie_schluessel_uniq",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def ist_taschengeld(self):
        return self.systemschluessel == TASCHENGELD


class Belohnung(models.Model):
    titel = models.CharField(max_length=80)
    kategorie = models.ForeignKey(
        Belohnungskategorie, on_delete=models.PROTECT, related_name="belohnungen"
    )
    preis_punkte = models.PositiveIntegerField()
    geldwert_cent = models.PositiveIntegerField(
        null=True, blank=True, help_text="Nur Taschengeld: Betrag in Cent."
    )
    symbol = models.CharField(max_length=60, blank=True)
    aktiv = models.BooleanField(default=True)
    reihenfolge = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ["kategorie__reihenfolge", "reihenfolge", "titel"]
        verbose_name = "Belohnung"
        verbose_name_plural = "Belohnungen"
        constraints = [
            models.CheckConstraint(condition=Q(preis_punkte__gt=0), name="belohnung_preis_pos"),
        ]

    def __str__(self):
        return self.titel

    @property
    def anzeige_symbol(self):
        return self.symbol or self.kategorie.symbol

    def clean(self):
        kategorie = getattr(self, "kategorie", None) if self.kategorie_id else None
        if kategorie is not None and kategorie.ist_taschengeld:
            if not self.geldwert_cent:
                raise ValidationError({"geldwert_cent": "Taschengeld braucht einen Betrag."})
        elif self.geldwert_cent is not None:
            raise ValidationError({"geldwert_cent": "Nur Taschengeld hat einen Betrag."})


class Status(models.TextChoices):
    OFFEN = "offen", "Offen"
    BESTAETIGT = "bestaetigt", "Bestätigt"
    ABGELEHNT = "abgelehnt", "Abgelehnt"
    ZURUECKGEZOGEN = "zurueckgezogen", "Zurückgezogen"


class Einloeseantrag(models.Model):
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="einloeseantraege"
    )
    belohnung = models.ForeignKey(Belohnung, on_delete=models.PROTECT, related_name="antraege")
    titel_snapshot = models.CharField(max_length=80)
    preis_snapshot = models.PositiveIntegerField()
    geldwert_cent_snapshot = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OFFEN)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    entschieden_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    entschieden_am = models.DateTimeField(null=True, blank=True)
    ablehnungsgrund = models.CharField(max_length=200, blank=True)
    buchung = models.OneToOneField(
        "punkte.Buchung", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-erstellt_am", "-id"]
        verbose_name = "Einlöseantrag"
        verbose_name_plural = "Einlöseanträge"
        indexes = [models.Index(fields=["kind", "status"], name="belohnung_antrag_kind_status")]
        constraints = [
            models.CheckConstraint(
                condition=Q(preis_snapshot__gt=0), name="belohnung_antrag_preis_pos"
            ),
        ]

    def __str__(self):
        return f"{self.titel_snapshot} ({self.get_status_display()})"

    @property
    def geldwert_text(self):
        cent = self.geldwert_cent_snapshot
        return "" if cent is None else f"{cent // 100},{cent % 100:02d} €"


class TaschengeldLimit(models.Model):
    """Überschreibt das Standard-Monatslimit für ein Kind."""

    kind = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="taschengeld_limit",
    )
    monatslimit_cent = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Taschengeld-Limit"
        verbose_name_plural = "Taschengeld-Limits"

    def __str__(self):
        return f"{self.kind_id}: {self.monatslimit_cent} Cent"
