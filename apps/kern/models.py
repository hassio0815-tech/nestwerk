"""Modelle von kern (DATA_MODEL 1). Zugriff von außen nur über die Module von kern,
nie direkt über diese Modelle.

Die FKs auf ``konten.Benutzer``/``konten.Geraet`` sind per String-Referenz gesetzt (kern
importiert konten nicht, Schichtenregel).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from .db import NurEinfuegenModell


class Einstellung(models.Model):
    """Wert einer Einstellung. Definition (Typ, Validierung) liegt in der Registry
    (``kern.einstellungen``), der Wert nur hier."""

    schluessel = models.CharField(max_length=100, primary_key=True)
    wert = models.JSONField()
    modul = models.CharField(max_length=40, db_index=True)
    geaendert_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Einstellung"
        verbose_name_plural = "Einstellungen"

    def __str__(self):
        return f"{self.schluessel} = {self.wert!r}"


class Rolle(models.TextChoices):
    ELTERN = "eltern", "Eltern"
    KIND = "kind", "Kind"
    SYSTEM = "system", "System"


OBJEKT_ID_MAX = 100


class AuditEintrag(NurEinfuegenModell):
    """Protokoll (insert-only). Nie sensible Inhalte (PIN, Passwort, Nachweis-Inhalte)."""

    zeit = models.DateTimeField(default=timezone.now, db_index=True)
    akteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Leer = System/Job",
    )
    akteur_name = models.CharField(max_length=80)
    rolle = models.CharField(max_length=10, choices=Rolle.choices)
    aktion = models.CharField(max_length=80, db_index=True)
    objekt_typ = models.CharField(max_length=60, blank=True, default="")
    # 100 = Länge von ``Einstellung.schluessel`` (Audit-Objekt "kern.einstellung")
    objekt_id = models.CharField(max_length=OBJEKT_ID_MAX, blank=True, default="")
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Betroffenes Kind",
    )
    details = models.JSONField(default=dict)
    geraet = models.ForeignKey(
        "konten.Geraet", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "Audit-Eintrag"
        verbose_name_plural = "Audit-Einträge"
        indexes = [models.Index(fields=["objekt_typ", "objekt_id"], name="kern_audit_objekt_idx")]

    def __str__(self):
        return f"{self.zeit:%Y-%m-%d %H:%M} {self.akteur_name}: {self.aktion}"


class JobSperre(models.Model):
    """Lease gegen Parallel-Läufe eines Jobs. Abgelaufen (``gehalten_bis <= jetzt``) = frei."""

    name = models.CharField(max_length=60, primary_key=True)
    inhaber = models.CharField(max_length=80)
    gehalten_bis = models.DateTimeField()

    class Meta:
        verbose_name = "Job-Sperre"
        verbose_name_plural = "Job-Sperren"

    def __str__(self):
        return f"{self.name} ({self.inhaber} bis {self.gehalten_bis:%Y-%m-%d %H:%M})"


class JobStatus(models.TextChoices):
    LAEUFT = "laeuft", "läuft"
    OK = "ok", "ok"
    FEHLER = "fehler", "Fehler"
    UEBERSPRUNGEN = "uebersprungen", "übersprungen"


class JobLauf(models.Model):
    name = models.CharField(max_length=60)
    gestartet_am = models.DateTimeField(default=timezone.now)
    beendet_am = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=JobStatus.choices)
    info = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Job-Lauf"
        verbose_name_plural = "Job-Läufe"
        indexes = [models.Index(fields=["name", "gestartet_am"], name="kern_joblauf_name_idx")]

    def __str__(self):
        return f"{self.name} {self.gestartet_am:%Y-%m-%d %H:%M} {self.status}"
