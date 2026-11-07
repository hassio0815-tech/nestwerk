"""Schreiben für lernen: Fundament (Etappe 1) und Üben ohne KI (Etappe 2).

Ablauf einer Lernsitzung (SPEC 21.2): ``sitzung_starten`` (Vorhaben, Strategie, Intensität,
Selbsteinschätzung) -> ``frage_stellen`` / ``antworten`` / ``hilfe`` / ``loesung_zeigen`` im
Wechsel -> ``sitzung_beenden`` -> ``rueckschau_speichern``.

- Gemessen wird die aktive Zeit (lange Denkpausen zählen nicht, ``lernen.leerlauf_sekunden``).
- Punkte gibt es nur für den Prozess: feste Beträge (nie pro richtige Antwort) für das Tagesziel
  und, je höchstens einmal am Tag, für Selbsttest, Fehlerüberarbeitung und Rückschau; alles
  gedeckelt durch ``lernen.lernpunkte_tageslimit``, abschaltbar durch ``lernen.lernpunkte_aktiv``.
  Hilfen kosten nichts. Eine gerissene Serie nimmt nie Punkte.
- Eine Runde zählt nach Zeit (``lernen.runde_ziel``, weiche Grenze) oder nach Fragen; einmal je
  Runde schlägt ``lernen.pause_nach_minuten`` eine Pause vor.
- Jede Änderung läuft in einer Transaktion, ebenso Buchung, Aktivität und Ereignis.
"""

import random
from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext as _

from apps.ereignisse import services as ereignisse
from apps.kern import zeit
from apps.kern.einstellungen import wert
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte
from apps.spielregeln import services as spielregeln

from . import (
    events,
    frust,
    historie,
    mathe_aufgaben,
    mathe_ki,
    plan_selectors,
    selectors,
    tagesziel,
    texte,
    wiederholung,
)
from .mathe import fehler as mathe_fehler
from .mathe import hilfe as mathe_hilfe
from .models import (
    Ergebnis,
    Erwartung,
    Fehlergrund,
    Frage,
    Freigabe,
    Intensitaet,
    Leistungsstufe,
    Lernmappe,
    Lernpause,
    Lernsitzung,
    PausenGrund,
    Quelle,
    Richtung,
    Selbsteinschaetzung,
    Strategie,
    Thema,
    Versuch,
    Vorhaben,
)
from .speicher import Speicher

QUELLE = "lernen"  # quelle_modul der Buchungen, modul der Aktivität
RUECKSCHAU_MAX = 300
ERKLAERUNG_AB_STUFE = 3  # "Erkläre es anders" gibt es, wenn das analoge Beispiel offen ist


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
    hinweis: str = ""  # Mathe: gezielter Hinweis zum Fehler (nie mit der Lösung)
    rechnung: bool = (
        False  # Lösung einer erzeugten Mathe-Aufgabe (andere Anzeige als "So heißt es")
    )
    rechenweg: tuple = ()  # Mathe: die Rechenschritte mit Zwischenergebnissen (mit der Lösung)
    pause_grund: str = ""  # "frust" oder "zeit", wenn pause_vorschlag gesetzt ist
    versuch_id: int | None = None  # der gebuchte Versuch (für den freiwilligen Fehlergrund)
    fehlergrund_frage: bool = False  # nach "noch nicht" ab der Klassenstufe: woran lag es?


def _jetzt(jetzt):
    return jetzt or zeit.jetzt()


def _rechenweg(aufgabe):
    """Die Rechenschritte der Aufgabe für die Lösungsanzeige (nur bei erzeugten Mathe-Aufgaben)."""
    if not aufgabe.generiert:
        return ()
    mathe = mathe_hilfe.aufgabe_aus_frage(aufgabe.frage)
    return tuple(mathe_hilfe.rechenweg(mathe)) if mathe is not None else ()


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
    portion=None,
    ziel_fragen=None,
    jetzt=None,
):
    """Legt eine Sitzung an. Gibt es noch eine offene, wird sie zuerst beendet (nur eine läuft).
    ``portion``: Portion eines Prüfungsplans (Etappe 6); dann üben nur ihre Fragen."""
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
    mathe_aufgaben.aufraeumen(jetzt)
    minuten = 0
    if ziel_fragen is None and portion is None and wert("lernen.runde_ziel") == "minuten":
        # Etappe 14: die Runde zählt nach Zeit; die Fragenzahl ist nur eine Sicherheitsgrenze
        minuten = wert(f"lernen.minuten_{intensitaet}")
        anzahl = wert("lernen.fragen_max_sitzung")
    else:
        anzahl = (
            ziel_fragen
            or (portion is None and mathe_aufgaben.aufgaben_je_runde(fach))
            or wert(f"lernen.fragen_{intensitaet}")
        )
    return Lernsitzung.objects.create(
        portion=portion,
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
        ziel_minuten=minuten,
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
    if neu_erreicht:
        # Die Metrik "Lern-Beteiligung" ist neu: Abzeichen und Meilensteine prüfen (Engine-Vorgabe)
        spielregeln.abzeichen_pruefen(kind)
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


def betrag_buchen(kind, soll, schluessel, referenz, heute):
    """Fester Betrag unter dem Lernpunkte-Tageslimit; nichts bei ausgeschalteten Lernpunkten.
    Idempotent über den Schlüssel. Gibt den gebuchten Betrag zurück (0 = nichts)."""
    if soll <= 0 or not wert("lernen.lernpunkte_aktiv"):
        return 0
    if punkte_selectors.buchung_zu_schluessel(schluessel) is not None:
        return 0
    tag = tagesziel.lerntag_holen(kind, heute)
    betrag = min(soll, max(0, wert("lernen.lernpunkte_tageslimit") - tag.punkte))
    if betrag <= 0:
        return 0
    punkte.buchen(
        kind,
        punkte.Art.MODUL,
        betrag,
        schluessel=schluessel,
        quelle_modul=QUELLE,
        bezugsdatum=heute,
        referenz=referenz,
        von=kind,
    )
    tag.punkte += betrag
    tag.save(update_fields=["punkte"])
    return betrag


def tagespunkte_buchen(kind, art, einstellung, referenz, heute):
    """Prozesspunkte für ``art`` (Selbsttest, Fehlerüberarbeitung, Rückschau): ein fester Betrag,
    höchstens einmal je Kind, Tag und Art, nie pro Antwort, unter dem Tageslimit."""
    return betrag_buchen(
        kind, wert(einstellung), f"lernen:{art}:{kind.pk}:{heute.isoformat()}", referenz, heute
    )


def _offen(sitzung):
    if sitzung.ende is not None:
        raise LernenFehler("Die Sitzung ist schon beendet.")
    if sitzung.aktuell_frage_id is None:
        raise LernenFehler("Es ist keine Frage offen.")
    return wiederholung.aufgabe_fuer(sitzung.aktuell_frage, sitzung.aktuell_richtung)


@transaction.atomic
def _naechste_wahl(sitzung, zufall, jetzt):
    """Das nächste Paar (Frage, Richtung): erzeugte Mathe-Aufgabe (SPEC 21.13) oder gespeicherte
    Frage nach der Abstandswiederholung. ``None``, wenn nichts mehr dran ist."""
    zufall = zufall or random.Random()
    if mathe_aufgaben.nutzt_generator(sitzung):
        frage = mathe_aufgaben.naechste(sitzung, zufall=zufall, jetzt=jetzt)
        return (frage, Richtung.DE_EN) if frage is not None else None
    kind, fach = sitzung.kind, sitzung.fach
    letzter = sitzung.antworten.order_by("-id").select_related("frage").first()
    themen = selectors.themen_fuer(kind, fach)
    thema, nur = sitzung.thema, None
    if sitzung.portion_id:  # Prüfungsportion: nur ihre Fragen, gleich aus welchem Fach
        nur = frozenset(plan_selectors.portion_fragen(sitzung.portion))
        themen, thema = Thema.objects.filter(fragen__pk__in=nur).distinct(), None
    return wiederholung.naechste(
        kind,
        fach,
        themen,
        nur_fragen=nur,
        thema=thema,
        vorhaben=sitzung.vorhaben,
        intensitaet=sitzung.intensitaet,
        heute=zeit.heute(jetzt),
        ausgeschlossen=set(sitzung.antworten.values_list("frage_id", "richtung")),
        letztes_thema=letzter.frage.thema_id if letzter else None,
        zufall=zufall,
    )


def _zeit_um(sitzung):
    """Weiche Grenze der Runde nach Zeit: gilt erst zwischen zwei Fragen, nie mitten drin."""
    return sitzung.ziel_minuten > 0 and sitzung.dauer_sekunden >= sitzung.ziel_minuten * 60


def frage_stellen(sitzung, *, zufall=None, jetzt=None):
    """Die offene oder nächste Frage (``Aufgabe``), ``None`` wenn nichts mehr dran ist.
    Neuladen zeigt dieselbe Frage. Danach ist ``sitzung_beenden`` fällig."""
    if sitzung.ende is not None:
        return None
    jetzt = _jetzt(jetzt)
    _zeit_buchen(sitzung, jetzt)
    if sitzung.aktuell_frage_id is None:
        if sitzung.versuche >= sitzung.ziel_fragen or _zeit_um(sitzung):
            sitzung.save()
            return None
        wahl = _naechste_wahl(sitzung, zufall, jetzt)
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


def mathe_hilfe_stufe_max():
    """Höchste Stufe der Mathe-Hilfeleiter, die die Eltern erlauben (Einstellung, Standard 5)."""
    return max(1, min(mathe_hilfe.MAX_STUFE, wert("lernen.mathe_hilfe_max_stufe")))


def _hat_mathe_hilfe(aufgabe):
    return aufgabe.generiert and mathe_hilfe.hat_hilfe(aufgabe.frage.generator)


@transaction.atomic
def hilfe(sitzung, *, jetzt=None):
    """Hilfe für die offene Frage; kostet keine Punkte.

    Mathe-Aufgaben: die nächste Stufe der Hilfeleiter (SPEC 21.3, höchstens die erlaubte); die
    Texte holt ``hilfe_stufen``, der Rückgabewert ist dann leer. Sonst Stufe 1 wie bisher:
    Anfangsbuchstabe und Länge, z. B. ``b _ _ _ _``."""
    aufgabe = _offen(sitzung)
    _zeit_buchen(sitzung, _jetzt(jetzt))
    if _hat_mathe_hilfe(aufgabe):
        stufe = min(sitzung.aktuell_hilfe + 1, mathe_hilfe_stufe_max())
        sitzung.aktuell_hilfe = max(sitzung.aktuell_hilfe, stufe)
        sitzung.hilfestufe_max = max(sitzung.hilfestufe_max, stufe)
        sitzung.save()
        return ""
    sitzung.aktuell_hilfe = max(sitzung.aktuell_hilfe, 1)
    sitzung.hilfestufe_max = max(sitzung.hilfestufe_max, 1)
    sitzung.save()
    return hinweis_text(aufgabe.loesung)


def hilfe_stufen(sitzung):
    """Die Texte der Hilfestufen 1 bis zur freigeschalteten für die offene Mathe-Aufgabe (sonst
    leer). Aus den gespeicherten Zahlen der Aufgabe, ohne ihre Lösung."""
    if sitzung.aktuell_frage_id is None or sitzung.aktuell_hilfe < 1:
        return []
    aufgabe = wiederholung.aufgabe_fuer(sitzung.aktuell_frage, sitzung.aktuell_richtung)
    if not _hat_mathe_hilfe(aufgabe):
        return []
    mathe = mathe_hilfe.aufgabe_aus_frage(aufgabe.frage)
    if mathe is None:
        return []
    stufe = selectors.sprachstufe(sitzung.kind, sitzung.fach)
    return mathe_hilfe.stufen_bis(mathe, min(sitzung.aktuell_hilfe, mathe_hilfe_stufe_max()), stufe)


def hilfe_kontext(sitzung, aufgabe):
    """Alles, was die Seite für Hilfe und Erklärkarte der offenen Aufgabe braucht."""
    if aufgabe is None:
        return {}
    if not _hat_mathe_hilfe(aufgabe):
        return {"hilfe_weiter": True, "hilfe_text": _("Tipp")}
    stufen = hilfe_stufen(sitzung)
    mathe = mathe_hilfe.aufgabe_aus_frage(aufgabe.frage)
    karte = karte_verborgen = None
    if mathe is not None:
        anzeige = mathe_hilfe.karte_anzeige(
            mathe, selectors.sprachstufe(sitzung.kind, sitzung.fach)
        )
        if anzeige is not None:
            karte, karte_verborgen = anzeige
    return {
        "hilfe_stufen": stufen,
        "hilfe_weiter": sitzung.aktuell_hilfe < mathe_hilfe_stufe_max(),
        "hilfe_text": _("Mehr Hilfe") if stufen else _("Hilfe"),
        "erklaerung_moeglich": sitzung.aktuell_hilfe >= ERKLAERUNG_AB_STUFE
        and mathe_ki.erklaerung_bereit(),
        "karte": karte,
        "karte_verborgen": karte_verborgen,
    }


def _abschliessen(sitzung, aufgabe, ergebnis, eingabe, hilfestufe, jetzt, fehlertyp=""):
    """Eine beantwortete Frage verbuchen: Versuch, Lernstand, Zähler, Frust, Zeit. Gibt
    ``(versuch, pause_grund, stufe_gesenkt, ziel_erreicht)`` zurück."""
    dauer_ms = max(0, int((jetzt - (sitzung.aktuell_seit or jetzt)).total_seconds() * 1000))
    felder = historie.versuch_felder(sitzung.kind, aufgabe.frage, aufgabe.richtung)
    versuch = Versuch.objects.create(
        sitzung=sitzung,
        frage=aufgabe.frage,
        richtung=aufgabe.richtung,
        ergebnis=ergebnis,
        hilfestufe=hilfestufe,
        eingabe=eingabe[:300],
        dauer_ms=dauer_ms,
        fehlertyp=fehlertyp,
        **felder,
    )
    richtig = ergebnis == Ergebnis.RICHTIG
    median_ms = wiederholung.median_dauer_ms(sitzung.kind) if richtig and hilfestufe == 0 else None
    wiederholung.stand_buchen(
        sitzung.kind,
        aufgabe.frage,
        aufgabe.richtung,
        richtig,
        zeit.heute(jetzt),
        jetzt,
        hilfestufe=hilfestufe,
        karte=felder["karte"],
        dauer_ms=dauer_ms,
        median_ms=median_ms,
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
    grund = ""
    if not sitzung.frust_erkannt:
        letzte = list(sitzung.antworten.order_by("-id").values_list("ergebnis", "dauer_ms")[:20])
        if frust.erkennen(letzte[::-1]) is not None:
            sitzung.frust_erkannt = True
            sitzung.pause_vorgeschlagen = True  # eine Pause je Runde genügt
            grund = "frust"
            senkt = _stufe_senken(sitzung)
    if not grund and not sitzung.pause_vorgeschlagen:
        # Etappe 14 (W-10): auch ohne Frust ein Pausen-Vorschlag, einmal nach N Minuten
        nach = wert("lernen.pause_nach_minuten")
        if nach and sitzung.dauer_sekunden >= nach * 60:
            sitzung.pause_vorgeschlagen = True
            grund = "zeit"
    sitzung.save()
    _portion_pruefen(sitzung, jetzt)
    return versuch, grund, senkt, ziel_erreicht


def _fehlergrund_frage(sitzung, ergebnis):
    """Nach "noch nicht" ab der eingestellten Klassenstufe darf das Kind sagen, woran es lag."""
    if ergebnis != Ergebnis.NOCH_NICHT or sitzung.fach_id is None:
        return False
    klasse = selectors.klassenstufe(sitzung.kind, sitzung.fach)
    return klasse is not None and klasse >= wert("lernen.fehlergrund_ab_klasse")


def _portion_pruefen(sitzung, jetzt):
    """Gehört die Sitzung zu einer Prüfungsportion, zählt der Fortschritt dort (Etappe 6)."""
    if sitzung.portion_id:
        from . import plan_services

        plan_services.fortschritt_pruefen(sitzung, jetzt)


_STUFEN = [Intensitaet.AUFWAERMEN, Intensitaet.NORMAL, Intensitaet.HERAUSFORDERUNG]


def _stufe_senken(sitzung):
    """Eine Stufe leichter, soweit möglich. ``True``, wenn sich etwas geändert hat."""
    stufe = _STUFEN.index(sitzung.intensitaet)
    if stufe == 0:
        return False
    sitzung.intensitaet = _STUFEN[stufe - 1]
    return True


def _noch_einmal(sitzung, aufgabe, eingabe, pruefung_, jetzt):
    """Erster Versuch mit erkanntem Fehler: Hinweis zeigen, dieselbe Aufgabe noch einmal."""
    sitzung.aktuell_versuche += 1
    Versuch.objects.create(
        sitzung=sitzung,
        frage=aufgabe.frage,
        richtung=aufgabe.richtung,
        ergebnis=Ergebnis.FAST,
        hilfestufe=sitzung.aktuell_hilfe,
        eingabe=eingabe[:300],
        dauer_ms=max(0, int((jetzt - (sitzung.aktuell_seit or jetzt)).total_seconds() * 1000)),
        fehlertyp=pruefung_.fehlertyp,
        **historie.versuch_felder(sitzung.kind, aufgabe.frage, aufgabe.richtung),
    )
    _zeit_buchen(sitzung, jetzt)
    sitzung.save()
    return Rueckmeldung(Ergebnis.FAST, pruefung_.hinweis, nochmal=True, hinweis=pruefung_.hinweis)


@transaction.atomic
def antworten(sitzung, eingabe, *, jetzt=None):
    """Prüft die Antwort auf die offene Frage. Ein kleiner Tippfehler ergibt beim ersten Mal
    "fast richtig" und dieselbe Frage noch einmal, sonst richtig oder noch nicht."""
    aufgabe = _offen(sitzung)
    jetzt = _jetzt(jetzt)
    stufe = selectors.sprachstufe(sitzung.kind, sitzung.fach)
    pruefung_ = aufgabe.pruefen(eingabe)
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
            fehlertyp=pruefung_.fehlertyp,
            **historie.versuch_felder(sitzung.kind, aufgabe.frage, aufgabe.richtung),
        )
        _zeit_buchen(sitzung, jetzt)
        sitzung.save()
        return Rueckmeldung(
            Ergebnis.FAST, pruefung_.hinweis or texte.ton("fast", stufe), nochmal=True
        )
    if (
        aufgabe.generiert
        and not pruefung_.richtig
        and pruefung_.fehlertyp in mathe_fehler.ZWEITE_CHANCE
        and sitzung.aktuell_versuche == 0
    ):
        # Mathe: ein erkannter Fehler bekommt einen gezielten Hinweis (ohne Lösung) und einen
        # zweiten Versuch, statt gleich die Lösung zu zeigen. Es kostet keine Punkte.
        return _noch_einmal(sitzung, aufgabe, eingabe, pruefung_, jetzt)
    ergebnis = Ergebnis.RICHTIG if pruefung_.richtig else Ergebnis.NOCH_NICHT
    versuch, grund, senkt, erreicht = _abschliessen(
        sitzung, aufgabe, ergebnis, eingabe, sitzung.aktuell_hilfe, jetzt, pruefung_.fehlertyp
    )
    return Rueckmeldung(
        ergebnis,
        texte.ton("richtig" if ergebnis == Ergebnis.RICHTIG else "noch_nicht", stufe),
        loesung="" if ergebnis == Ergebnis.RICHTIG else aufgabe.loesung,
        rechnung=aufgabe.generiert,
        rechenweg=() if ergebnis == Ergebnis.RICHTIG else _rechenweg(aufgabe),
        hinweis="" if ergebnis == Ergebnis.RICHTIG else pruefung_.hinweis,
        pause_vorschlag=bool(grund),
        pause_grund=grund,
        stufe_gesenkt=senkt,
        ziel_erreicht=erreicht,
        versuch_id=versuch.pk,
        fehlergrund_frage=_fehlergrund_frage(sitzung, ergebnis),
    )


@transaction.atomic
def loesung_zeigen(sitzung, *, jetzt=None):
    """Hilfestufe 2: Das Kind schaut die Lösung an. Zählt als "noch nicht", die Frage kommt
    bald wieder; es kostet keine Punkte."""
    aufgabe = _offen(sitzung)
    stufe = selectors.sprachstufe(sitzung.kind, sitzung.fach)
    versuch, grund, senkt, erreicht = _abschliessen(
        sitzung, aufgabe, Ergebnis.NOCH_NICHT, "", max(2, sitzung.aktuell_hilfe), _jetzt(jetzt)
    )
    return Rueckmeldung(
        Ergebnis.NOCH_NICHT,
        texte.ton("loesung", stufe),
        loesung=aufgabe.loesung,
        rechnung=aufgabe.generiert,
        rechenweg=_rechenweg(aufgabe),
        pause_vorschlag=bool(grund),
        pause_grund=grund,
        stufe_gesenkt=senkt,
        ziel_erreicht=erreicht,
        versuch_id=versuch.pk,
        fehlergrund_frage=_fehlergrund_frage(sitzung, Ergebnis.NOCH_NICHT),
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
    _fehlerueberarbeitung_belohnen(sitzung, jetzt)
    _portion_pruefen(sitzung, jetzt)
    return sitzung


def _fehlerueberarbeitung_belohnen(sitzung, jetzt):
    """Eine Runde "Meine Stolperstellen üben" mit genug Antworten ist eine Fehlerüberarbeitung:
    fester Betrag, höchstens einmal am Tag (W-9)."""
    if sitzung.vorhaben == Vorhaben.STOLPERSTELLEN and sitzung.versuche >= wert(
        "lernen.fehlerueberarbeitung_min_antworten"
    ):
        tagespunkte_buchen(
            sitzung.kind,
            "fehlerueberarbeitung",
            "lernen.punkte_fehlerueberarbeitung",
            sitzung,
            zeit.heute(jetzt),
        )


@transaction.atomic
def fehlergrund_speichern(sitzung, versuch_id, grund):
    """Das Kind sagt nach "noch nicht", woran es lag (freiwillig, ändert nichts an Punkten oder
    Wiederholung). Nur für einen "noch nicht"-Versuch der eigenen Sitzung."""
    grund = _wahl(grund, Fehlergrund, "Fehlergrund")
    versuch = sitzung.antworten.filter(pk=versuch_id, ergebnis=Ergebnis.NOCH_NICHT).first()
    if versuch is None:
        raise LernenFehler("Zu dieser Antwort gibt es keinen Fehlergrund.")
    versuch.fehlergrund = grund
    versuch.save(update_fields=["fehlergrund"])
    return versuch


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
    if sitzung.rueckschau_schwer or sitzung.rueckschau_geholfen or sitzung.selbsteinschaetzung:
        tagespunkte_buchen(
            sitzung.kind,
            "rueckschau",
            "lernen.punkte_rueckschau",
            sitzung,
            zeit.heute(sitzung.ende),
        )
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
