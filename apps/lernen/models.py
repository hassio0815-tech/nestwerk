"""Datenmodell von lernen (SPEC 21; Etappe 1 Fundament, 2 Üben ohne KI, 3 KI, 4 Material, 5 Tutor).

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
    # Etappe 4: Frage stammt aus einem Upload; mit dem Material verschwindet sie
    material = models.ForeignKey(
        "Material", null=True, blank=True, on_delete=models.CASCADE, related_name="fragen"
    )

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
    # Etappe 4: Sind Fragen aus Uploads sofort nutzbar? ``None`` = Familien-Einstellung
    # ``lernen.freigabe_durch_eltern`` (Standard: Eltern geben frei).
    fragen_sofort_nutzbar = models.BooleanField(null=True, blank=True)

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


# --- Etappe 3: KI-Anbindung (SPEC 21.6) -----------------------------------------------------------


class KiTyp(models.TextChoices):
    OPENAI_KOMPATIBEL = (
        "openai_kompatibel",
        _("OpenAI-kompatibel (Ollama, vLLM, LiteLLM, eigener Server)"),
    )
    ANTHROPIC = "anthropic", _("Anthropic")
    OPENAI = "openai", _("OpenAI")


class KiAufgabe(models.TextChoices):
    AUSLESEN = "auslesen", _("Auslesen (Foto oder Text einlesen)")
    FRAGEN_ERZEUGEN = "fragen_erzeugen", _("Fragen erzeugen")
    BEWERTEN = "bewerten", _("Antworten bewerten")
    TUTOR = "tutor", _("Tutor (Hilfe beim Lösen)")


class KiAuftragStatus(models.TextChoices):
    WARTEND = "wartend", _("wartend")
    LAEUFT = "laeuft", _("läuft")
    FERTIG = "fertig", _("fertig")
    FEHLER = "fehler", _("Fehler")


class KiAnbieter(models.Model):
    """Ein konfigurierter KI-Zugang. Der API-Schlüssel liegt nur als Fernet-Token in der DB
    (``benachrichtigung.crypto``) und wird nie angezeigt oder geloggt. Neu angelegt ist ein
    Anbieter immer inaktiv; Cloud-Anbieter brauchen vor der Aktivierung die Einwilligung der
    Eltern (Zeitpunkt und Elternperson)."""

    name = models.CharField(max_length=60, unique=True)
    typ = models.CharField(max_length=20, choices=KiTyp.choices)
    basis_url = models.CharField(max_length=300, blank=True)
    modell = models.CharField(max_length=120)
    schluessel_verschluesselt = models.TextField(blank=True, editable=False)
    aktiv = models.BooleanField(default=False)
    ist_cloud = models.BooleanField(default=True)
    einwilligung_am = models.DateTimeField(null=True, blank=True)
    einwilligung_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    letzter_test_am = models.DateTimeField(null=True, blank=True)
    letzter_test_ok = models.BooleanField(null=True, blank=True)
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def hat_schluessel(self):
        return bool(self.schluessel_verschluesselt)


class KiZuordnung(models.Model):
    """Welcher Anbieter eine Aufgabe erledigt (familienweit, nicht pro Kind). Keine Zeile =
    KI für diese Aufgabe aus."""

    aufgabe = models.CharField(max_length=20, choices=KiAufgabe.choices, unique=True)
    anbieter = models.ForeignKey(KiAnbieter, on_delete=models.CASCADE, related_name="zuordnungen")

    class Meta:
        ordering = ["aufgabe"]

    def __str__(self):
        return f"{self.aufgabe} -> {self.anbieter_id}"


class KiAuftrag(models.Model):
    """Warteschlangen-Eintrag für KI-Arbeit im Hintergrund. Enthält nie Inhalte, nur einen
    Verweis auf die Eingabe (z. B. ``lernen.lernmappe:12``) und den Idempotenz-Schlüssel."""

    aufgabe = models.CharField(max_length=20, choices=KiAufgabe.choices)
    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    anbieter = models.ForeignKey(
        KiAnbieter, null=True, blank=True, on_delete=models.SET_NULL, related_name="auftraege"
    )
    schluessel = models.CharField(max_length=120, unique=True)
    eingabe_verweis = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=10, choices=KiAuftragStatus.choices, default=KiAuftragStatus.WARTEND
    )
    versuche = models.PositiveSmallIntegerField(default=0)
    fehler_art = models.CharField(max_length=30, blank=True)
    naechster_versuch_am = models.DateTimeField(null=True, blank=True)
    gestartet_am = models.DateTimeField(null=True, blank=True)
    beendet_am = models.DateTimeField(null=True, blank=True)
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["status", "naechster_versuch_am"])]

    def __str__(self):
        return f"{self.aufgabe} ({self.status})"


# --- Etappe 4: Material-Pipeline (SPEC 21.5) ----------------------------------------------------


class MaterialArt(models.TextChoices):
    BILD = "bild", _("Bild")
    DOKUMENT = "dokument", _("Dokument")


class MaterialEingang(models.TextChoices):
    UPLOAD = "upload", _("Upload")
    INBOX = "inbox", _("Ordner inbox")


class MaterialStatus(models.TextChoices):
    WARTET_KI = "wartet_ki", _("wartet auf KI-Einrichtung")
    WARTET = "wartet", _("wartet")
    LIEST = "liest", _("wird gelesen")
    RUECKFRAGE = "rueckfrage", _("braucht Rückfrage")
    FRAGEN = "fragen", _("Fragen werden gemacht")
    WARTET_ELTERN = "wartet_eltern", _("wartet auf die Eltern")
    BEREIT = "bereit", _("bereit")
    FEHLER = "fehler", _("Fehler")


class Material(models.Model):
    """Ein Upload oder eine Datei aus dem Ordner ``inbox`` in der Lernmappe eines Kindes.

    ``name`` ist der neutrale Dateiname im Speicher (``<32 Hex>.<ext>``), nie der Name des
    Uploads; ``anzeigename`` ist die bereinigte Fassung zur Anzeige. Der Inhalt der Datei und
    der ausgelesene Text sind **Daten** und nie Anweisungen (Prompt-Injection).
    """

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="materialien"
    )
    name = models.CharField(max_length=60)
    anzeigename = models.CharField(max_length=80, blank=True)
    art = models.CharField(max_length=10, choices=MaterialArt.choices)
    mime = models.CharField(max_length=40)
    groesse = models.PositiveIntegerField(default=0)
    inhalt_hash = models.CharField(max_length=64, db_index=True)
    bereich = models.CharField(max_length=10, default="inbox")  # inbox oder archiv
    eingang = models.CharField(
        max_length=10, choices=MaterialEingang.choices, default=MaterialEingang.UPLOAD
    )
    hinweis_fach = models.CharField(max_length=40, blank=True)  # Fach-Unterordner im inbox
    status = models.CharField(
        max_length=14, choices=MaterialStatus.choices, default=MaterialStatus.WARTET_KI
    )
    fehler = models.CharField(max_length=30, blank=True)
    fach = models.ForeignKey(
        Fach, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    thema_name = models.CharField(max_length=80, blank=True)
    klassenstufe = models.PositiveSmallIntegerField(null=True, blank=True)
    konfidenz = models.FloatField(null=True, blank=True)
    text = models.TextField(blank=True)
    # Zählt Neustarts; Teil des Idempotenz-Schlüssels der KI-Aufträge
    durchgang = models.PositiveSmallIntegerField(default=1)
    erstellt = models.DateTimeField(auto_now_add=True)
    aktualisiert = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-erstellt", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "name"], name="lernen_material_name_je_kind")
        ]
        indexes = [models.Index(fields=["kind", "status"], name="lernen_material_kind_status")]

    def __str__(self):
        return f"Material {self.pk} ({self.status})"


# --- Etappe 5: Tutor mit Hilfeleiter (SPEC 21.3, 21.4) -------------------------------------------


class GespraechStatus(models.TextChoices):
    OFFEN = "offen", _("offen")
    BEENDET = "beendet", _("beendet")


class NachrichtRolle(models.TextChoices):
    KIND = "kind", _("Kind")
    TUTOR = "tutor", _("Tutor")


class NachrichtArt(models.TextChoices):
    FRAGE = "frage", _("Frage oder Nachricht")
    VERSUCH = "versuch", _("Lösungsversuch")
    MEHR_HILFE = "mehr_hilfe", _("Bitte um mehr Hilfe")
    ANTWORT = "antwort", _("Antwort des Tutors")
    BEWERTUNG = "bewertung", _("Rückmeldung zum Versuch")
    HINWEIS = "hinweis", _("Hinweis der App")


class Markierung(models.TextChoices):
    """Warum ein Tutor-Text nicht von der KI stammt oder eine Nachricht auffiel (für die Eltern)."""

    LOESUNGSBITTE = "loesungsbitte", _("Bitte, die Aufgabe zu lösen")
    ROLLENWECHSEL = "rollenwechsel", _("Versuch, die Regeln zu ändern")
    LECK = "leck", _("Antwort zurückgehalten (Lösung vermutet)")


class TutorGespraech(models.Model):
    """Eine Unterhaltung eines Kindes mit dem Tutor. Gehört genau einem Kind; Geschwister und
    andere Kinder sehen sie nie. ``hilfestufe`` ist die bisher höchste Stufe der Hilfeleiter
    (1 bis 5) und steigt nur auf Wunsch des Kindes."""

    kind = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_gespraeche"
    )
    material = models.ForeignKey(
        Material, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    thema = models.ForeignKey(
        Thema, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(
        max_length=10, choices=GespraechStatus.choices, default=GespraechStatus.OFFEN
    )
    hilfestufe = models.PositiveSmallIntegerField(default=1)
    beginn = models.DateTimeField()
    ende = models.DateTimeField(null=True, blank=True)
    letzte_aktivitaet = models.DateTimeField()

    class Meta:
        ordering = ["-beginn", "-id"]
        indexes = [models.Index(fields=["kind", "status"], name="lernen_tutor_kind_status")]

    def __str__(self):
        return f"Tutor-Gespräch {self.pk} ({self.status})"


class TutorNachricht(models.Model):
    """Eine Nachricht im Gespräch. Das Protokoll ist für die Eltern nur lesbar."""

    gespraech = models.ForeignKey(
        TutorGespraech, on_delete=models.CASCADE, related_name="nachrichten"
    )
    rolle = models.CharField(max_length=6, choices=NachrichtRolle.choices)
    art = models.CharField(max_length=12, choices=NachrichtArt.choices, default=NachrichtArt.FRAGE)
    text = models.TextField()
    hilfestufe = models.PositiveSmallIntegerField(default=1)
    markierung = models.CharField(max_length=14, choices=Markierung.choices, blank=True)
    urteil = models.CharField(max_length=12, blank=True)
    empfohlene_stufe = models.PositiveSmallIntegerField(null=True, blank=True)
    zeit = models.DateTimeField()

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["rolle", "zeit"], name="lernen_tutor_nachr_zeit")]

    def __str__(self):
        return f"Tutor-Nachricht {self.pk} ({self.rolle})"
