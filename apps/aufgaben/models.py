"""Aufgaben: Kategorie, Vorlage (Bibliothek), Aufgabe (Definition + Plan), AufgabenInstanz,
Interesse (Reservierung/Konflikt) und Meldung (AP12). Nachweis-Fotos: AP13.
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.kern import zeit
from apps.kern.sprache import uebersetzt

from . import wiederholung
from .wiederholung import Plan

HEX_FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


class Freigabeart(models.TextChoices):
    VERTRAUEN = "vertrauen", gettext_lazy("Vertrauen (sofort gutgeschrieben)")
    ELTERN = "eltern", gettext_lazy("Eltern bestätigen")
    NACHWEIS = "nachweis", gettext_lazy("Foto-/Text-Nachweis")


class Status(models.TextChoices):
    AKTIV = "aktiv", gettext_lazy("Aktiv")
    PAUSIERT = "pausiert", gettext_lazy("Pausiert")
    BEENDET = "beendet", gettext_lazy("Beendet")


class Kategorie(models.Model):
    name = models.CharField(max_length=40, unique=True)
    symbol = models.CharField(max_length=60)
    farbe = models.CharField(max_length=7, blank=True)
    systemschluessel = models.SlugField(
        blank=True, help_text=gettext_lazy("Feste Kennung, z. B. 'schule' (Brücke zum Lernmodul).")
    )
    reihenfolge = models.SmallIntegerField(default=0)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["reihenfolge", "name"]
        verbose_name = gettext_lazy("Kategorie")
        verbose_name_plural = gettext_lazy("Kategorien")
        constraints = [
            models.UniqueConstraint(
                fields=["systemschluessel"],
                condition=~Q(systemschluessel=""),
                name="aufgaben_kategorie_schluessel_uniq",
            ),
        ]

    def __str__(self):
        return uebersetzt(self.name)

    def clean(self):
        if self.farbe and not HEX_FARBE.match(self.farbe):
            raise ValidationError({"farbe": _("Farbe im Format #rrggbb angeben.")})


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
        verbose_name = gettext_lazy("Vorlage")
        verbose_name_plural = gettext_lazy("Vorlagen")
        constraints = [
            models.CheckConstraint(condition=Q(punkte__gt=0), name="aufgaben_vorlage_punkte_pos"),
        ]

    def __str__(self):
        return uebersetzt(self.titel)

    @property
    def plan(self) -> Plan:
        return Plan.aus_json(self.wiederholung)

    def clean(self):
        if self.wiederholung:
            try:
                fehler = wiederholung.pruefen(self.plan)
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValidationError(
                    {"wiederholung": _("Ungültige Wiederholung: %(fehler)s") % {"fehler": exc}}
                ) from exc
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
        help_text=gettext_lazy(
            "Leer = offen für alle Kinder. Gesetzt = nur dieses Kind sieht die Aufgabe."
        ),
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
        null=True, blank=True, help_text=gettext_lazy("Leer = globaler Wert (Einstellungen)")
    )

    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    erstellt_am = models.DateTimeField(default=timezone.now)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["titel", "id"]
        verbose_name = gettext_lazy("Aufgabe")
        verbose_name_plural = gettext_lazy("Aufgaben")
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
        return uebersetzt(self.titel)

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
            fehler["zugewiesen_an"] = _("Zuweisung nur an ein Kind möglich.")
        if self.sonderpunkte_deckel_prozent is not None and self.sonderpunkte_deckel_prozent > 1000:
            fehler["sonderpunkte_deckel_prozent"] = _("Wert zu hoch.")
        if fehler:
            raise ValidationError(fehler)


class InstanzStatus(models.TextChoices):
    OFFEN = "offen", gettext_lazy("Offen")
    KONFLIKT = "konflikt", gettext_lazy("Mehrere Interessenten")
    RESERVIERT = "reserviert", gettext_lazy("Reserviert")
    GEMELDET = "gemeldet", gettext_lazy("Gemeldet")
    RUECKFRAGE = "rueckfrage", gettext_lazy("Rückfrage")
    BESTAETIGT = "bestaetigt", gettext_lazy("Bestätigt")
    ABGELEHNT = "abgelehnt", gettext_lazy("Abgelehnt")
    NICHT_UEBERNOMMEN = "nicht_uebernommen", gettext_lazy("Nicht übernommen")
    STORNIERT = "storniert", gettext_lazy("Storniert")
    NACHBESSERN = "nachbessern", gettext_lazy("Zum Nachbessern")


# Nicht abgeschlossene Zustände ("offen" im Sinne von K9: kein Stapel)
LAUFENDE_STATUS = (
    InstanzStatus.OFFEN,
    InstanzStatus.KONFLIKT,
    InstanzStatus.RESERVIERT,
    InstanzStatus.GEMELDET,
    InstanzStatus.RUECKFRAGE,
)


class AufgabenInstanz(models.Model):
    """Konkretes Vorkommen einer Aufgabe (DATA_MODEL 7.4).

    - ``plan_datum``: Plan-Tag, aus dem die Instanz erzeugt wurde. Unveränderlich, fachlicher
      Idempotenz-Schlüssel ``unique(aufgabe, plan_datum)``.
    - ``faellig_am``: wirksames Datum (Wochenplan/AP14 darf es verschieben).
    - Zeitgebunden = ``fenster_ende`` gesetzt. Ungebunden: höchstens eine laufende Instanz je
      Aufgabe (Teil-Unique, K9 "kein Stapel").
    - Statusübergänge nur per bedingtem Update in den Services.
    """

    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.PROTECT, related_name="instanzen")
    plan_datum = models.DateField(null=True, blank=True)
    faellig_am = models.DateField(null=True, blank=True)
    fenster_start = models.DateTimeField(null=True, blank=True)
    fenster_ende = models.DateTimeField(null=True, blank=True)
    titel_snapshot = models.CharField(max_length=80)
    punkte_snapshot = models.PositiveIntegerField()
    freigabeart_snapshot = models.CharField(max_length=10, choices=Freigabeart.choices)
    status = models.CharField(
        max_length=20, choices=InstanzStatus.choices, default=InstanzStatus.OFFEN
    )
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="aufgaben_instanzen",
        help_text="Aktueller Inhaber (ab Reservierung).",
    )
    reserviert_bis = models.DateTimeField(null=True, blank=True, db_index=True)
    erinnert_am = models.DateTimeField(null=True, blank=True)
    vorwarnung_am = models.DateTimeField(null=True, blank=True)
    bestaetigt_am = models.DateTimeField(null=True, blank=True)
    bestaetigt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    abgeschlossen_am = models.DateTimeField(
        null=True, blank=True, help_text="Zeitpunkt des Endzustands (K9: nächster Termin danach)."
    )
    gemeldet_am = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Erste Meldung 'erledigt' (K1: bestimmt Bezugsdatum/Woche der Aktivität).",
    )
    sonderpunkte = models.PositiveIntegerField(default=0)
    sonderpunkte_begruendung = models.CharField(max_length=200, blank=True, default="")
    geprueft_am = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Vertrauens-Aufgabe: von den Eltern durchgesehen ("Passt").',
    )
    geprueft_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    nachbessern_anzahl = models.PositiveSmallIntegerField(
        default=0,
        help_text="Wie oft zum Nachbessern zurückgegeben (Runde; Teil der Buchungsschlüssel).",
    )
    nachbessern_bis = models.DateTimeField(null=True, blank=True)
    nachbessern_grund = models.CharField(max_length=200, blank=True, default="")
    sortierung = models.IntegerField(default=0)
    erzeugt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["faellig_am", "sortierung", "id"]
        verbose_name = gettext_lazy("Aufgaben-Instanz")
        verbose_name_plural = gettext_lazy("Aufgaben-Instanzen")
        constraints = [
            models.UniqueConstraint(
                fields=["aufgabe", "plan_datum"],
                condition=Q(plan_datum__isnull=False),
                name="aufgaben_instanz_plan_uniq",
            ),
            models.UniqueConstraint(
                fields=["aufgabe"],
                condition=Q(
                    fenster_ende__isnull=True, status__in=LAUFENDE_STATUS, nachbessern_anzahl=0
                ),
                name="aufgaben_instanz_ungebunden_ein_laufend",
            ),
            models.CheckConstraint(
                condition=Q(fenster_ende__isnull=True)
                | Q(fenster_start__isnull=True)
                | Q(fenster_ende__gt=models.F("fenster_start")),
                name="aufgaben_instanz_fenster_gueltig",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "fenster_ende"], name="aufgaben_inst_status_ende"),
            models.Index(fields=["kind", "status"], name="aufgaben_inst_kind_status"),
            models.Index(fields=["faellig_am"], name="aufgaben_inst_faellig"),
        ]

    def __str__(self):
        return f"{self.titel_snapshot} ({self.faellig_am or _('ohne Termin')})"

    @property
    def zeitgebunden(self) -> bool:
        return self.fenster_ende is not None

    @property
    def verschoben(self) -> bool:
        """Manuell im Wochenplan verschoben (wirksames Datum ≠ Plan-Tag)."""
        return self.faellig_am != self.plan_datum


class InteresseStatus(models.TextChoices):
    AKTIV = "aktiv", gettext_lazy("Wartet auf Entscheidung")
    ZUGETEILT = "zugeteilt", gettext_lazy("Zugeteilt")
    VERDRAENGT = "verdraengt", gettext_lazy("Vergeben/gelöst")
    ZURUECKGEZOGEN = "zurueckgezogen", gettext_lazy("Zurückgegeben")
    ABGELAUFEN = "abgelaufen", gettext_lazy("Abgelaufen")


# Interesse zählt noch (Eindeutigkeit je Instanz und Kind)
INTERESSE_LAUFEND = (InteresseStatus.AKTIV, InteresseStatus.ZUGETEILT)


class Interesse(models.Model):
    """Ein Kind will eine Instanz übernehmen (DATA_MODEL 7.5).

    ``zugeteilt`` = Inhaber (direkt bei einem Interessenten oder durch Eltern bei Konflikt),
    ``aktiv`` = wartet im Konflikt auf die Eltern-Entscheidung.
    """

    instanz = models.ForeignKey(
        AufgabenInstanz, on_delete=models.CASCADE, related_name="interessen"
    )
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="aufgaben_interessen"
    )
    status = models.CharField(max_length=15, choices=InteresseStatus.choices)
    erstellt_am = models.DateTimeField(default=timezone.now)
    entschieden_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    geaendert_am = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["erstellt_am", "id"]
        verbose_name = gettext_lazy("Interesse")
        verbose_name_plural = gettext_lazy("Interessen")
        constraints = [
            models.UniqueConstraint(
                fields=["instanz", "kind"],
                condition=Q(status__in=INTERESSE_LAUFEND),
                name="aufgaben_interesse_laufend_uniq",
            ),
        ]
        indexes = [models.Index(fields=["kind", "status"], name="aufgaben_int_kind_status")]

    def __str__(self):
        return f"{self.kind} -> {self.instanz} ({self.status})"


class MeldungStatus(models.TextChoices):
    OFFEN = "offen", gettext_lazy("Wartet auf Bestätigung")
    RUECKFRAGE = "rueckfrage", gettext_lazy("Rückfrage")
    BESTAETIGT = "bestaetigt", gettext_lazy("Bestätigt")
    ABGELEHNT = "abgelehnt", gettext_lazy("Abgelehnt")


MELDUNG_LAUFEND = (MeldungStatus.OFFEN, MeldungStatus.RUECKFRAGE)


class Meldung(models.Model):
    """Kind meldet "erledigt" (DATA_MODEL 7.6). Texte sind Nachweis-Inhalte: Sie werden beim
    Abschluss (Bestätigung/Ablehnung) geleert, nur der Vermerk ``nachweis_geloescht_am`` bleibt.
    Fotos (``Nachweis``) kommen mit AP13 und hängen an der Meldung.
    """

    instanz = models.ForeignKey(AufgabenInstanz, on_delete=models.CASCADE, related_name="meldungen")
    kind = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    gemeldet_am = models.DateTimeField(default=timezone.now)
    text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=MeldungStatus.choices, default=MeldungStatus.OFFEN
    )
    rueckfrage_text = models.CharField(max_length=300, blank=True, default="")
    antwort_text = models.TextField(blank=True, default="")
    entschieden_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    entschieden_am = models.DateTimeField(null=True, blank=True)
    nachweis_geloescht_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["gemeldet_am", "id"]
        verbose_name = gettext_lazy("Meldung")
        verbose_name_plural = gettext_lazy("Meldungen")
        constraints = [
            models.UniqueConstraint(
                fields=["instanz"],
                condition=Q(status__in=MELDUNG_LAUFEND),
                name="aufgaben_meldung_eine_offene",
            ),
        ]

    def __str__(self):
        return f"Meldung {self.instanz} ({self.status})"
