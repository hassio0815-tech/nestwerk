"""Datenmodell von avatar (DATA_MODEL 9): Thema, Slot, ModDefinition, Avatar, RenderCache.

ModSet und ModBesitz (Kauf, Bauzeit) folgen mit AP26. ``ModDefinition.seltenheit`` ist hier eine
Zahl 1-6; die Kopplung an ``spielregeln.Rang`` (Preis und Bauzeit je Rang) macht AP26.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.kern import zeit


class Thema(models.Model):
    schluessel = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=40)
    beschreibung = models.CharField(max_length=200, blank=True)
    palette = models.JSONField(default=dict)
    figur_varianten = models.JSONField(default=list, help_text="Wählbare Frisuren")
    bau_inszenierung = models.CharField(max_length=40, default="keine")
    daten = models.JSONField(default=dict, help_text="Kleidung, Grundausstattung, Formen")
    nur_eltern = models.BooleanField(default=False)
    aktiv = models.BooleanField(default=True)
    reihenfolge = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ["reihenfolge", "schluessel"]

    def __str__(self):
        return self.name

    def als_dict(self):
        """Thema in der Form, die der Renderer erwartet (``zustand['thema_daten']``)."""
        return {
            "schluessel": self.schluessel,
            "name": self.name,
            "beschreibung": self.beschreibung,
            "palette": self.palette,
            "bau_inszenierung": self.bau_inszenierung,
            "nur_eltern": self.nur_eltern,
            "reihenfolge": self.reihenfolge,
            **self.daten,
        }


class Slot(models.Model):
    schluessel = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=40)
    ebene = models.SmallIntegerField(unique=True)

    class Meta:
        ordering = ["ebene"]

    def __str__(self):
        return self.name


class ModDefinition(models.Model):
    schluessel = models.SlugField(max_length=60, unique=True)
    thema = models.ForeignKey(Thema, on_delete=models.PROTECT, related_name="mods")
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="mods")
    seltenheit = models.SmallIntegerField()
    name = models.CharField(max_length=60)
    beschreibung = models.CharField(max_length=200, blank=True)
    preis = models.IntegerField(null=True, blank=True, help_text="Leer = Standardpreis des Rangs")
    bauzeit_stunden = models.IntegerField(
        null=True, blank=True, help_text="Leer = Standard des Rangs"
    )
    bauplan = models.JSONField(default=dict, help_text='{"teile": [...]}')
    svg_override = models.TextField(blank=True, help_text="Whitelist-geprüft")
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["thema__reihenfolge", "seltenheit", "slot__ebene"]
        constraints = [
            models.UniqueConstraint(
                fields=["thema", "slot", "seltenheit"], name="avatar_mod_thema_slot_seltenheit"
            ),
            models.CheckConstraint(
                condition=Q(seltenheit__gte=1, seltenheit__lte=6), name="avatar_mod_seltenheit_1_6"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.thema_id}/{self.slot_id}/{self.seltenheit})"

    def render_mod(self):
        """Mod in der Form, die der Renderer erwartet."""
        return {
            "teile": (self.bauplan or {}).get("teile", []),
            "svg_override": self.svg_override or None,
        }

    def clean(self):
        from django.core.exceptions import ValidationError

        from .generator import svgsicher

        if self.svg_override:
            meldung = svgsicher.svg_pruefen(self.svg_override)
            if meldung:
                raise ValidationError({"svg_override": meldung})


class Avatar(models.Model):
    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="avatar",
    )
    thema = models.ForeignKey(Thema, on_delete=models.PROTECT, related_name="avatare")
    figur = models.JSONField(default=dict, help_text="haut, haar, frisur")
    angelegt = models.JSONField(
        default=dict, help_text="{slot: mod-schluessel}; nur fertige Mods (AP26 prüft den Besitz)"
    )
    render_hash = models.CharField(max_length=64, blank=True)
    thema_gewaehlt_am = models.DateTimeField(default=zeit.jetzt)

    def __str__(self):
        return f"Avatar von {self.benutzer_id}"


class RenderCache(models.Model):
    hash = models.CharField(max_length=64, primary_key=True)
    svg = models.TextField()
    erstellt_am = models.DateTimeField(default=zeit.jetzt)
    zuletzt_genutzt = models.DateTimeField(default=zeit.jetzt, db_index=True)

    def __str__(self):
        return self.hash[:12]
