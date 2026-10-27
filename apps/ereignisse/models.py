"""Modelle von ereignisse (DATA_MODEL 4). Zugriff von außen nur über ``services``,
``selectors`` und ``registry``.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy


class Zielgruppe(models.TextChoices):
    ELTERN = "eltern", gettext_lazy("Eltern")
    KIND = "kind", gettext_lazy("Kind")
    BEIDE = "beide", gettext_lazy("Eltern und Kind")
    INTERN = "intern", gettext_lazy("intern")


class EreignisTyp(models.Model):
    """Katalog-Eintrag. Definition im Code (``registry.typ_deklarieren``), Sync bei
    ``post_migrate``; Bezeichnung, Zielgruppe, Kanäle, TTL und ``aktiv`` sind in der DB
    editierbar und werden vom Sync nie überschrieben."""

    slug = models.CharField(max_length=80, primary_key=True)
    modul = models.CharField(max_length=40)
    bezeichnung = models.CharField(max_length=120)
    zielgruppe = models.CharField(max_length=10, choices=Zielgruppe.choices)
    standard_kanaele = models.JSONField(default=list)
    deep_link_muster = models.CharField(max_length=200, blank=True, default="")
    push_ttl_sekunden = models.PositiveIntegerField(default=86400)
    aktiv = models.BooleanField(default=True)

    class Meta:
        verbose_name = gettext_lazy("Ereignistyp")
        verbose_name_plural = gettext_lazy("Ereignistypen")

    def __str__(self):
        return self.slug


class Ereignis(models.Model):
    """Outbox-Zeile. Entsteht in der Transaktion der Fachänderung (Rollback = kein Ereignis)."""

    typ = models.ForeignKey(EreignisTyp, on_delete=models.PROTECT, related_name="+")
    zeit = models.DateTimeField(default=timezone.now)
    akteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Wer das Ereignis ausgelöst hat; leer = System/Job",
    )
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Betroffenes Kind",
    )
    daten = models.JSONField(default=dict)
    # NULL statt "": Teil-Unique gilt nur für gesetzte Schlüssel
    schluessel = models.CharField(max_length=150, null=True, blank=True)  # noqa: DJ001
    verteilt = models.BooleanField(default=False)

    class Meta:
        verbose_name = gettext_lazy("Ereignis")
        verbose_name_plural = gettext_lazy("Ereignisse")
        indexes = [
            models.Index(fields=["typ", "zeit"], name="ereignisse_typ_zeit_idx"),
            models.Index(fields=["kind"], name="ereignisse_kind_idx"),
            models.Index(
                fields=["id"], condition=Q(verteilt=False), name="ereignisse_unverteilt_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["schluessel"],
                condition=Q(schluessel__isnull=False),
                name="ereignisse_schluessel_uniq",
            )
        ]

    def __str__(self):
        return f"#{self.pk} {self.typ_id}"


class Status(models.TextChoices):
    OFFEN = "offen", gettext_lazy("offen")
    OK = "ok", gettext_lazy("ok")
    FEHLER = "fehler", gettext_lazy("Fehler (Retry geplant)")
    AUFGEGEBEN = "aufgegeben", gettext_lazy("aufgegeben")


class EreignisVerarbeitung(models.Model):
    """Ein asynchroner Handler je Ereignis. ``unique(ereignis, handler)`` = genau einmal."""

    ereignis = models.ForeignKey(Ereignis, on_delete=models.CASCADE, related_name="+")
    handler = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFEN)
    versuche = models.PositiveSmallIntegerField(default=0)
    naechster_versuch = models.DateTimeField(null=True, blank=True, default=timezone.now)
    letzter_fehler = models.TextField(blank=True, default="")
    erledigt_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Ereignis-Verarbeitung")
        verbose_name_plural = gettext_lazy("Ereignis-Verarbeitungen")
        indexes = [
            models.Index(fields=["status", "naechster_versuch"], name="ereignisse_vera_faellig_idx")
        ]
        constraints = [
            models.UniqueConstraint(fields=["ereignis", "handler"], name="ereignisse_vera_uniq")
        ]

    def __str__(self):
        return f"{self.ereignis_id}/{self.handler}: {self.status}"


class WorkerHerzschlag(models.Model):
    """Lebenszeichen des Worker-Prozesses (Healthcheck, Systemstatus)."""

    name = models.CharField(max_length=60, primary_key=True)
    inhaber = models.CharField(max_length=80)
    zuletzt = models.DateTimeField()

    class Meta:
        verbose_name = gettext_lazy("Worker-Herzschlag")
        verbose_name_plural = gettext_lazy("Worker-Herzschläge")

    def __str__(self):
        return f"{self.name} ({self.inhaber}, {self.zuletzt:%Y-%m-%d %H:%M:%S})"
