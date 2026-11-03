"""Datenmodell von lernen (SPEC 21; Etappe 1 Fundament, Etappe 2 Üben ohne KI).

``Fach`` -> ``Thema`` (je Klassenstufe) -> ``Frage`` (Vokabel oder Frage). Pro Kind gibt es genau
eine ``Lernmappe``, beliebig viele ``Lernsitzung``en und je Fach eine ``Leistungsstufe``.
Namen von Fächern und Themen aus den Startdaten sind in der Datenmigration mit ``gettext_noop``
markiert (docs/i18n.md); von Eltern geänderte Namen bleiben unverändert.

Etappe 2 ergänzt ``Lernstand`` (Abstandswiederholung je Kind, Frage und Richtung), ``Versuch``
(jede Antwort einer Lernsitzung), ``Lerntag`` (Tagesbilanz), ``Lernziel`` (angepasstes Tagesziel)
und ``Lernpause`` (Schonung). Alles additiv zu Etappe 1.
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


class Vorhaben(models.TextChoices):
    """Was sich das Kind vor dem Üben vornimmt (SPEC 21.2, Lernen lernen)."""

    NEU = "neu", _("Neues kennenlernen")
    WIEDERHOLEN = "wiederholen", _("Wiederholen, was dran ist")
    STOLPERSTELLEN = "stolperstellen", _("Meine Stolperstellen üben")


class Strategie(models.TextChoices):
    LAUT = "laut", _("Ich sage das Wort laut")
    ABDECKEN = "abdecken", _("Ich denke erst nach, dann tippe ich")
    BILD = "bild", _("Ich stelle mir ein Bild dazu vor")
    SATZ = "satz", _("Ich denke mir einen Satz dazu aus")


class Erwartung(models.TextChoices):
    """Selbsteinschätzung vorher: Wie viel werde ich wissen?"""

    WENIGES = "weniges", _("Ich weiß noch wenig")
    EINIGES = "einiges", _("Ich weiß einiges")
    VIELES = "vieles", _("Ich weiß schon viel")


class Richtung(models.TextChoices):
    DE_EN = "de_en", _("Deutsch zu Fremdsprache")
    EN_DE = "en_de", _("Fremdsprache zu Deutsch")


class Ergebnis(models.TextChoices):
    RICHTIG = "richtig", _("richtig")
    FAST = "fast", _("fast richtig")
    NOCH_NICHT = "noch_nicht", _("noch nicht")


class PausenGrund(models.TextChoices):
    KRANK = "krank", _("Krankheit")
    FERIEN = "ferien", _("Ferien")
    SONSTIGES = "sonstiges", _("Sonstiges")


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
    rueckschau = models.TextField(
        blank=True
    )  # Etappe 1, frei; Etappe 2 nutzt die zwei Felder unten

    # --- Etappe 2: Üben ohne KI ---
    thema = models.ForeignKey(
        Thema, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    vorhaben = models.CharField(max_length=16, choices=Vorhaben.choices, blank=True)
    strategie = models.CharField(max_length=16, choices=Strategie.choices, blank=True)
    erwartung = models.CharField(max_length=10, choices=Erwartung.choices, blank=True)
    ziel_fragen = models.PositiveSmallIntegerField(default=10)
    richtig = models.PositiveIntegerField(default=0)
    ende = models.DateTimeField(null=True, blank=True)
    letzte_aktivitaet = models.DateTimeField(null=True, blank=True)
    frust_erkannt = models.BooleanField(default=False)
    rueckschau_schwer = models.CharField(max_length=300, blank=True)
    rueckschau_geholfen = models.CharField(max_length=300, blank=True)
    rueckschau_fertig = models.BooleanField(default=False)
    # Die gerade offene Frage (damit Neuladen dieselbe Frage zeigt und Antworten geprüft werden)
    aktuell_frage = models.ForeignKey(
        "Frage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    aktuell_richtung = models.CharField(max_length=5, choices=Richtung.choices, blank=True)
    aktuell_seit = models.DateTimeField(null=True, blank=True)
    aktuell_versuche = models.PositiveSmallIntegerField(default=0)
    aktuell_hilfe = models.PositiveSmallIntegerField(default=0)

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


class Lernstand(models.Model):
    """Abstandswiederholung: Stand eines Kindes bei einer Frage in einer Richtung.
    ``box`` zeigt auf den Abstand in der Einstellung ``lernen.box_abstaende_tage``."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lernstaende"
    )
    frage = models.ForeignKey(Frage, on_delete=models.CASCADE, related_name="staende")
    richtung = models.CharField(max_length=5, choices=Richtung.choices)
    box = models.PositiveSmallIntegerField(default=0)
    faellig_am = models.DateField()
    versuche = models.PositiveIntegerField(default=0)
    richtige = models.PositiveIntegerField(default=0)
    zuletzt = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "frage", "richtung"], name="lernen_stand_je_kind_frage_richtung"
            )
        ]
        indexes = [models.Index(fields=["kind", "faellig_am"], name="lernen_stand_kind_faellig")]

    def __str__(self):
        return f"{self.kind_id}/{self.frage_id}/{self.richtung}: Box {self.box}"


class Versuch(models.Model):
    """Eine Antwort in einer Lernsitzung. Speichert nur Eingabe, Ergebnis, Hilfe und Dauer."""

    sitzung = models.ForeignKey(Lernsitzung, on_delete=models.CASCADE, related_name="antworten")
    frage = models.ForeignKey(Frage, on_delete=models.CASCADE, related_name="+")
    richtung = models.CharField(max_length=5, choices=Richtung.choices)
    ergebnis = models.CharField(max_length=12, choices=Ergebnis.choices)
    hilfestufe = models.PositiveSmallIntegerField(default=0)
    eingabe = models.CharField(max_length=300, blank=True)
    dauer_ms = models.PositiveIntegerField(default=0)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Versuch {self.sitzung_id}/{self.frage_id}: {self.ergebnis}"


class Lerntag(models.Model):
    """Tagesbilanz eines Kindes: aktive Lernzeit und ob Mindesttag und Tagesziel erreicht sind.
    ``ziel_minuten`` ist das Ziel, das an diesem Tag galt (spätere Anpassung ändert es nicht)."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lerntage"
    )
    datum = models.DateField()
    sekunden = models.PositiveIntegerField(default=0)
    ziel_minuten = models.PositiveSmallIntegerField()
    mindesttag = models.BooleanField(default=False)
    erreicht = models.BooleanField(default=False)
    punkte = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-datum"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "datum"], name="lernen_tag_je_kind_datum")
        ]

    def __str__(self):
        return f"Lerntag {self.kind_id} {self.datum}"


class Lernziel(models.Model):
    """Das persönliche, angepasste Tagesziel eines Kindes (SPEC 21.2). Senken geschieht ohne
    Vorwurf; eine Erhöhung steht nur als ``vorschlag_minuten`` bereit, bis das Kind zustimmt."""

    kind = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lernziel"
    )
    ziel_minuten = models.PositiveSmallIntegerField()
    vorschlag_minuten = models.PositiveSmallIntegerField(null=True, blank=True)
    seit = models.DateField()  # erster Lerntag: davor gab es keine verfehlten Tage
    geaendert_am = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Lernziel {self.kind_id}: {self.ziel_minuten} min"


class Lernpause(models.Model):
    """Schonung: Tage, an denen kein Ziel verlangt wird (Krankheit, Ferien). ``kind`` leer =
    alle Kinder, ``bis`` leer = offen (Ferien-Schalter)."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="lernpausen",
    )
    von = models.DateField()
    bis = models.DateField(null=True, blank=True)
    grund = models.CharField(max_length=10, choices=PausenGrund.choices, default="sonstiges")

    class Meta:
        ordering = ["-von"]
        constraints = [
            models.CheckConstraint(
                condition=Q(bis__isnull=True) | Q(bis__gte=models.F("von")),
                name="lernen_pause_bis_nach_von",
            )
        ]

    def __str__(self):
        return f"Pause {self.kind_id or 'alle'} {self.von}-{self.bis or 'offen'}"
