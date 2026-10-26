"""Datenmodell von avatar (DATA_MODEL 9): Thema, Slot, ModSet, ModDefinition, Avatar, ModBesitz,
RenderCache.

``ModDefinition.seltenheit`` ist eine Zahl 1-6 = ``spielregeln.Rang.stufe`` (Preis und Bauzeit
je Rang, AP26). ``ModBesitz`` ist Kauf + Bauauftrag + Besitz in einem (DATA_MODEL 9.6).
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


class ModSet(models.Model):
    """God-Mode-Set je 26-Wochen-Zyklus (DATA_MODEL 9.3, O3): ``nummer`` 1, 2, … = Zyklus.
    Die 6 Mods (1 je Slot) entstehen aus den Seltenheit-6-Bauplänen des Themas (AP27)."""

    thema = models.ForeignKey(Thema, on_delete=models.PROTECT, related_name="modsets")
    nummer = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=60)

    class Meta:
        verbose_name = "Mod-Set"
        verbose_name_plural = "Mod-Sets"
        ordering = ["thema__reihenfolge", "nummer"]
        constraints = [
            models.UniqueConstraint(fields=["thema", "nummer"], name="avatar_modset_thema_nummer"),
            models.CheckConstraint(condition=Q(nummer__gte=1), name="avatar_modset_nummer_ab_1"),
        ]

    def __str__(self):
        return self.name


class ModDefinition(models.Model):
    schluessel = models.SlugField(max_length=60, unique=True)
    thema = models.ForeignKey(Thema, on_delete=models.PROTECT, related_name="mods")
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="mods")
    seltenheit = models.SmallIntegerField()
    modset = models.ForeignKey(
        ModSet,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mods",
        help_text="Nur God-Mode-Zyklus-Sets (AP27)",
    )
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
                fields=["thema", "slot", "seltenheit"],
                condition=Q(modset__isnull=True),
                name="avatar_mod_thema_slot_seltenheit",
            ),
            models.UniqueConstraint(
                fields=["thema", "slot", "modset"],
                condition=Q(modset__isnull=False),
                name="avatar_mod_thema_slot_modset",
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
        default=dict, help_text="{slot: mod-schluessel}; nur fertige, eigene Mods (AP26)"
    )
    name = models.CharField(
        max_length=20, blank=True, default="", help_text="Name der Figur (optional, höchstens 20 Zeichen)"
    )
    render_hash = models.CharField(max_length=64, blank=True)
    thema_gewaehlt_am = models.DateTimeField(default=zeit.jetzt)

    def __str__(self):
        return f"Avatar von {self.benutzer_id}"


class BesitzStatus(models.TextChoices):
    IM_BAU = "im_bau", "im Bau"
    FERTIG = "fertig", "fertig"
    VERLOREN = "verloren", "verloren"
    EINGEFROREN = "eingefroren", "in der Ruhmeshalle"


AKTIV = (BesitzStatus.IM_BAU, BesitzStatus.FERTIG)


class ModBesitz(models.Model):
    """Gekaufter Mod eines Kindes (DATA_MODEL 9.6): ``im_bau`` bis ``fertig_geplant_am``, dann
    ``fertig`` (Job ``mods_fertigstellen``); Themenwechsel -> ``verloren`` (keine Erstattung).

    ``zaehlt_ab_iso_*``: Woche, ab der der Mod für die Ausbaustufe zählt (Zeitbremse, höchstens
    ``avatar.max_zaehlende_mods_woche`` neue zählende Mods je ISO-Woche, Warteschlange)."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mod_besitz"
    )
    mod = models.ForeignKey(ModDefinition, on_delete=models.PROTECT, related_name="besitz")
    preis_bezahlt = models.PositiveIntegerField()
    bauzeit_stunden = models.PositiveIntegerField(help_text="Snapshot beim Kauf")
    buchung = models.OneToOneField(
        "punkte.Buchung", on_delete=models.PROTECT, related_name="+", help_text="Mod-Kauf"
    )
    gekauft_am = models.DateTimeField(default=zeit.jetzt)
    fertig_geplant_am = models.DateTimeField(db_index=True)
    fertig_am = models.DateTimeField(null=True, blank=True)
    zaehlt_ab_iso_jahr = models.SmallIntegerField(null=True, blank=True)
    zaehlt_ab_iso_woche = models.SmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=BesitzStatus.choices, default=BesitzStatus.IM_BAU
    )
    verloren_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Mod-Besitz"
        verbose_name_plural = "Mod-Besitz"
        ordering = ["gekauft_am", "id"]
        indexes = [
            models.Index(fields=["kind", "status"], name="avatar_besitz_kind_status"),
            models.Index(
                fields=["kind", "zaehlt_ab_iso_jahr", "zaehlt_ab_iso_woche"],
                name="avatar_besitz_zaehlwoche",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "mod"],
                condition=Q(status__in=["im_bau", "fertig"]),
                name="avatar_besitz_kein_doppelkauf",
            ),
            models.CheckConstraint(
                condition=Q(status="im_bau") | Q(fertig_am__isnull=False) | Q(status="verloren"),
                name="avatar_besitz_fertig_mit_zeit",
            ),
        ]

    def __str__(self):
        return f"{self.kind_id} {self.mod_id} {self.status}"


WIDMUNG_MAX = 140


class RuhmeshallenEintrag(models.Model):
    """Ein Held in der Ruhmeshalle (Entscheidung 33): der fertig ausgebaute Avatar, eingefroren
    mit allem, was zum Zeichnen nötig ist (Thema-Daten, angelegte Mods, Figur). Unveränderlich
    bis auf die Widmung der Eltern; Löschen ist nicht möglich. ``themenstart`` (Start des Baus)
    ist je Kind eindeutig: ein Doppelklick erzeugt keinen zweiten Eintrag."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ruhmeshalle"
    )
    thema = models.ForeignKey(Thema, on_delete=models.PROTECT, related_name="ruhmeshalle")
    thema_daten = models.JSONField(default=dict, help_text="Snapshot für den Renderer")
    mods = models.JSONField(
        default=dict, help_text="Snapshot {slot: {schluessel, name, seltenheit, teile, ...}}"
    )
    figur = models.JSONField(default=dict)
    avatar_name = models.CharField(
        max_length=20, blank=True, default="", help_text="Snapshot des Figurennamens beim Einfrieren"
    )
    rang_stufe = models.PositiveSmallIntegerField()
    rang_name = models.CharField(max_length=40)
    rang_selten = models.CharField(max_length=20, help_text="Seltenheitsfarbe des Sockels")
    themenstart = models.DateTimeField()
    erstellt_am = models.DateTimeField(default=zeit.jetzt)
    bauzeit_wochen = models.PositiveSmallIntegerField()
    anzahl_mods = models.PositiveSmallIntegerField()
    aufgaben_anzahl = models.PositiveIntegerField()
    widmung = models.CharField(max_length=WIDMUNG_MAX, blank=True, default="")
    widmung_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    widmung_am = models.DateTimeField(null=True, blank=True)

    VERAENDERBAR = frozenset({"widmung", "widmung_von", "widmung_am"})

    class Meta:
        verbose_name = "Ruhmeshallen-Eintrag"
        verbose_name_plural = "Ruhmeshallen-Einträge"
        ordering = ["erstellt_am", "id"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "themenstart"], name="avatar_halle_einmalig"),
        ]

    def __str__(self):
        return f"{self.kind_id} {self.thema_id} {self.erstellt_am:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            felder = kwargs.get("update_fields")
            if felder is None or not set(felder) <= self.VERAENDERBAR:
                raise ValueError("Ruhmeshallen-Einträge sind unveränderlich (nur die Widmung)")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Ruhmeshallen-Einträge werden nie gelöscht")

    def render_zustand(self):
        """Render-Eingabe aus dem Snapshot (unabhängig von späteren Änderungen am Thema)."""
        return {
            "thema": self.thema_daten.get("schluessel", self.thema.schluessel),
            "thema_daten": self.thema_daten,
            "figur": self.figur,
            "mods": {
                slot: {"teile": m.get("teile", []), "svg_override": m.get("svg_override")}
                for slot, m in self.mods.items()
            },
        }


class RenderCache(models.Model):
    hash = models.CharField(max_length=64, primary_key=True)
    svg = models.TextField()
    erstellt_am = models.DateTimeField(default=zeit.jetzt)
    zuletzt_genutzt = models.DateTimeField(default=zeit.jetzt, db_index=True)

    def __str__(self):
        return self.hash[:12]
