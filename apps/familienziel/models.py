"""Modelle von familienziel (DATA_MODEL 11, AP29).

- ``Familienbelohnung``: Liste der Eltern (Pizza, Spieleabend …), aus der abgestimmt wird.
- ``Familienwoche``: eine Zeile je ISO-Woche (unique). Der Fortschritt wird nie gespeichert,
  sondern live aus ``punkte`` gelesen; gespeichert sind Ziel-Snapshot, Belohnung, Status.
- ``Stimme``: eine Stimme je Kind und Zielwoche, änderbar bis Abstimmungsende.
- ``Grossziel``: Fakt "großes Ziel freigeschaltet" (unique je auslösender Woche).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _


class Familienbelohnung(models.Model):
    titel = models.CharField(max_length=60)
    symbol = models.CharField(max_length=60, blank=True, default="")
    ist_grossziel = models.BooleanField(default=False)
    aktiv = models.BooleanField(default=True)
    reihenfolge = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("Familienbelohnung")
        verbose_name_plural = _("Familienbelohnungen")
        ordering = ["reihenfolge", "id"]

    def __str__(self):
        return gettext(self.titel) if self.titel else ""  # Start-Titel in der aktiven Sprache


class AbstimmungStatus(models.TextChoices):
    OFFEN = "offen", _("offen")
    GESCHLOSSEN = "geschlossen", _("geschlossen")
    GLEICHSTAND = "gleichstand", _("Eltern entscheiden")
    ELTERN_ENTSCHIEDEN = "eltern_entschieden", _("von den Eltern entschieden")


class WochenStatus(models.TextChoices):
    LAUFEND = "laufend", _("laufend")
    ERREICHT = "erreicht", _("erreicht")
    VERFEHLT = "verfehlt", _("verfehlt")
    NEUTRAL = "neutral", _("neutral")


class Familienwoche(models.Model):
    iso_jahr = models.PositiveSmallIntegerField()
    iso_woche = models.PositiveSmallIntegerField()
    montag = models.DateField()
    ziel_punkte = models.PositiveIntegerField(help_text=_("Snapshot aus der Einstellung"))
    belohnung = models.ForeignKey(
        Familienbelohnung,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wochen",
    )
    abstimmung_status = models.CharField(
        max_length=20, choices=AbstimmungStatus.choices, default=AbstimmungStatus.OFFEN
    )
    status = models.CharField(
        max_length=10, choices=WochenStatus.choices, default=WochenStatus.LAUFEND
    )
    erreicht_am = models.DateTimeField(null=True, blank=True)
    eingeloest_am = models.DateTimeField(null=True, blank=True)
    finalisiert_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Familienwoche")
        verbose_name_plural = _("Familienwochen")
        ordering = ["iso_jahr", "iso_woche"]
        constraints = [
            models.UniqueConstraint(
                fields=["iso_jahr", "iso_woche"], name="familienziel_woche_idem"
            ),
            models.CheckConstraint(
                condition=Q(status="erreicht", erreicht_am__isnull=False) | ~Q(status="erreicht"),
                name="familienziel_erreicht_hat_zeit",
            ),
        ]

    def __str__(self):
        return f"{self.iso_jahr}-W{self.iso_woche:02d}"


class Stimme(models.Model):
    woche = models.ForeignKey(Familienwoche, on_delete=models.CASCADE, related_name="stimmen")
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="familienziel_stimmen"
    )
    belohnung = models.ForeignKey(
        Familienbelohnung, on_delete=models.PROTECT, related_name="stimmen"
    )
    abgegeben_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("Stimme")
        verbose_name_plural = _("Stimmen")
        constraints = [
            models.UniqueConstraint(fields=["woche", "kind"], name="familienziel_stimme_je_kind")
        ]

    def __str__(self):
        return f"{self.kind_id} -> {self.belohnung_id} ({self.woche})"


class Grossziel(models.Model):
    ausloesende_woche = models.OneToOneField(
        Familienwoche, on_delete=models.PROTECT, related_name="grossziel"
    )
    belohnung = models.ForeignKey(
        Familienbelohnung, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    name = models.CharField(max_length=60, blank=True, default="")
    freigeschaltet_am = models.DateTimeField(default=timezone.now)
    eingeloest_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Großziel")
        verbose_name_plural = _("Großziele")
        ordering = ["-freigeschaltet_am", "-id"]

    def __str__(self):
        return gettext("Großziel nach %(woche)s") % {"woche": self.ausloesende_woche}
