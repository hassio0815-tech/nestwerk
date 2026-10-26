"""Modelle von punkte (DATA_MODEL 3). Zugriff von außen nur über ``services``/``selectors``.

``Buchung`` ist das unveränderliche Ledger: Salden werden immer aus der Summe der Buchungen
berechnet, nie gespeichert. Insert-only über ``kern.db`` (Modell, QuerySet, SQLite-Trigger).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.kern.db import NurEinfuegenModell


class Art(models.TextChoices):
    AUFGABE = "aufgabe", "Aufgabe"
    SERIENBONUS = "serienbonus", "Serienbonus"
    SONDERPUNKTE = "sonderpunkte", "Sonderpunkte"
    MODUL = "modul", "Modul"
    EINLOESUNG = "einloesung", "Einlösung"
    MODKAUF = "modkauf", "Mod-Kauf"
    KORREKTUR = "korrektur", "Korrektur"
    STORNO = "storno", "Storno"


# Arten, deren XP-Wirkung negativ sein darf (ARCHITECTURE 13.2 K2)
XP_SENKEND = (Art.KORREKTUR, Art.STORNO)


class Buchung(NurEinfuegenModell):
    """Ein Ledger-Eintrag (insert-only). Wirkung je Art: ``services.WIRKUNG``."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        limit_choices_to={"rolle": "kind"},
    )
    gebucht_am = models.DateTimeField(default=timezone.now)
    bezugsdatum = models.DateField(db_index=True, help_text="Fachlicher Tag (Berlin)")
    art = models.CharField(max_length=20, choices=Art.choices)
    guthaben_delta = models.IntegerField()
    xp_delta = models.IntegerField()
    idempotenz_schluessel = models.CharField(max_length=120, unique=True)
    storno_von = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="storno",
        help_text="Originalbuchung dieser Gegenbuchung",
    )
    quelle_modul = models.CharField(max_length=40)
    referenz_typ = models.CharField(max_length=60, blank=True, default="")
    referenz_id = models.CharField(max_length=40, blank=True, default="")
    begruendung = models.CharField(max_length=200, blank=True, default="")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Leer = System/Job",
    )

    class Meta:
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"
        indexes = [
            models.Index(fields=["kind", "gebucht_am"], name="punkte_buchung_kind_idx"),
            models.Index(fields=["referenz_typ", "referenz_id"], name="punkte_buchung_ref_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(xp_delta__gte=0) | Q(art__in=XP_SENKEND),
                name="punkte_buchung_xp_nicht_negativ",
            ),
            models.CheckConstraint(
                condition=Q(art=Art.STORNO, storno_von__isnull=False)
                | (~Q(art=Art.STORNO) & Q(storno_von__isnull=True)),
                name="punkte_buchung_storno_mit_original",
            ),
            models.CheckConstraint(
                condition=~Q(guthaben_delta=0, xp_delta=0),
                name="punkte_buchung_nicht_leer",
            ),
        ]

    def __str__(self):
        return (
            f"{self.bezugsdatum} {self.get_art_display()} "
            f"G{self.guthaben_delta:+d} XP{self.xp_delta:+d}"
        )
