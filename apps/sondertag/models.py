"""Datenmodell von sondertag (DATA_MODEL 10, AP27): ein Modell für den ganzen Lebenszyklus.

``SondertagAnspruch`` = Anspruch (aus Meilenstein oder manuell) + Wunsch + Annahme + Historie.
Status (gespeichert): ``verdient`` -> ``wunsch_offen`` -> ``angenommen`` -> ``stattgefunden``.
"Einlösbar" wird nicht gespeichert, sondern berechnet (``einloesbar_ab <= heute`` und erster
offener Anspruch des Kindes), weil es allein vom Datum abhängt.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.kern import zeit


class Quelle(models.TextChoices):
    MEILENSTEIN = "meilenstein", "Meilenstein"
    MANUELL = "manuell", "manuell erfasst"


class Status(models.TextChoices):
    VERDIENT = "verdient", "verdient"
    WUNSCH_OFFEN = "wunsch_offen", "Wunsch offen"
    ANGENOMMEN = "angenommen", "angenommen"
    STATTGEFUNDEN = "stattgefunden", "stattgefunden"


class BegleitungWunsch(models.TextChoices):
    MAMA = "mama", "Mama"
    PAPA = "papa", "Papa"
    EGAL = "egal", "egal"


OFFEN = (Status.VERDIENT, Status.WUNSCH_OFFEN)
ANGENOMMEN = (Status.ANGENOMMEN, Status.STATTGEFUNDEN)


class SondertagAnspruch(models.Model):
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sondertage"
    )
    meilenstein = models.OneToOneField(
        "spielregeln.MeilensteinErreicht",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sondertag",
        help_text="NULL nur bei manueller Historie",
    )
    quelle = models.CharField(max_length=12, choices=Quelle.choices, default=Quelle.MEILENSTEIN)
    titel = models.CharField(max_length=80, blank=True, default="", help_text="z. B. Meilenstein")
    verdient_am = models.DateTimeField(default=zeit.jetzt)
    einloesbar_ab = models.DateField(null=True, blank=True, help_text="berechnet (Grenzen)")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.VERDIENT)
    wunsch = models.TextField(blank=True, default="")
    begleitung_wunsch = models.CharField(
        max_length=5, choices=BegleitungWunsch.choices, blank=True, default=""
    )
    wunsch_am = models.DateTimeField(null=True, blank=True)
    angenommen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    begleitung = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Übergabe ändert nur dieses Feld (Audit)",
    )
    annahme_datum = models.DateField(
        null=True, blank=True, help_text="Bezugsdatum für Abstand und App-Jahr (korrigierbar)"
    )
    stattgefunden_am = models.DateField(null=True, blank=True)
    einloesbar_gemeldet_am = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Meldung 'jetzt einlösbar' verschickt (genau einmal, auch bei Freischaltung)",
    )
    notiz = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "Sondertag"
        verbose_name_plural = "Sondertage"
        ordering = ["verdient_am", "id"]
        indexes = [
            models.Index(fields=["kind", "status"], name="sondertag_kind_status"),
            models.Index(fields=["kind", "annahme_datum"], name="sondertag_kind_annahme"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quelle="manuell") | Q(meilenstein__isnull=False),
                name="sondertag_meilenstein_oder_manuell",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["verdient", "wunsch_offen"])
                | Q(annahme_datum__isnull=False),
                name="sondertag_angenommen_mit_datum",
            ),
        ]

    def __str__(self):
        return f"Sondertag {self.kind_id} ({self.status})"

    @property
    def offen(self):
        return self.status in OFFEN
