"""Datenmodell von lernen (SPEC 21, Etappe 1: Fundament ohne KI).

``Fach`` -> ``Thema`` (je Klassenstufe) -> ``Frage`` (Vokabel oder Frage). Pro Kind gibt es genau
eine ``Lernmappe``, beliebig viele ``Lernsitzung``en und je Fach eine ``Leistungsstufe``.
Namen von Fächern und Themen aus den Startdaten sind in der Datenmigration mit ``gettext_noop``
markiert (docs/i18n.md); von Eltern geänderte Namen bleiben unverändert.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class FrageTyp(models.TextChoices):
    VOKABEL = "vokabel", _("Vokabel")
    FRAGE = "frage", _("Frage")


class Quelle(models.TextChoices):
    SYSTEM = "system", _("Startdaten")
    ELTERN = "eltern", _("Eltern")
    KI = "ki", _("KI")


class Freigabe(models.TextChoices):
    OFFEN = "offen", _("wartet auf Freigabe")
    FREIGEGEBEN = "freigegeben", _("freigegeben")
    ABGELEHNT = "abgelehnt", _("abgelehnt")


class Intensitaet(models.TextChoices):
    AUFWAERMEN = "aufwaermen", _("Aufwärmen")
    NORMAL = "normal", _("Normal")
    HERAUSFORDERUNG = "herausforderung", _("Herausforderung")


class Selbsteinschaetzung(models.TextChoices):
    ZU_LEICHT = "zu_leicht", _("zu leicht")
    PASSEND = "passend", _("passend")
    ZU_SCHWER = "zu_schwer", _("zu schwer")


class Fach(models.Model):
    schluessel = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    reihenfolge = models.PositiveSmallIntegerField(default=0)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


class Thema(models.Model):
    fach = models.ForeignKey(Fach, on_delete=models.CASCADE, related_name="themen")
    # Klassenstufe des Lehrplans (nicht die Klasse eines Kindes); leer = stufenlos
    klassenstufe = models.PositiveSmallIntegerField(null=True, blank=True)
    name = models.CharField(max_length=80)
    reihenfolge = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["fach", "klassenstufe", "reihenfolge", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["fach", "klassenstufe", "name"], name="lernen_thema_eindeutig"
            )
        ]

    def __str__(self):
        return f"{self.fach_id}/{self.klassenstufe}/{self.name}"


class Frage(models.Model):
    """Eine Vokabel (``frage`` = Deutsch, ``antwort`` = Fremdsprache) oder eine Frage mit Antwort.
    Fragen aus KI oder Eltern gehören einem Kind (``kind``) und haben einen Freigabestatus;
    Startdaten (``quelle=system``) gehören niemandem und sind freigegeben."""

    thema = models.ForeignKey(Thema, on_delete=models.CASCADE, related_name="fragen")
    typ = models.CharField(max_length=10, choices=FrageTyp.choices, default=FrageTyp.FRAGE)
    frage = models.CharField(max_length=300)
    antwort = models.CharField(max_length=300)
    quelle = models.CharField(max_length=10, choices=Quelle.choices, default=Quelle.SYSTEM)
    freigabe = models.CharField(
        max_length=12, choices=Freigabe.choices, default=Freigabe.FREIGEGEBEN
    )
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="lernfragen",
    )
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["thema", "id"]
        indexes = [models.Index(fields=["thema", "freigabe"], name="lernen_frage_thema_frei")]
        constraints = [
            # Startdaten gehören keinem Kind
            models.CheckConstraint(
                condition=~Q(quelle="system") | Q(kind__isnull=True),
                name="lernen_frage_system_ohne_kind",
            )
        ]

    def __str__(self):
        return f"{self.frage} = {self.antwort}"


class Lernmappe(models.Model):
    """Genau eine je Kind. Sichtbar nur für das Kind und die Eltern, nie für Geschwister."""

    kind = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lernmappe"
    )
    erstellt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Lernmappe {self.kind_id}"


class Lernsitzung(models.Model):
    """Eine Übungseinheit. Gemessen wird nur, was die Rückschau und das Wochenbild brauchen."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lernsitzungen"
    )
    fach = models.ForeignKey(Fach, null=True, blank=True, on_delete=models.SET_NULL)
    beginn = models.DateTimeField()
    dauer_sekunden = models.PositiveIntegerField(default=0)
    versuche = models.PositiveIntegerField(default=0)
    intensitaet = models.CharField(
        max_length=16, choices=Intensitaet.choices, default=Intensitaet.NORMAL
    )
    # Höchste benutzte Hilfestufe (0 = keine Hilfe)
    hilfestufe_max = models.PositiveSmallIntegerField(default=0)
    selbsteinschaetzung = models.CharField(
        max_length=10, choices=Selbsteinschaetzung.choices, blank=True
    )
    rueckschau = models.TextField(blank=True)

    class Meta:
        ordering = ["-beginn"]
        indexes = [models.Index(fields=["kind", "beginn"], name="lernen_sitzung_kind_beginn")]

    def __str__(self):
        return f"Lernsitzung {self.kind_id} {self.beginn:%Y-%m-%d}"


class Leistungsstufe(models.Model):
    """Leistungsstufe und Klassenstufe eines Kindes in einem Fach. Tragen die Eltern im
    Einrichtungs-Assistenten ein (SPEC 21.8); die Bezeichnung ist frei (z. B. Grundniveau)."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leistungsstufen"
    )
    fach = models.ForeignKey(Fach, on_delete=models.CASCADE, related_name="leistungsstufen")
    stufe = models.CharField(max_length=40, blank=True)
    klassenstufe = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "fach"], name="lernen_stufe_je_kind_fach")
        ]

    def __str__(self):
        return f"{self.kind_id}/{self.fach_id}: {self.stufe}"
