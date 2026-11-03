"""Schreiben für lernen: Fundament (Etappe 1) und Üben ohne KI (Etappe 2).

Ablauf einer Lernsitzung (SPEC 21.2): ``sitzung_starten`` (Vorhaben, Strategie, Intensität,
Selbsteinschätzung) -> ``frage_stellen`` / ``antworten`` / ``hilfe`` / ``loesung_zeigen`` im
Wechsel -> ``sitzung_beenden`` -> ``rueckschau_speichern``.

- Gemessen wird die aktive Zeit (lange Denkpausen zählen nicht, ``lernen.leerlauf_sekunden``).
- Punkte gibt es nur für den Prozess: ein fester Betrag, sobald das Tagesziel erreicht ist (nie
  pro richtige Antwort), gedeckelt durch ``lernen.lernpunkte_tageslimit``, abschaltbar durch
  ``lernen.lernpunkte_aktiv``. Hilfen kosten nichts. Eine gerissene Serie nimmt nie Punkte.
- Jede Änderung läuft in einer Transaktion, ebenso Buchung, Aktivität und Ereignis.
"""

import random
from dataclasses import dataclass

from django.db import transaction

from apps.ereignisse import services as ereignisse
from apps.kern import zeit
from apps.kern.einstellungen import wert
from apps.punkte import services as punkte
from apps.spielregeln import services as spielregeln

from . import events, frust, pruefung, selectors, tagesziel, texte, wiederholung
from .models import (
    Ergebnis,
    Erwartung,
    Frage,
    Freigabe,
    Intensitaet,
    Leistungsstufe,
    Lernmappe,
    Lernpause,
    Lernsitzung,
    PausenGrund,
    Quelle,
    Selbsteinschaetzung,
    Strategie,
    Versuch,
    Vorhaben,
)
from .speicher import Speicher

QUELLE = "lernen"  # quelle_modul der Buchungen, modul der Aktivität
RUECKSCHAU_MAX = 300


class LernenFehler(ValueError):
    """Fachlicher Fehler beim Üben (z. B. keine offene Frage)."""


def lernmappe_sicherstellen(kind, speicher=None):
    """Legt die Lernmappe (1:1 je Kind) und ihre Ordner an. Idempotent."""
    mappe, _neu = Lernmappe.objects.get_or_create(kind=kind)
    (speicher or Speicher()).ordner_anlegen(kind.pk)
    return mappe


def speicher_limit_bytes():
    return wert("lernen.speicher_limit_mb") * 1024 * 1024


def fragen_sofort_nutzbar(kind):
    """Sind KI-Fragen aus Uploads dieses Kindes sofort nutzbar? Gilt die Einstellung der Lernmappe
    (pro Kind), sonst ``lernen.freigabe_durch_eltern`` (Standard: Eltern geben frei)."""
    mappe = Lernmappe.objects.filter(kind=kind).first() if kind is not None else None
    if mappe is not None and mappe.fragen_sofort_nutzbar is not None:
        return mappe.fragen_sofort_nutzbar
    return not wert("lernen.freigabe_durch_eltern")


def frage_anlegen(thema, typ, frage, antwort, *, quelle, kind=None, material=None):
    """Neue Frage von Eltern oder KI. KI-Fragen warten auf die Freigabe der Eltern, außer die
    Lernmappe des Kindes erlaubt die sofortige Nutzung; Eltern-Fragen sind sofort freigegeben."""
    if quelle == Quelle.SYSTEM:
        raise ValueError("Startdaten entstehen nur per Datenmigration.")
    offen = quelle == Quelle.KI and not fragen_sofort_nutzbar(kind)
    return Frage.objects.create(
        material=material,
        thema=thema,
        typ=typ,
        frage=frage,
        antwort=antwort,
        quelle=quelle,
        kind=kind,
        freigabe=Freigabe.OFFEN if offen else Freigabe.FREIGEGEBEN,
    )


def leistungsstufe_setzen(kind, fach, stufe="", klassenstufe=None):
    obj, _neu = Leistungsstufe.objects.update_or_create(
        kind=kind, fach=fach, defaults={"stufe": stufe, "klassenstufe": klassenstufe}
    )
    return obj


# --- Üben (Etappe 2) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rueckmeldung:
    """Was das Kind nach einer Antwort sieht."""

    ergebnis: str
    text: str
    loesung: str = ""  # nur bei "noch nicht"
    nochmal: bool = False  # "fast richtig": dieselbe Frage noch einmal
    pause_vorschlag: bool = False
    stufe_gesenkt: bool = False
    ziel_erreicht: bool = False


def _jetzt(jetzt):
    return jetzt or zeit.jetzt()


def _kind_pruefen(kind):
    if getattr(kind, "rolle", None) != "kind":
        raise LernenFehler("Üben gibt es nur für Kinder.")


def _wahl(wert_, auswahl, name):
    if wert_ not in auswahl.values:
        raise LernenFehler(f"{name}: unbekannte Auswahl '{wert_}'")
    return wert_


def tag_vorbereiten(kind, heute=None):
    """Gleicht Ferien ab und passt das Tagesziel an (Senken oder Vorschlag). Idempotent; wird beim
    Öffnen der Lernseite und beim Start einer Sitzung aufgerufen. Gibt die Anpassung zurück."""
    heute = heute or zeit.heute()
    with transaction.atomic():
        tagesziel.ferien_abgleichen(heute)
        anpassung = tagesziel.ziel_anpassen(kind, heute)
        tagesziel.lerntag_holen(kind, heute)
    return anpassung


@transaction.atomic
def sitzung_starten(
    kind,
    fach,
    *,
    thema=None,
    intensitaet=Intensitaet.NORMAL,
    vorhaben=Vorhaben.WIEDERHOLEN,
    strategie=Strategie.ABDECKEN,
    erwartung=Erwartung.EINIGES,
    jetzt=None,
):
    """Legt eine Sitzung an. Gibt es noch eine offene, wird sie zuerst beendet (nur eine läuft)."""
    _kind_pruefen(kind)
    jetzt = _jetzt(jetzt)
    if not fach.aktiv or (thema is not None and thema.fach_id != fach.pk):
        raise LernenFehler("Fach oder Thema passt nicht.")
    intensitaet = _wahl(intensitaet, Intensitaet, "Intensität")
    vorhaben = _wahl(vorhaben, Vorhaben, "Vorhaben")
    strategie = _wahl(strategie, Strategie, "Strategie")
    erwartung = _wahl(erwartung, Erwartung, "Selbsteinschätzung")
    alte = selectors.offene_sitzung(kind)
    if alte is not None:
        sitzung_beenden(alte, jetzt=jetzt)
    tag_vorbereiten(kind, zeit.heute(jetzt))
    anzahl = wert(f"lernen.fragen_{intensitaet}")
    return Lernsitzung.objects.create(
        kind=kind,
        fach=fach,
        thema=thema,
        beginn=jetzt,
        letzte_aktivitaet=jetzt,
        intensitaet=intensitaet,
        vorhaben=vorhaben,
        strategie=strategie,
        erwartung=erwartung,
        ziel_fragen=anzahl,
    )


def _zeit_buchen(sitzung, jetzt):
    """Rechnet die aktive Zeit seit dem letzten Schritt auf Sitzung und Lerntag. Beim ersten
    Überschreiten von Mindesttag und Tagesziel: Aktivität, Punkte, Ereignis. Gibt zurück, ob
    das Tagesziel dabei erreicht wurde."""
    kind = sitzung.kind
    heute = zeit.heute(jetzt)
    verstrichen = (jetzt - (sitzung.letzte_aktivitaet or sitzung.beginn)).total_seconds()
    sekunden = max(0, min(int(verstrichen), wert("lernen.leerlauf_sekunden")))
    sitzung.dauer_sekunden += sekunden
    sitzung.letzte_aktivitaet = jetzt
    tag = tagesziel.lerntag_holen(kind, heute)
    tag.sekunden += sekunden
    neu_erreicht = False
    if not tag.mindesttag and tag.sekunden >= wert("lernen.mindesttag_minuten") * 60:
        tag.mindesttag = True
        spielregeln.aktivitaet_erfassen(
            kind,
            heute,
            modul=QUELLE,
            referenz=f"tag:{kind.pk}:{heute.isoformat()}",
            erfasst_am=jetzt,
        )
    if not tag.erreicht and tag.sekunden >= tag.ziel_minuten * 60:
        tag.erreicht = True
        neu_erreicht = True
        _tagesziel_belohnen(kind, tag, heute)
    tag.save()
    return neu_erreicht


def _tagesziel_belohnen(kind, tag, heute):
    """Fester Betrag fürs Tagesziel (Beteiligung), gedeckelt und abschaltbar; dazu das Ereignis."""
    betrag = 0
    if wert("lernen.lernpunkte_aktiv"):
        betrag = min(
            wert("lernen.tagesziel_punkte"),
            max(0, wert("lernen.lernpunkte_tageslimit") - tag.punkte),
        )
    if betrag > 0:
        punkte.buchen(
            kind,
            punkte.Art.MODUL,
            betrag,
            schluessel=f"lernen:tagesziel:{kind.pk}:{heute.isoformat()}",
            quelle_modul=QUELLE,
            bezugsdatum=heute,
            referenz=tag,
            von=kind,
        )
        tag.punkte += betrag
    stufe = selectors.sprachstufe(kind)
    ereignisse.veroeffentlichen(
        events.LERNZIEL_ERREICHT,
        kind=kind,
        daten={
            "datum": heute.isoformat(),
            "minuten": tag.ziel_minuten,
            "punkte": betrag,
            "hinweis_msgid": texte.msgid("ziel_geschafft", stufe),
            "hinweis_parameter": {},
        },
        schluessel=f"{events.LERNZIEL_ERREICHT}:{kind.pk}:{heute.isoformat()}",
    )


def _offen(sitzung):
    if sitzung.ende is not None:
        raise LernenFehler("Die Sitzung ist schon beendet.")
    if sitzung.aktuell_frage_id is None:
        raise LernenFehler("Es ist keine Frage offen.")
    return wiederholung.aufgabe_fuer(sitzung.aktuell_frage, sitzung.aktuell_richtung)


@transaction.atomic
def frage_stellen(sitzung, *, zufall=None, jetzt=None):
    """Die offene oder nächste Frage (``Aufgabe``), ``None`` wenn nichts mehr dran ist.
    Neuladen zeigt dieselbe Frage. Danach ist ``sitzung_beenden`` fällig."""
    if sitzung.ende is not None:
        return None
    jetzt = _jetzt(jetzt)
    _zeit_buchen(sitzung, jetzt)
    if sitzung.aktuell_frage_id is None:
        if sitzung.versuche >= sitzung.ziel_fragen:
            sitzung.save()
            return None
        kind, fach = sitzung.kind, sitzung.fach
        letzter = sitzung.antworten.order_by("-id").select_related("frage").first()
        wahl = wiederholung.naechste(
            kind,
            fach,
            selectors.themen_bis(fach, selectors.klassenstufe(kind, fach)),
            thema=sitzung.thema,
            vorhaben=sitzung.vorhaben,
            intensitaet=sitzung.intensitaet,
            heute=zeit.heute(jetzt),
            ausgeschlossen=set(sitzung.antworten.values_list("frage_id", "richtung")),
            letztes_thema=letzter.frage.thema_id if letzter else None,
            zufall=zufall or random.Random(),
        )
        if wahl is None:
            sitzung.save()
            return None
        sitzung.aktuell_frage, sitzung.aktuell_richtung = wahl
        sitzung.aktuell_seit = jetzt
        sitzung.aktuell_versuche = 0
        sitzung.aktuell_hilfe = 0
    sitzung.save()
    return wiederholung.aufgabe_fuer(sitzung.aktuell_frage, sitzung.aktuell_richtung)


def hinweis_text(loesung):
    """Hilfe 1: Anfangsbuchstabe und Länge, z. B. ``b _ _ _ _``. Kostet nichts."""
    return " ".join(
        zeichen if i == 0 or zeichen == " " else "_" for i, zeichen in enumerate(loesung)
    )


@transaction.atomic
def hilfe(sitzung, *, jetzt=None):
    """Hilfestufe 1 für die offene Frage; gibt den Hinweis zurück. Kostet keine Punkte."""
    aufgabe = _offen(sitzung)
    _zeit_buchen(sitzung, _jetzt(jetzt))
    sitzung.aktuell_hilfe = max(sitzung.aktuell_hilfe, 1)
    sitzung.hilfestufe_max = max(sitzung.hilfestufe_max, 1)
    sitzung.save()
    return hinweis_text(aufgabe.loesung)


def _abschliessen(sitzung, aufgabe, ergebnis, eingabe, hilfestufe, jetzt):
    """Eine beantwortete Frage verbuchen: Versuch, Lernstand, Zähler, Frust, Zeit."""
    dauer_ms = max(0, int((jetzt - (sitzung.aktuell_seit or jetzt)).total_seconds() * 1000))
    Versuch.objects.create(
        sitzung=sitzung,
        frage=aufgabe.frage,
        richtung=aufgabe.richtung,
        ergebnis=ergebnis,
        hilfestufe=hilfestufe,
        eingabe=eingabe[:300],
        dauer_ms=dauer_ms,
    )
    richtig = ergebnis == Ergebnis.RICHTIG
    wiederholung.stand_buchen(
        sitzung.kind, aufgabe.frage, aufgabe.richtung, richtig, zeit.heute(jetzt), jetzt
    )
    sitzung.versuche += 1
    sitzung.richtig += 1 if richtig else 0
    sitzung.hilfestufe_max = max(sitzung.hilfestufe_max, hilfestufe)
    sitzung.aktuell_frage = None
    sitzung.aktuell_richtung = ""
    sitzung.aktuell_seit = None
    sitzung.aktuell_versuche = 0
    sitzung.aktuell_hilfe = 0
    ziel_erreicht = _zeit_buchen(sitzung, jetzt)
    senkt = False
    pause = False
    if not sitzung.frust_erkannt:
        letzte = list(sitzung.antworten.order_by("-id").values_list("ergebnis", "dauer_ms")[:20])
        if frust.erkennen(letzte[::-1]) is not None:
            sitzung.frust_erkannt = True
            pause = True
            senkt = _stufe_senken(sitzung)
    sitzung.save()
    return pause, senkt, ziel_erreicht


_STUFEN = [Intensitaet.AUFWAERMEN, Intensitaet.NORMAL, Intensitaet.HERAUSFORDERUNG]


def _stufe_senken(sitzung):
    """Eine Stufe leichter, soweit möglich. ``True``, wenn sich etwas geändert hat."""
    stufe = _STUFEN.index(sitzung.intensitaet)
    if stufe == 0:
        return False
    sitzung.intensitaet = _STUFEN[stufe - 1]
    return True


@transaction.atomic
def antworten(sitzung, eingabe, *, jetzt=None):
    """Prüft die Antwort auf die offene Frage. Ein kleiner Tippfehler ergibt beim ersten Mal
    "fast richtig" und dieselbe Frage noch einmal, sonst richtig oder noch nicht."""
    aufgabe = _offen(sitzung)
    jetzt = _jetzt(jetzt)
    stufe = selectors.sprachstufe(sitzung.kind, sitzung.fach)
    pruefung_ = pruefung.pruefen(eingabe, aufgabe.erwartet)
    if pruefung_.fast and sitzung.aktuell_versuche == 0:
        sitzung.aktuell_versuche += 1
        Versuch.objects.create(
            sitzung=sitzung,
            frage=aufgabe.frage,
            richtung=aufgabe.richtung,
            ergebnis=Ergebnis.FAST,
            hilfestufe=sitzung.aktuell_hilfe,
            eingabe=eingabe[:300],
            dauer_ms=max(0, int((jetzt - (sitzung.aktuell_seit or jetzt)).total_seconds() * 1000)),
        )
        _zeit_buchen(sitzung, jetzt)
        sitzung.save()
        return Rueckmeldung(Ergebnis.FAST, texte.ton("fast", stufe), nochmal=True)
    ergebnis = Ergebnis.RICHTIG if pruefung_.richtig else Ergebnis.NOCH_NICHT
    pause, senkt, erreicht = _abschliessen(
        sitzung, aufgabe, ergebnis, eingabe, sitzung.aktuell_hilfe, jetzt
    )
    return Rueckmeldung(
        ergebnis,
        texte.ton("richtig" if ergebnis == Ergebnis.RICHTIG else "noch_nicht", stufe),
        loesung="" if ergebnis == Ergebnis.RICHTIG else aufgabe.loesung,
        pause_vorschlag=pause,
        stufe_gesenkt=senkt,
        ziel_erreicht=erreicht,
    )


@transaction.atomic
def loesung_zeigen(sitzung, *, jetzt=None):
    """Hilfestufe 2: Das Kind schaut die Lösung an. Zählt als "noch nicht", die Frage kommt
    bald wieder; es kostet keine Punkte."""
    aufgabe = _offen(sitzung)
    stufe = selectors.sprachstufe(sitzung.kind, sitzung.fach)
    pause, senkt, erreicht = _abschliessen(
        sitzung, aufgabe, Ergebnis.NOCH_NICHT, "", 2, _jetzt(jetzt)
    )
    return Rueckmeldung(
        Ergebnis.NOCH_NICHT,
        texte.ton("loesung", stufe),
        loesung=aufgabe.loesung,
        pause_vorschlag=pause,
        stufe_gesenkt=senkt,
        ziel_erreicht=erreicht,
    )


@transaction.atomic
def sitzung_beenden(sitzung, *, jetzt=None):
    """Beendet die Sitzung (idempotent) und verbucht die letzte Zeit."""
    if sitzung.ende is not None:
        return sitzung
    jetzt = _jetzt(jetzt)
    _zeit_buchen(sitzung, jetzt)
    sitzung.ende = jetzt
    sitzung.aktuell_frage = None
    sitzung.aktuell_richtung = ""
    sitzung.aktuell_seit = None
    sitzung.save()
    return sitzung


@transaction.atomic
def rueckschau_speichern(sitzung, schwer="", geholfen="", einschaetzung=""):
    """Die zwei Fragen nach dem Üben (Was war schwer? Was hat geholfen?) und optional, ob es
    zu leicht, passend oder zu schwer war. Alles darf leer bleiben; einmal gespeichert gilt sie."""
    if sitzung.ende is None:
        sitzung_beenden(sitzung)
    if sitzung.rueckschau_fertig:
        return sitzung
    sitzung.rueckschau_schwer = " ".join(str(schwer).split())[:RUECKSCHAU_MAX]
    sitzung.rueckschau_geholfen = " ".join(str(geholfen).split())[:RUECKSCHAU_MAX]
    if einschaetzung:
        sitzung.selbsteinschaetzung = _wahl(einschaetzung, Selbsteinschaetzung, "Einschätzung")
    sitzung.rueckschau_fertig = True
    sitzung.save()
    return sitzung


@transaction.atomic
def vorschlag_entscheiden(kind, *, annehmen, heute=None):
    """Das Kind nimmt den Vorschlag für ein höheres Tagesziel an oder lässt ihn."""
    _kind_pruefen(kind)
    tagesziel.vorschlag_entscheiden(kind, heute or zeit.heute(), annehmen=annehmen)


# --- Schonung (Eltern) -------------------------------------------------------------------------


def pause_eintragen(kind, von, bis, grund=PausenGrund.KRANK):
    """Eltern tragen Pausentage ein (``kind=None``: alle Kinder). Dann fehlt kein Ziel."""
    if bis < von:
        raise LernenFehler("Das Ende liegt vor dem Anfang.")
    _wahl(grund, PausenGrund, "Grund")
    return Lernpause.objects.create(kind=kind, von=von, bis=bis, grund=grund)


def pause_loeschen(pause):
    pause.delete()
