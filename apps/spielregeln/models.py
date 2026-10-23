"""Modelle von spielregeln (DATA_MODEL 6.3–6.6, AP20).

- ``Aktivitaet`` und ``Pause`` sind die **Historie** (Fakten).
- ``Wochenauswertung`` und ``KindStand`` sind **Zwischenspeicher**: jederzeit aus der Historie
  neu berechenbar (``manage.py spielregeln_neuberechnen``, ARCHITECTURE 7.1).
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class PauseQuelle(models.TextChoices):
    ELTERN = "eltern", "Eltern"
    HAUSAUTOMATION = "hausautomation", "Hausautomation"


class Pause(models.Model):
    """Pause eines Kindes oder der ganzen Familie (``kind = NULL``). ``von``/``bis`` sind lokale
    Daten, inklusiv; ``bis = NULL`` = offen. Überlappungen sind erlaubt (Vereinigung zählt)."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pausen",
        limit_choices_to={"rolle": "kind"},
    )
    von = models.DateField()
    bis = models.DateField(null=True, blank=True)
    grund = models.CharField(max_length=120, blank=True, default="")
    quelle = models.CharField(max_length=20, choices=PauseQuelle.choices)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    erstellt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Pause"
        verbose_name_plural = "Pausen"
        indexes = [models.Index(fields=["kind", "von", "bis"], name="spielregeln_pause_kind")]
        constraints = [
            models.CheckConstraint(
                condition=Q(bis__isnull=True) | Q(bis__gte=F("von")),
                name="spielregeln_pause_bis_nach_von",
            )
        ]

    def __str__(self):
        wer = self.kind_id or "Familie"
        return f"Pause {wer}: {self.von}–{self.bis or 'offen'}"

    @property
    def familie(self):
        return self.kind_id is None


class Aktivitaet(models.Model):
    """Fakt "Kind war an ``datum`` aktiv" (bestätigte Aufgabe, später z. B. Lernen).

    ``datum`` = wirksames Bezugsdatum (K1: Meldedatum; nach Finalisierung der Meldewoche der
    Tag der Bestätigung). Storno markiert, löscht nie."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="aktivitaeten"
    )
    datum = models.DateField()
    modul = models.CharField(max_length=40)
    referenz = models.CharField(max_length=60)
    storniert = models.BooleanField(default=False)
    erstellt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Aktivität"
        verbose_name_plural = "Aktivitäten"
        indexes = [models.Index(fields=["kind", "datum"], name="spielregeln_akt_kind_datum")]
        constraints = [
            models.UniqueConstraint(fields=["modul", "referenz"], name="spielregeln_akt_idem")
        ]

    def __str__(self):
        return f"{self.kind_id} {self.datum} {self.modul}:{self.referenz}"


class Wochenauswertung(models.Model):
    """Auswertung einer ISO-Woche je Kind (Zwischenspeicher). ``finalisiert_am = NULL`` =
    vorläufig (Woche vorbei, Puffer läuft noch)."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wochenauswertungen"
    )
    iso_jahr = models.PositiveSmallIntegerField()
    iso_woche = models.PositiveSmallIntegerField()
    montag = models.DateField(db_index=True)
    aktiv = models.BooleanField()
    neutral = models.BooleanField(help_text="nicht aktiv, aber pausiert (Serie bleibt)")
    pausentage = models.PositiveSmallIntegerField()
    xp_woche = models.IntegerField(default=0)
    wochenserie_danach = models.PositiveSmallIntegerField()
    aktive_wochen_gesamt = models.PositiveIntegerField()
    # Held der Woche (AP30)
    zuwachs_relativ = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    held_der_woche = models.BooleanField(default=False)
    finalisiert_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Wochenauswertung"
        verbose_name_plural = "Wochenauswertungen"
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "iso_jahr", "iso_woche"], name="spielregeln_woche_idem"
            ),
            models.CheckConstraint(
                condition=Q(iso_woche__gte=1, iso_woche__lte=53), name="spielregeln_woche_1_53"
            ),
        ]

    def __str__(self):
        return f"{self.kind_id} {self.iso_jahr}-W{self.iso_woche:02d}"


class KindStand(models.Model):
    """Zwischenspeicher je Kind (DATA_MODEL 6.6). Rang-Felder ergänzt AP22.

    ``wochenserie``/``aktive_wochen_gesamt``/``rekord_wochenserie``: Stand nach der letzten
    finalisierten Woche. ``tagesserie``/``rekord_tagesserie``: Stand am ``stand_datum``.
    """

    kind = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="spielstand",
    )
    wochenserie = models.PositiveSmallIntegerField(default=0)
    rekord_wochenserie = models.PositiveSmallIntegerField(default=0)
    aktive_wochen_gesamt = models.PositiveIntegerField(default=0)
    tagesserie = models.PositiveSmallIntegerField(default=0)
    rekord_tagesserie = models.PositiveSmallIntegerField(default=0)
    letzte_woche = models.CharField(max_length=10, blank=True, default="")  # "2026-W44"
    stand_datum = models.DateField(null=True, blank=True)
    aktualisiert_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Spielstand"
        verbose_name_plural = "Spielstände"

    def __str__(self):
        return f"Stand {self.kind_id}"
