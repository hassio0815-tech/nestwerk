"""Stammdaten der Aufgaben: Kategorie, Vorlage (Bibliothek), Aufgabe (Definition + Plan).

Instanzen, Reservierung, Meldung gehören zu AP11/AP12.
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.kern import zeit

from . import wiederholung
from .wiederholung import Plan

HEX_FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


class Freigabeart(models.TextChoices):
    VERTRAUEN = "vertrauen", "Vertrauen (sofort gutgeschrieben)"
    ELTERN = "eltern", "Eltern bestätigen"
    NACHWEIS = "nachweis", "Foto-/Text-Nachweis"


class Status(models.TextChoices):
    AKTIV = "aktiv", "Aktiv"
    PAUSIERT = "pausiert", "Pausiert"
    BEENDET = "beendet", "Beendet"


class Kategorie(models.Model):
    name = models.CharField(max_length=40, unique=True)
    symbol = models.CharField(max_length=60)
    farbe = models.CharField(max_length=7, blank=True)
    systemschluessel = models.SlugField(
        blank=True, help_text="Feste Kennung, z. B. 'schule' (Brücke zum Lernmodul)."
    )
    reihenfolge = models.SmallIntegerField(default=0)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["reihenfolge", "name"]
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"
        constraints = [
            models.UniqueConstraint(
                fields=["systemschluessel"],
                condition=~Q(systemschluessel=""),
                name="aufgaben_kategorie_schluessel_uniq",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.farbe and not HEX_FARBE.match(self.farbe):
            raise ValidationError({"farbe": "Farbe im Format #rrggbb angeben."})


class Vorlage(models.Model):
    titel = models.CharField(max_length=80)
    beschreibung = models.TextField(blank=True)
    punkte = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    freigabeart = models.CharField(max_length=10, choices=Freigabeart.choices)
    kategorie = models.ForeignKey(
        Kategorie, null=True, blank=True, on_delete=models.PROTECT, related_name="vorlagen"
    )
    wiederholung = models.JSONField(null=True, blank=True, help_text="Struktur wie Plan.als_json")
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["kategorie__reihenfolge", "titel"]
        verbose_name = "Vorlage"
        verbose_name_plural = "Vorlagen"
        constraints = [
            models.CheckConstraint(condition=Q(punkte__gt=0), name="aufgaben_vorlage_punkte_pos"),
        ]

    def __str__(self):
        return self.titel

    @property
    def plan(self) -> Plan:
        return Plan.aus_json(self.wiederholung)

    def clean(self):
        if self.wiederholung:
            try:
                fehler = wiederholung.pruefen(self.plan)
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValidationError({"wiederholung": f"Ungültige Wiederholung: {exc}"}) from exc
            if fehler:
                raise ValidationError({"wiederholung": " ".join(fehler.values())})


class Aufgabe(models.Model):
    titel = models.CharField(max_length=80)
    punkte = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    beschreibung = models.TextField(blank=True)
    freigabeart = models.CharField(
        max_length=10, choices=Freigabeart.choices, default=Freigabeart.ELTERN
    )
    kategorie = models.ForeignKey(
        Kategorie, null=True, blank=True, on_delete=models.PROTECT, related_name="aufgaben"
    )
    vorlage = models.ForeignKey(
        Vorlage, null=True, blank=True, on_delete=models.SET_NULL, related_name="aufgaben"
    )
    zugewiesen_an = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="zugewiesene_aufgaben",
        limit_choices_to={"rolle": "kind"},
        help_text="Leer = offen für alle Kinder. Gesetzt = nur dieses Kind sieht die Aufgabe.",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.AKTIV, db_index=True
    )

    wiederholungsart = models.CharField(
        max_length=12, choices=wiederholung.ARTEN, default=wiederholung.EINMALIG
    )
    wochentage = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Bitmaske, Bit 0 = Montag"
    )
    intervall_tage = models.PositiveSmallIntegerField(null=True, blank=True)
    start_datum = models.DateField(null=True, blank=True, default=zeit.heute)
    end_datum = models.DateField(null=True, blank=True)
    fenster_von = models.TimeField(null=True, blank=True)
    fenster_bis = models.TimeField(null=True, blank=True)
    fenster_tage = models.PositiveSmallIntegerField(null=True, blank=True)
    limit_anzahl = models.PositiveSmallIntegerField(null=True, blank=True)
    limit_zeitraum = models.CharField(max_length=5, blank=True, choices=wiederholung.ZEITRAEUME)
    sonderpunkte_deckel_prozent = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Leer = globaler Wert (Einstellungen)"
    )

    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    erstellt_am = models.DateTimeField(default=timezone.now)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["titel", "id"]
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben"
        constraints = [
            models.CheckConstraint(condition=Q(punkte__gt=0), name="aufgaben_aufgabe_punkte_pos"),
            models.CheckConstraint(
                condition=Q(intervall_tage__isnull=True) | Q(intervall_tage__gte=1),
                name="aufgaben_aufgabe_intervall_pos",
            ),
            models.CheckConstraint(
                condition=Q(end_datum__isnull=True)
                | Q(start_datum__isnull=True)
                | Q(end_datum__gte=models.F("start_datum")),
                name="aufgaben_aufgabe_ende_nach_start",
            ),
            models.CheckConstraint(
                condition=(
                    Q(limit_anzahl__isnull=True, limit_zeitraum="")
                    | (Q(limit_anzahl__gte=1) & ~Q(limit_zeitraum=""))
                ),
                name="aufgaben_aufgabe_limit_paar",
            ),
        ]

    def __str__(self):
        return self.titel

    @property
    def plan(self) -> Plan:
        """Wiederholungs-/Zeitplan für die Instanz-Erzeugung (AP11)."""
        return Plan(
            art=self.wiederholungsart,
            wochentage=self.wochentage,
            intervall_tage=self.intervall_tage,
            start_datum=self.start_datum,
            end_datum=self.end_datum,
            fenster_von=self.fenster_von,
            fenster_bis=self.fenster_bis,
            fenster_tage=self.fenster_tage,
            limit_anzahl=self.limit_anzahl,
            limit_zeitraum=self.limit_zeitraum,
        )

    @property
    def zeitgebunden(self) -> bool:
        return self.fenster_bis is not None

    def clean(self):
        fehler = wiederholung.pruefen(self.plan)
        if self.zugewiesen_an_id and self.zugewiesen_an.rolle != "kind":
            fehler["zugewiesen_an"] = "Zuweisung nur an ein Kind möglich."
        if self.sonderpunkte_deckel_prozent is not None and self.sonderpunkte_deckel_prozent > 1000:
            fehler["sonderpunkte_deckel_prozent"] = "Wert zu hoch."
        if fehler:
            raise ValidationError(fehler)
