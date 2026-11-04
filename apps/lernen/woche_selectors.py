"""Lesen für die Wochenansichten (SPEC 21.9 Familienansicht, 21.10 Eltern-Sicht).

- **Beteiligung statt Menge (L12):** Die Familienansicht zeigt nur, wer geübt hat (Tage), und den
  Fortschritt des Lern-Familienziels. Es gibt keine Rangliste und keine Zahl, die Kinder
  gegeneinander stellt.
- **Wochen-Titel ohne Punkte:** reine Anzeige-Berechnung (nichts wird gespeichert, nichts
  gebucht, nichts gemeldet). Jeder Wert ist relativ zum eigenen Ziel oder zur eigenen Vorwoche.
  Gleichstand teilt den Titel; bei nur einem Kind mit Aktivität gibt es keine Titel.
- **Eltern-Wochenbild:** je Kind, ohne Geschwistervergleich, mit Handlungsvorschlägen statt
  Bewertung (``woche_texte``).

Die Funktionen bekommen die Kinder als Argument; die Aufrufer (Registry, Views) holen sie über
``konten``.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction

from django.utils.formats import date_format

from apps.kern import zeit
from apps.kern.einstellungen import wert

from . import plan_selectors, selectors, tagesziel
from .mathe import fehler as mathe_fehler
from .models import (
    Ergebnis,
    Lernsitzung,
    Lerntag,
    Selbsteinschaetzung,
    Thema,
    TutorGespraech,
    Versuch,
)
from .woche_texte import Vorschlag

UEBUNGSMEISTER = "uebungsmeister"
AUFSTEIGER = "aufsteiger"
DURCHBEISSER = "durchbeisser"
ENTDECKER = "entdecker"
TITEL = (UEBUNGSMEISTER, AUFSTEIGER, DURCHBEISSER, ENTDECKER)

VERLAUF_WOCHEN = 4
FEHLERARTEN_MAX = 3
TUTOR_HOHE_STUFE = 4  # ab dieser Stufe der Hilfeleiter gilt die Hilfe als hoch
VORSCHLAEGE_MAX = 8


# --- Eine Woche eines Kindes ---------------------------------------------------------------------


def _fenster(montag):
    return zeit.tag_beginn(montag), zeit.tag_beginn(montag + timedelta(days=7))


@dataclass(frozen=True)
class KindWoche:
    """Was ein Kind in einer Woche getan hat. Alles Rohe bleibt hier; verglichen wird nur gegen
    das eigene Ziel oder die eigene Vorwoche."""

    kind: object
    montag: date
    tage_geuebt: int  # Tage ab dem Mindesttag
    tage_ziel: int  # Tage, an denen das EIGENE Tagesziel erreicht wurde
    antworten: int  # richtige und falsche Antworten (ohne "fast richtig")
    richtig: int
    mit_hilfe: int
    fehler: int  # verschiedene Fragen, die mindestens einmal falsch waren
    ueberarbeitet: int  # davon später ohne Hilfe richtig beantwortet
    neue_themen: int
    themen: dict = field(default_factory=dict)  # thema_id -> (Antworten, Fehlversuche)

    @property
    def aktiv(self):
        return self.tage_geuebt >= 1

    @property
    def treffer(self):
        """Anteil richtiger Antworten in Prozent (genau gerechnet) oder ``None``."""
        return Fraction(self.richtig * 100, self.antworten) if self.antworten else None

    @property
    def hilfe(self):
        """Anteil der Antworten mit Hilfe in Prozent oder ``None``."""
        return Fraction(self.mit_hilfe * 100, self.antworten) if self.antworten else None


def kind_woche(kind, montag):
    """Zahlen eines Kindes für die Woche ab ``montag`` (nur dieses Kind wird gelesen)."""
    tage = list(
        Lerntag.objects.filter(
            kind=kind, datum__gte=montag, datum__lt=montag + timedelta(days=7)
        ).values_list("mindesttag", "erreicht")
    )
    von, bis = _fenster(montag)
    zeilen = list(
        Versuch.objects.filter(
            sitzung__kind=kind,
            erstellt__gte=von,
            erstellt__lt=bis,
            ergebnis__in=(Ergebnis.RICHTIG, Ergebnis.NOCH_NICHT),
        )
        .order_by("id")
        .values_list("frage_id", "richtung", "ergebnis", "hilfestufe", "frage__thema_id")
    )
    falsch, geklaert, themen = set(), set(), {}
    richtig = mit_hilfe = 0
    for frage, richtung, ergebnis, hilfe, thema in zeilen:
        schluessel = (frage, richtung)
        antworten, fehlversuche = themen.get(thema, (0, 0))
        mit_hilfe += 1 if hilfe > 0 else 0
        if ergebnis == Ergebnis.RICHTIG:
            richtig += 1
            if schluessel in falsch and hilfe == 0:
                geklaert.add(schluessel)
        else:
            falsch.add(schluessel)
            fehlversuche += 1
        themen[thema] = (antworten + 1, fehlversuche)
    neue = 0
    if themen:
        frueher = set(
            Versuch.objects.filter(sitzung__kind=kind, erstellt__lt=von)
            .values_list("frage__thema_id", flat=True)
            .distinct()
        )
        # Die allererste Woche ist kein "Entdecken": ohne Vergangenheit ist alles neu.
        neue = len(set(themen) - frueher) if frueher else 0
    return KindWoche(
        kind=kind,
        montag=montag,
        tage_geuebt=sum(1 for mindest, _erreicht in tage if mindest),
        tage_ziel=sum(1 for _mindest, erreicht in tage if erreicht),
        antworten=len(zeilen),
        richtig=richtig,
        mit_hilfe=mit_hilfe,
        fehler=len(falsch),
        ueberarbeitet=len(geklaert),
        neue_themen=neue,
        themen=themen,
    )


# --- Wochen-Titel --------------------------------------------------------------------------------


@dataclass(frozen=True)
class WochenTitel:
    schluessel: str
    kinder: tuple


def titel_anzeigen():
    return bool(wert("lernen.titel_anzeigen"))


def _beste(werte):
    """Alle Kinder mit dem größten Wert (Gleichstand teilt). ``werte``: ``{kind: wert}``."""
    if not werte:
        return ()
    spitze = max(werte.values())
    return tuple(k for k, w in werte.items() if w == spitze)


def titel_berechnen(kinder, montag):
    """Die Wochen-Titel der Woche ab ``montag``: ``[WochenTitel]`` (leer, wenn nicht vergeben).

    Gerechnet wird nur unter Kindern mit Aktivität. Gibt es weniger als zwei, vergibt niemand
    einen Titel. Die Titel bringen keine Punkte und lösen keine Meldung aus."""
    stand = [kind_woche(k, montag) for k in kinder]
    aktive = [s for s in stand if s.aktiv]
    if len(aktive) < 2:
        return []
    meister = {s.kind: s.tage_ziel for s in aktive if s.tage_ziel >= 1}
    mindest = wert("lernen.titel_min_versuche")
    schritt = wert("lernen.woche_tendenz_prozent")
    aufstieg = {}
    for s in aktive:
        if s.antworten < mindest:
            continue
        vorher = kind_woche(s.kind, montag - timedelta(days=7))
        if vorher.antworten < mindest:
            continue
        besser = (s.treffer - vorher.treffer) + (vorher.hilfe - s.hilfe)
        if besser >= schritt:
            aufstieg[s.kind] = besser
    zaeh = {
        s.kind: Fraction(s.ueberarbeitet, s.fehler)
        for s in aktive
        if s.fehler >= wert("lernen.titel_min_fehler") and s.ueberarbeitet >= 1
    }
    entdecker = tuple(s.kind for s in aktive if s.neue_themen >= 1)
    ergebnis = [
        (UEBUNGSMEISTER, _beste(meister)),
        (AUFSTEIGER, _beste(aufstieg)),
        (DURCHBEISSER, _beste(zaeh)),
        (ENTDECKER, entdecker),
    ]
    return [WochenTitel(schluessel, kinder_) for schluessel, kinder_ in ergebnis if kinder_]


def titel_vorwoche(kinder, heute):
    """Titel der Vorwoche für die Anzeige; leer, wenn die Eltern die Anzeige abgeschaltet haben."""
    if not titel_anzeigen():
        return []
    return titel_berechnen(kinder, tagesziel.montag(heute) - timedelta(days=7))


# --- Familienansicht -----------------------------------------------------------------------------


def _woche_tage(montag):
    return [montag + timedelta(days=i) for i in range(7)]


@dataclass(frozen=True)
class Beteiligung:
    """Ein Kind, das diese Woche geübt hat, mit Haken je Wochentag (keine Zahl, kein Rang)."""

    kind: object
    tage: tuple  # sieben Paare (Datum, geübt), Montag bis Sonntag


def uebungswoche(kinder, heute):
    """Nur Kinder mit geübten Tagen, alphabetisch. Wer nicht geübt hat, kommt nicht vor."""
    montag = tagesziel.montag(heute)
    tage = _woche_tage(montag)
    zeilen = []
    for kind in kinder:
        geuebt = set(
            Lerntag.objects.filter(
                kind=kind, mindesttag=True, datum__gte=montag, datum__lte=tage[-1]
            ).values_list("datum", flat=True)
        )
        if geuebt:
            zeilen.append(Beteiligung(kind, tuple((t, t in geuebt) for t in tage)))
    return sorted(zeilen, key=lambda b: b.kind.anzeigename.lower())


@dataclass(frozen=True)
class Familienziel:
    """ "Alle üben an N Tagen": der Fortschritt aller Kinder in einem Balken, ohne Namen."""

    tage: int
    teilnehmer: int
    erfuellt: int
    soll: int
    geschafft: int

    @property
    def erreicht(self):
        return self.teilnehmer > 0 and self.erfuellt == self.teilnehmer

    @property
    def prozent(self):
        return min(100, self.geschafft * 100 // self.soll) if self.soll else 0


def _pausiert(kind, montag, heute):
    pausen = tagesziel.pausentage(kind, montag, montag + timedelta(days=6))
    if wert("lernen.ferien_schalter"):
        # Die offene Ferien-Pause entsteht erst beim nächsten Abgleich (wie bei der Serie).
        pausen.update(heute + timedelta(days=i) for i in range(7 - heute.weekday()))
    return len(pausen)


def familienziel(kinder, heute):
    """Lern-Familienziel der laufenden Woche oder ``None``, wenn niemand etwas verlangt wird
    (alle geschont oder keine Kinder). Pausentage senken, was von einem Kind verlangt wird."""
    montag = tagesziel.montag(heute)
    ziel = wert("lernen.familienziel_tage")
    teilnehmer = erfuellt = soll = geschafft = 0
    for kind in kinder:
        noetig = max(0, ziel - _pausiert(kind, montag, heute))
        if noetig == 0:
            continue
        geuebt = Lerntag.objects.filter(
            kind=kind, mindesttag=True, datum__gte=montag, datum__lte=heute
        ).count()
        teilnehmer += 1
        soll += noetig
        geschafft += min(geuebt, noetig)
        erfuellt += 1 if geuebt >= noetig else 0
    if teilnehmer == 0:
        return None
    return Familienziel(ziel, teilnehmer, erfuellt, soll, geschafft)


# --- Eltern-Wochenbild ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verlaufspunkt:
    montag: date
    antworten: int
    treffer: int | None  # Prozent
    hilfe: int | None  # Prozent


@dataclass(frozen=True)
class Schwaeche:
    fach: str
    thema: str
    fehler: int
    antworten: int


@dataclass(frozen=True)
class Meldung:
    fach: str
    art: str  # "zu_leicht" oder "zu_schwer"
    anzahl: int


@dataclass(frozen=True)
class PruefungHinweis:
    titel: str
    fach: str
    termin: date
    tage_bis: int
    plan_ok: bool
    prozent: int


@dataclass(frozen=True)
class Fehlerart:
    """Häufige Fehlerart beim Mathe-Üben (Fehleranalyse): Schlüssel und Zahl der Antworten."""

    typ: str
    anzahl: int
    hinweis: str  # der Hinweis, den das Kind dazu bekommt (zum Mithelfen)


@dataclass
class Wochenbild:
    kind: object
    montag: date
    tage_geuebt: int = 0
    soll_tage: int = 0
    tage_ziel: int = 0
    antworten: int = 0
    hilfe_prozent: int | None = None
    hilfe_tendenz: str = ""  # "sinkt", "steigt", "gleich" oder leer
    tutor_hoch: int = 0
    verlauf: list = field(default_factory=list)
    schwaechen: list = field(default_factory=list)
    fehlerarten: list = field(default_factory=list)  # Fehleranalyse (Mathe), häufigste zuerst
    einschaetzung: dict = field(default_factory=dict)
    meldungen: list = field(default_factory=list)
    pruefungen: list = field(default_factory=list)
    vorschlaege: list = field(default_factory=list)


def _prozent(bruch):
    return None if bruch is None else int(bruch + Fraction(1, 2))


def _verlauf(kind, montag):
    punkte = []
    for i in range(VERLAUF_WOCHEN - 1, -1, -1):
        w = kind_woche(kind, montag - timedelta(weeks=i))
        punkte.append(Verlaufspunkt(w.montag, w.antworten, _prozent(w.treffer), _prozent(w.hilfe)))
    return punkte


def _tendenz(verlauf):
    """Hilfe der jüngsten Woche mit Daten gegen den Schnitt der früheren Wochen."""
    werte = [p.hilfe for p in verlauf if p.hilfe is not None]
    if len(werte) < 2:
        return ""
    unterschied = werte[-1] - sum(werte[:-1]) / len(werte[:-1])
    schritt = wert("lernen.woche_tendenz_prozent")
    if unterschied <= -schritt:
        return "sinkt"
    return "steigt" if unterschied >= schritt else "gleich"


def _schwaechen(woche):
    mindest = wert("lernen.woche_schwaeche_fehler")
    anteil = wert("lernen.woche_schwaeche_prozent")
    treffer = {
        pk: (antworten, fehler)
        for pk, (antworten, fehler) in woche.themen.items()
        if pk is not None and fehler >= mindest and fehler * 100 >= anteil * antworten
    }
    namen = {t.pk: t for t in Thema.objects.filter(pk__in=treffer).select_related("fach")}
    ergebnis = [
        Schwaeche(namen[pk].fach.name, namen[pk].name, fehler, antworten)
        for pk, (antworten, fehler) in treffer.items()
        if pk in namen
    ]
    return sorted(ergebnis, key=lambda s: (-s.fehler, s.thema))


def _fehlerarten(kind, montag):
    """Die häufigsten erkannten Fehlerarten der Woche (nur mit eigenem Hinweistext), ab der
    gleichen Mindestzahl wie bei den Schwächen."""
    von, bis = _fenster(montag)
    zaehler = Counter(
        Versuch.objects.filter(sitzung__kind=kind, erstellt__gte=von, erstellt__lt=bis)
        .exclude(fehlertyp="")
        .values_list("fehlertyp", flat=True)
    )
    mindest = wert("lernen.woche_schwaeche_fehler")
    bekannt = [(t, n) for t, n in zaehler.items() if t in mathe_fehler.HINWEISE and n >= mindest]
    bekannt.sort(key=lambda x: (-x[1], x[0]))
    return [Fehlerart(t, n, mathe_fehler.hinweis_text(t)) for t, n in bekannt[:FEHLERARTEN_MAX]]


def _sitzungen(kind, montag):
    von, bis = _fenster(montag)
    return list(
        Lernsitzung.objects.filter(kind=kind, beginn__gte=von, beginn__lt=bis).select_related(
            "fach"
        )
    )


def _meldungen(sitzungen):
    zaehler = Counter(
        (s.fach.name if s.fach else "", s.selbsteinschaetzung)
        for s in sitzungen
        if s.selbsteinschaetzung in (Selbsteinschaetzung.ZU_LEICHT, Selbsteinschaetzung.ZU_SCHWER)
    )
    return [Meldung(fach, art, n) for (fach, art), n in sorted(zaehler.items())]


def _pruefungen(kind, heute):
    bis = heute + timedelta(days=wert("lernen.woche_pruefung_tage"))
    liste = []
    for p in plan_selectors.aktive_pruefungen(kind).filter(termin__gte=heute, termin__lte=bis):
        liste.append(
            PruefungHinweis(
                p.titel,
                p.fach.name,
                p.termin,
                (p.termin - heute).days,
                p.plan_ok,
                plan_selectors.fortschritt(p).prozent if p.plan_ok else 0,
            )
        )
    return liste


def wochenbild(kind, heute, montag=None):
    """Das Wochenbild eines Kindes für die Eltern (``montag`` leer = laufende Woche)."""
    montag = montag or tagesziel.montag(heute)
    woche = kind_woche(kind, montag)
    sitzungen = _sitzungen(kind, montag)
    verlauf = _verlauf(kind, montag)
    von, bis = _fenster(montag)
    bild = Wochenbild(
        kind=kind,
        montag=montag,
        tage_geuebt=woche.tage_geuebt,
        soll_tage=max(0, wert("lernen.serie_tage_pro_woche") - _pausiert(kind, montag, heute)),
        tage_ziel=woche.tage_ziel,
        antworten=woche.antworten,
        hilfe_prozent=verlauf[-1].hilfe,
        hilfe_tendenz=_tendenz(verlauf),
        tutor_hoch=TutorGespraech.objects.filter(
            kind=kind, beginn__gte=von, beginn__lt=bis, hilfestufe__gte=TUTOR_HOHE_STUFE
        ).count(),
        verlauf=verlauf,
        schwaechen=_schwaechen(woche),
        fehlerarten=_fehlerarten(kind, montag),
        einschaetzung=dict(
            Counter(v for s in sitzungen if s.ende is not None and (v := selectors.vergleich(s)))
        ),
        meldungen=_meldungen(sitzungen),
        pruefungen=_pruefungen(kind, heute),
    )
    bild.vorschlaege = vorschlaege(bild, heute)
    return bild


def vorschlaege(bild, heute):
    """Regelbasierte Handlungsvorschläge aus den Daten des Wochenbilds: kurze Sätze als
    msgid mit Parametern, nie eine Bewertung oder Note."""
    liste = []

    def dazu(schluessel, **parameter):
        liste.append(Vorschlag(schluessel, parameter))

    vorbei = bild.montag + timedelta(days=7) <= heute
    spaet = vorbei or heute.weekday() >= 3
    if bild.soll_tage > 0:
        if bild.tage_geuebt >= bild.soll_tage:
            dazu("wochenziel_geschafft")
        elif bild.tage_geuebt == 0 and spaet:
            dazu("kein_uebungstag")
        elif vorbei:
            dazu("weniger_tage", tage=bild.tage_geuebt, soll=bild.soll_tage)
    minuten = wert("lernen.pruefung_portion_minuten")
    for s in bild.schwaechen[:2]:
        dazu("schwaeche", fach=s.fach, thema=s.thema, minuten=minuten)
    hoch = wert("lernen.woche_hilfe_hoch_prozent")
    if bild.hilfe_prozent is not None and bild.hilfe_prozent >= hoch:
        dazu("viel_hilfe")
    elif bild.hilfe_tendenz == "sinkt":
        dazu("weniger_hilfe")
    if bild.tutor_hoch >= 2:
        dazu("tutor_hohe_stufe")
    if bild.einschaetzung.get("weniger", 0) >= 2:
        dazu("zu_optimistisch")
    if bild.einschaetzung.get("mehr", 0) >= 2:
        dazu("traut_sich_zu_wenig")
    for m in bild.meldungen:
        if m.fach:
            dazu("meldung_" + m.art, fach=m.fach)
    for p in bild.pruefungen:
        datum = date_format(p.termin, "SHORT_DATE_FORMAT")
        if not p.plan_ok:
            dazu("pruefung_ohne_plan", titel=p.titel, fach=p.fach, datum=datum)
        elif p.tage_bis <= 7 and p.prozent < 50:
            dazu("pruefung_knapp", titel=p.titel, tage=p.tage_bis, prozent=p.prozent)
    return liste[:VORSCHLAEGE_MAX]
