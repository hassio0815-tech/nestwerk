"""Modelle von spielregeln (DATA_MODEL 6.1–6.7, AP20/AP22).

- ``Aktivitaet`` und ``Pause`` sind die **Historie** (Fakten).
- ``RangAufstieg`` ist ein **dauerhafter Fakt** (nie zurückgenommen, ARCHITECTURE 7.1/7.4).
- ``Rang`` und ``Kalibrierung`` sind Konfiguration (Eltern, Audit).
- ``Wochenauswertung`` und ``KindStand`` sind **Zwischenspeicher**: jederzeit aus der Historie
  neu berechenbar (``manage.py spielregeln_neuberechnen``, ARCHITECTURE 7.1).
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


class Rang(models.Model):
    """Rangstufe = Seltenheit (SPEC 6.2/18.1, Entscheidung 14). Name umbenennbar; Schwellen und
    Mindestwochen steigen mit der Stufe (Service prüft). Die niedrigste Stufe ist der Startrang."""

    stufe = models.PositiveSmallIntegerField(unique=True)
    schluessel = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=40)
    xp_schwelle = models.PositiveIntegerField()
    min_aktive_wochen = models.PositiveSmallIntegerField()
    mod_preis = models.PositiveIntegerField()
    bauzeit_stunden = models.PositiveIntegerField()
    farbe = models.CharField(max_length=7)
    ist_endstufe = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Rang"
        verbose_name_plural = "Ränge"
        ordering = ["stufe"]
        constraints = [
            models.UniqueConstraint(
                fields=["ist_endstufe"],
                condition=Q(ist_endstufe=True),
                name="spielregeln_rang_eine_endstufe",
            )
        ]

    def __str__(self):
        return f"{self.stufe} {self.name}"

    @property
    def selten(self):
        """Wert für ``data-selten`` (Designsystem: common … legendary, god)."""
        return "god" if self.schluessel == "godmode" else self.schluessel


class Kalibrierung(models.Model):
    """Kalibrierungsfaktoren (K3, DATA_MODEL 6.2): ``kind = NULL`` = global (genau eine Zeile).
    Wirksamer Faktor = global x Kind. AP22 nutzt ``faktor_schwelle`` (XP-Schwellen), Preis und
    Bauzeit folgen mit AP26."""

    kind = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="kalibrierung",
    )
    faktor_schwelle = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    faktor_preis = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    faktor_bauzeit = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    notiz = models.CharField(max_length=200, blank=True, default="")
    geaendert_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    geaendert_am = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Kalibrierung"
        verbose_name_plural = "Kalibrierungen"
        constraints = [
            models.UniqueConstraint(
                Coalesce("kind", Value("global"), output_field=models.CharField()),
                name="spielregeln_kalibrierung_eine_globale",
            ),
            models.CheckConstraint(
                condition=Q(faktor_schwelle__gte=0.25, faktor_schwelle__lte=4)
                & Q(faktor_preis__gte=0.25, faktor_preis__lte=4)
                & Q(faktor_bauzeit__gte=0.25, faktor_bauzeit__lte=4),
                name="spielregeln_kalibrierung_bereich",
            ),
        ]

    def __str__(self):
        return f"Kalibrierung {self.kind_id or 'global'}: {self.faktor_schwelle}"


class RangAufstieg(models.Model):
    """Fakt "Kind hat Rang erreicht" (unique je Kind+Rang). Bleibt, auch wenn Schwellen später
    steigen oder XP durch Korrektur sinken (K2). Mehrfachsprung = je Stufe ein Eintrag."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rangaufstiege"
    )
    rang = models.ForeignKey(Rang, on_delete=models.PROTECT, related_name="aufstiege")
    erreicht_am = models.DateTimeField(default=timezone.now)
    xp_bei_aufstieg = models.IntegerField()
    aktive_wochen_bei_aufstieg = models.PositiveIntegerField()
    schwelle_bei_aufstieg = models.PositiveIntegerField(help_text="wirksame XP-Schwelle")

    class Meta:
        verbose_name = "Rangaufstieg"
        verbose_name_plural = "Rangaufstiege"
        constraints = [
            models.UniqueConstraint(fields=["kind", "rang"], name="spielregeln_rangaufstieg_idem")
        ]

    def __str__(self):
        return f"{self.kind_id} -> {self.rang_id}"


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
    """Zwischenspeicher je Kind (DATA_MODEL 6.6). ``rang`` = höchster erreichter Rang (aus den
    ``RangAufstieg``-Fakten, sonst Startrang).

    ``wochenserie``/``aktive_wochen_gesamt``/``rekord_wochenserie``: Stand nach der letzten
    finalisierten Woche. ``tagesserie``/``rekord_tagesserie``: Stand am ``stand_datum``.
    """

    kind = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="spielstand",
    )
    rang = models.ForeignKey(
        Rang, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
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
