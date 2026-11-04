"""Schreiben für die Prüfungsvorbereitung (SPEC 21.7, 21.2).

- ``pruefung_anlegen`` baut den Plan rückwärts vom Termin aus. Ist das Pensum nicht schaffbar,
  entsteht **kein** Plan (Realitätscheck mit Vorschlägen); Kind und Eltern entscheiden.
- ``tag_pflegen`` schiebt verpasste Portionen ohne Schuldzuweisung auf spätere Tage (erst die
  Puffertage, dann erneuter Realitätscheck) und vergibt die kleinen Boni. Nie werden Punkte
  abgezogen.
- Eine Portion gilt erst als erledigt, wenn wirklich geübt wurde (Mindestanzahl Antworten oder
  Mindestzeit, beides Einstellungen).
- Punkte gibt es nur für den Prozess: ein fester kleiner Betrag für eine eingehaltene Planwoche
  und für eine vorbereitete Prüfung, unter dem Lernpunkte-Tageslimit und nur bei eingeschalteten
  Lernpunkten. Nie pro richtige Antwort.
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

from . import events, plan, plan_selectors, plan_texte, selectors, services, tagesziel
from .models import (
    Ergebnis,
    Frage,
    PortionArt,
    PortionStatus,
    ProbePruefung,
    ProbeVersuch,
    Pruefung,
    Pruefungsportion,
    Pruefungsstoff,
    PruefungStatus,
    Richtung,
    Vorhaben,
)

TITEL_MAX = 80


class PlanFehler(ValueError):
    """Fachlicher Fehler der Prüfungsvorbereitung (freundlich formuliert, darf angezeigt werden)."""


def _stufe(kind, fach=None):
    return selectors.sprachstufe(kind, fach)


# --- Anlegen und Planen ---------------------------------------------------------------------------


@transaction.atomic
def pruefung_anlegen(kind, fach, titel, termin, *, themen=(), materialien=(), heute=None):
    """Legt Prüfung und Stoff an und rechnet den Plan. Der Plan kann ``plan_ok=False`` haben:
    dann hat das Kind einen Realitätscheck mit Vorschlägen vor sich, aber keinen vollen Plan."""
    services._kind_pruefen(kind)  # noqa: SLF001
    heute = heute or zeit.heute()
    stufe = _stufe(kind, fach)
    if not fach.aktiv:
        raise PlanFehler(_("Dieses Fach gibt es gerade nicht."))
    if termin <= heute:
        raise PlanFehler(plan_texte.ton("termin_vorbei", stufe))
    sichtbare_themen = {t.pk: t for t in plan_selectors.themen_zur_auswahl(kind, fach)}
    sichtbares_material = {m.pk: m for m in plan_selectors.materialien_zur_auswahl(kind, fach)}
    themen = [sichtbare_themen.get(getattr(t, "pk", t)) for t in themen]
    materialien = [sichtbares_material.get(getattr(m, "pk", m)) for m in materialien]
    if None in themen or None in materialien:
        raise PlanFehler(_("Dieser Stoff gehört nicht zu deinem Fach."))
    if not themen and not materialien:
        raise PlanFehler(plan_texte.ton("kein_stoff", stufe))
    titel = " ".join(str(titel).split())[:TITEL_MAX] or fach.name
    neu = Pruefung.objects.create(kind=kind, fach=fach, titel=titel, termin=termin)
    for t in dict.fromkeys(themen):
        Pruefungsstoff.objects.create(pruefung=neu, thema=t)
    for m in dict.fromkeys(materialien):
        Pruefungsstoff.objects.create(pruefung=neu, material=m)
    plan_berechnen(neu, heute)
    return neu


@transaction.atomic
def plan_berechnen(pruefung_, heute=None, *, nachholen=False):
    """Rechnet den Plan neu. Erledigtes bleibt, offene Zukunft wird ersetzt, offene Vergangenheit
    gilt als verschoben. Geht es nicht auf, ändert sich am Plan nichts außer ``plan_ok``.

    ``nachholen``: Ausfall aufholen. Die Puffertage bleiben erst Reserve und werden nur gebraucht,
    wenn es sonst nicht passt."""
    heute = heute or zeit.heute()
    if pruefung_.status in (PruefungStatus.ABGESCHLOSSEN, PruefungStatus.ABGEBROCHEN):
        return None
    tagesziel.ferien_abgleichen(heute)
    kwargs = plan_selectors.eingabe(pruefung_, heute, nachholen=nachholen)
    ergebnis = plan.plane(**kwargs)
    if not ergebnis.ok and nachholen and ergebnis.grund == plan.GRUND_ZU_VIEL:
        ergebnis = plan.plane(**kwargs, puffer_nutzen=True)
    if not ergebnis.ok:
        pruefung_.plan_ok = False
        pruefung_.save(update_fields=["plan_ok"])
        return ergebnis
    _schreiben(pruefung_, ergebnis, heute, nachholen)
    return ergebnis


def _schreiben(pruefung_, ergebnis, heute, nachholen):
    offen = pruefung_.portionen.filter(status=PortionStatus.OFFEN)
    verschoben = offen.filter(datum__lt=heute, art__in=(PortionArt.NEU, PortionArt.WIEDERHOLUNG))
    anzahl_verschoben = verschoben.count()
    verschoben.update(status=PortionStatus.VERSCHOBEN)
    offen.exclude(status=PortionStatus.VERSCHOBEN).delete()
    stoffe = {str(s.pk): s for s in pruefung_.stoffe.all()}
    Pruefungsportion.objects.bulk_create(
        Pruefungsportion(
            pruefung=pruefung_,
            stoff=stoffe.get(e.stoff),
            datum=e.datum,
            art=e.art,
            minuten=e.minuten,
            fragen=list(e.fragen),
            pflicht=e.pflicht,
        )
        for e in ergebnis.eintraege
    )
    pruefung_.plan_ok = True
    pruefung_.puffer_genutzt = ergebnis.puffer_genutzt
    if nachholen and anzahl_verschoben:
        pruefung_.plan_angepasst_am = heute
    erste = next((e.datum for e in ergebnis.eintraege if e.art != plan.ART_PUFFER), None)
    if pruefung_.status == PruefungStatus.GEPLANT and erste is not None and erste <= heute:
        pruefung_.status = PruefungStatus.AKTIV
    pruefung_.save()


# --- Eingriffe von Kind und Eltern ---------------------------------------------------------------


@transaction.atomic
def termin_aendern(pruefung_, termin, heute=None):
    """Neuer Termin (Kind oder Eltern); der Plan wird neu gerechnet."""
    heute = heute or zeit.heute()
    if termin <= heute:
        raise PlanFehler(plan_texte.ton("termin_vorbei", _stufe(pruefung_.kind, pruefung_.fach)))
    pruefung_.termin = termin
    pruefung_.save(update_fields=["termin"])
    return plan_berechnen(pruefung_, heute)


@transaction.atomic
def stoff_entfernen(pruefung_, stoff, heute=None):
    """Den Stoff verkleinern (Vorschlag des Realitätschecks): ein Stoffteil fällt weg."""
    if stoff.pruefung_id != pruefung_.pk:
        raise PlanFehler(_("Dieser Stoff gehört nicht zu dieser Prüfung."))
    if pruefung_.stoffe.count() <= 1:
        raise PlanFehler(_("Ein Stoffteil muss bleiben. Du kannst die Prüfung auch beenden."))
    stoff.delete()
    return plan_berechnen(pruefung_, heute or zeit.heute())


@transaction.atomic
def ziel_erhoehen(kind, pruefung_, minuten, heute=None):
    """Das Kind nimmt den Vorschlag an, pro Tag etwas länger zu üben. Nur auf eigenen Wunsch und
    höchstens um den Zuschlag aus den Einstellungen."""
    services._kind_pruefen(kind)  # noqa: SLF001
    heute = heute or zeit.heute()
    ziel = tagesziel.ziel_holen(kind, heute)
    if (
        not ziel.ziel_minuten
        < minuten
        <= ziel.ziel_minuten + wert("lernen.pruefung_ziel_zuschlag_max")
    ):
        raise PlanFehler(_("Dieses Ziel ist nicht möglich."))
    ziel.vorschlag_minuten = minuten
    ziel.save(update_fields=["vorschlag_minuten"])
    tagesziel.vorschlag_entscheiden(kind, heute, annehmen=True)
    return plan_berechnen(pruefung_, heute, nachholen=bool(pruefung_.portionen.exists()))


def pruefung_abbrechen(pruefung_):
    """Das Kind beendet die Vorbereitung. Der Plan bleibt zum Nachlesen, nichts wird bestraft."""
    if pruefung_.status in (PruefungStatus.GEPLANT, PruefungStatus.AKTIV):
        pruefung_.status = PruefungStatus.ABGEBROCHEN
        pruefung_.save(update_fields=["status"])
    return pruefung_


def pruefung_loeschen(pruefung_):
    """Eltern löschen die Prüfung samt Plan."""
    pruefung_.delete()


# --- Pflege: verpasste Tage, Abschluss, Boni -----------------------------------------------------


def tag_pflegen(kind, heute=None, jetzt=None):
    """Hält die Pläne des Kindes aktuell (beim Öffnen der Seiten). Idempotent.

    Verpasste Portionen wandern auf spätere Tage, ohne Vorwurf. Nach dem Termin ist die Prüfung
    abgeschlossen. Eine eingehaltene Planwoche gibt den kleinen Bonus."""
    jetzt = jetzt or zeit.jetzt()
    heute = heute or zeit.heute(jetzt)
    for p in list(plan_selectors.aktive_pruefungen(kind)):
        with transaction.atomic():
            if p.termin < heute:
                p.status = PruefungStatus.ABGESCHLOSSEN
                p.save(update_fields=["status"])
                continue
            if _verpasst(p, heute):
                plan_berechnen(p, heute, nachholen=True)
            elif p.status == PruefungStatus.GEPLANT:
                erste = p.portionen.exclude(art=PortionArt.PUFFER).order_by("datum").first()
                if erste and erste.datum <= heute:
                    p.status = PruefungStatus.AKTIV
                    p.save(update_fields=["status"])
            _wochen_belohnen(p, heute)
            _vorbereitet_pruefen(p, heute)


def _verpasst(p, heute):
    return p.portionen.filter(
        status=PortionStatus.OFFEN,
        datum__lt=heute,
        art__in=(PortionArt.NEU, PortionArt.WIEDERHOLUNG),
    ).exists()


# --- Üben einer Portion --------------------------------------------------------------------------


@transaction.atomic
def portion_starten(kind, portion, *, jetzt=None):
    """Startet das Üben der Portion (vorhandenes Üben aus Etappe 2). Läuft schon eine Sitzung zu
    dieser Portion, geht es dort weiter."""
    services._kind_pruefen(kind)  # noqa: SLF001
    if portion.pruefung.kind_id != kind.pk:
        raise PlanFehler(_("Diese Portion gehört nicht zu dir."))
    if portion.pruefung.status not in plan_selectors.AKTIVE:
        raise PlanFehler(_("Diese Prüfung ist beendet."))
    if portion.art == PortionArt.PUFFER or portion.status != PortionStatus.OFFEN:
        raise PlanFehler(_("Diese Portion kann man nicht üben."))
    fragen = plan_selectors.portion_fragen(portion)
    if not fragen:
        raise PlanFehler(_("Zu dieser Portion gibt es gerade keine Fragen."))
    offen = selectors.offene_sitzung(kind)
    if offen is not None and offen.portion_id == portion.pk:
        return offen
    vorhaben = Vorhaben.NEU if portion.art == PortionArt.NEU else Vorhaben.WIEDERHOLEN
    return services.sitzung_starten(
        kind,
        portion.pruefung.fach,
        vorhaben=vorhaben,
        portion=portion,
        ziel_fragen=min(len(fragen) * _richtungen(fragen), 50),
        jetzt=jetzt,
    )


def _richtungen(frage_ids):
    """Vokabeln gibt es in zwei Richtungen; so viele Paare kann eine Portion höchstens haben."""
    return 2 if Frage.objects.filter(pk__in=frage_ids, typ="vokabel").exists() else 1


def fortschritt_pruefen(sitzung, jetzt=None):
    """Nach einer Antwort oder dem Ende einer Sitzung: Ist die Portion jetzt wirklich geübt?
    Erledigt wird nur durch Üben (Antworten oder Zeit), nie durch einen Klick."""
    portion = sitzung.portion
    if portion is None or portion.status != PortionStatus.OFFEN:
        return False
    jetzt = jetzt or zeit.jetzt()
    antworten, sekunden = plan_selectors.portion_zaehler(portion)
    verfuegbar = max(1, len(plan_selectors.portion_fragen(portion)))
    noetig = min(wert("lernen.pruefung_min_antworten"), verfuegbar)
    if antworten >= noetig or (antworten >= 1 and sekunden >= wert("lernen.pruefung_min_sekunden")):
        portion_erledigen(portion, zeit.heute(jetzt), jetzt)
        return True
    return False


@transaction.atomic
def portion_erledigen(portion, heute, jetzt=None):
    portion.status = PortionStatus.ERLEDIGT
    portion.erledigt_am = heute
    portion.save(update_fields=["status", "erledigt_am"])
    p = portion.pruefung
    _wochen_belohnen(p, heute)
    _vorbereitet_pruefen(p, heute)


# --- Punkte und Ereignis -------------------------------------------------------------------------


def _betrag_buchen(kind, soll, schluessel, referenz, heute):
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
        quelle_modul=services.QUELLE,
        bezugsdatum=heute,
        referenz=referenz,
        von=kind,
    )
    tag.punkte += betrag
    tag.save(update_fields=["punkte"])
    return betrag


def _wochen_belohnen(p, heute):
    """Eine Planwoche ist eingehalten, wenn alle ihre Portionen erledigt sind. Fester Bonus je
    Woche, einmal (Schlüssel). Verschobene Portionen zählen nicht gegen die Woche."""
    if p.status not in plan_selectors.AKTIVE:
        return 0
    gesamt = 0
    for montag, portionen in plan_selectors.wochen(p).items():
        if all(x.status == PortionStatus.ERLEDIGT for x in portionen):
            gesamt += _betrag_buchen(
                p.kind,
                wert("lernen.pruefung_punkte_woche"),
                f"lernen:pruefung_woche:{p.pk}:{montag.isoformat()}",
                p,
                heute,
            )
    return gesamt


def _vorbereitet_pruefen(p, heute):
    """Sind alle Pflicht-Portionen erledigt, ist die Prüfung vorbereitet: Bonus und Ereignis, je
    einmal. Der Bonus kommt nach, falls das Tageslimit gerade ausgeschöpft war."""
    if p.status not in plan_selectors.AKTIVE or not p.plan_ok:
        return False
    pflicht = [
        x
        for x in plan_selectors.plan_portionen(p)
        if x.art == PortionArt.NEU or (x.art == PortionArt.WIEDERHOLUNG and x.pflicht)
    ]
    if not pflicht or any(x.status != PortionStatus.ERLEDIGT for x in pflicht):
        return False
    schluessel = f"lernen:pruefung_vorbereitet:{p.pk}"
    betrag = _betrag_buchen(
        p.kind, wert("lernen.pruefung_punkte_vorbereitet"), schluessel, p, heute
    )
    if p.vorbereitet_am is not None:
        return False
    p.vorbereitet_am = heute
    p.save(update_fields=["vorbereitet_am"])
    stufe = _stufe(p.kind, p.fach)
    ereignisse.veroeffentlichen(
        events.PRUEFUNG_VORBEREITET,
        kind=p.kind,
        daten={
            "pruefung_id": p.pk,
            "termin": p.termin.isoformat(),
            "punkte": betrag,
            "hinweis_msgid": plan_texte.msgid("vorbereitet", stufe),
            "hinweis_parameter": {"titel": p.titel},
        },
        schluessel=f"{events.PRUEFUNG_VORBEREITET}:{p.pk}",
    )
    return True


# --- Probe-Prüfung -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ThemaErgebnis:
    thema: object
    richtig: int
    gesamt: int
    einstufung: str  # "staerke" | "mitte" | "ueben"


@transaction.atomic
def probe_starten(pruefung_, *, jetzt=None, zufall=None):
    """Startet die Probe-Prüfung aus freigegebenen Fragen des Stoffs, gemischt, ohne Zeitdruck. Eine
    offene Probe wird fortgesetzt."""
    if pruefung_.status not in plan_selectors.AKTIVE:
        raise PlanFehler(_("Diese Prüfung ist beendet."))
    offen = plan_selectors.offene_probe(pruefung_)
    if offen is not None:
        return offen
    ids = [i for fragen in plan_selectors.stoffe_fragen(pruefung_).values() for i in fragen]
    if not ids:
        raise PlanFehler(_("Für eine Probe-Prüfung gibt es noch keine Fragen."))
    (zufall or random.Random()).shuffle(ids)
    return ProbePruefung.objects.create(
        pruefung=pruefung_,
        fragen=ids[: wert("lernen.pruefung_probe_fragen")],
        beginn=jetzt or zeit.jetzt(),
    )


def probe_aufgabe(probe_):
    """Die nächste Frage der Probe (``Aufgabe``) oder ``None``, wenn alle beantwortet sind."""
    from . import wiederholung

    beantwortet = set(probe_.versuche.values_list("frage_id", flat=True))
    for frage_id in probe_.fragen:
        if frage_id not in beantwortet:
            frage = Frage.objects.filter(pk=frage_id).first()
            if frage is not None:
                return wiederholung.aufgabe_fuer(frage, Richtung.DE_EN)
    return None


@transaction.atomic
def probe_antworten(probe_, eingabe, *, jetzt=None):
    """Nimmt die Antwort auf die nächste Frage. Es gibt keine Rückmeldung pro Frage und keine
    Zeitgrenze; am Ende steht ein Hinweis je Thema (``probe_ergebnis``)."""
    if probe_.ende is not None:
        raise PlanFehler(_("Die Probe-Prüfung ist schon fertig."))
    aufgabe = probe_aufgabe(probe_)
    if aufgabe is None:
        return probe_beenden(probe_, jetzt=jetzt)
    geprueft = aufgabe.pruefen(eingabe)
    ergebnis = (
        Ergebnis.RICHTIG
        if geprueft.richtig
        else Ergebnis.FAST
        if geprueft.fast
        else Ergebnis.NOCH_NICHT
    )
    ProbeVersuch.objects.create(
        probe=probe_,
        frage=aufgabe.frage,
        richtung=aufgabe.richtung,
        ergebnis=ergebnis,
        eingabe=str(eingabe)[:300],
    )
    if probe_aufgabe(probe_) is None:
        probe_beenden(probe_, jetzt=jetzt)
    return probe_


def probe_beenden(probe_, *, jetzt=None):
    if probe_.ende is None:
        probe_.ende = jetzt or zeit.jetzt()
        probe_.save(update_fields=["ende"])
    return probe_


def probe_ergebnis(probe_):
    """Stärken und Schwächen je Thema, ohne Note. Ein Tippfehler zählt als richtig."""
    zaehler = {}
    for v in probe_.versuche.select_related("frage__thema"):
        richtig, gesamt = zaehler.get(v.frage.thema, (0, 0))
        zaehler[v.frage.thema] = (richtig + (v.ergebnis != Ergebnis.NOCH_NICHT), gesamt + 1)
    stark = wert("lernen.pruefung_probe_staerke_prozent")
    schwach = wert("lernen.pruefung_probe_schwaeche_prozent")
    ergebnisse = []
    for thema, (richtig, gesamt) in sorted(zaehler.items(), key=lambda x: x[0].name):
        anteil = 100 * richtig / gesamt
        einstufung = "staerke" if anteil >= stark else "ueben" if anteil < schwach else "mitte"
        ergebnisse.append(ThemaErgebnis(thema, richtig, gesamt, einstufung))
    return ergebnisse


def schwaechen(probe_):
    """Die Fragen, die in Themen mit Übungsbedarf nicht gesessen haben (Vorschlag für den Plan)."""
    schwache = {e.thema.pk for e in probe_ergebnis(probe_) if e.einstufung == "ueben"}
    return [
        v.frage_id
        for v in probe_.versuche.select_related("frage")
        if v.frage.thema_id in schwache and v.ergebnis == Ergebnis.NOCH_NICHT
    ]


@transaction.atomic
def schwaechen_einplanen(probe_, heute=None):
    """Nimmt den Vorschlag an: Schwächen kommen als kleine Wiederholungen in die letzten Plantage
    mit freiem Platz (nie über das Tagesziel). Gibt die Zahl der neuen Portionen zurück."""
    heute = heute or zeit.heute()
    p = probe_.pruefung
    if probe_.schwaechen_eingeplant or p.status not in plan_selectors.AKTIVE:
        return 0
    probe_.schwaechen_eingeplant = True
    probe_.save(update_fields=["schwaechen_eingeplant"])
    fragen = schwaechen(probe_)
    if not fragen:
        return 0
    params = plan_selectors.parameter(p.kind, heute)
    stoff_von = {}
    for s in p.stoffe.all():
        for i in plan_selectors.stoff_fragen(s, p.kind):
            stoff_von.setdefault(i, s)
    belegt = {}
    tage = []
    for x in p.portionen.exclude(status=PortionStatus.VERSCHOBEN):
        belegt[x.datum] = belegt.get(x.datum, 0) + x.minuten
        if x.art == PortionArt.PUFFER:
            tage.append((x.datum, True))
        elif x.art != PortionArt.LEICHT:
            tage.append((x.datum, False))
    kandidaten = sorted(
        {d for d, puffer in tage if not puffer and d >= heute and d < p.termin}, reverse=True
    )
    je = plan.fragen_je_portion(params)
    neu = 0
    stuecke = [fragen[i : i + je] for i in range(0, len(fragen), je)]
    for stueck in stuecke:
        minuten = plan.minuten_wdh(plan.minuten_neu(len(stueck), params), params)
        for tag in kandidaten:
            if belegt.get(tag, 0) + minuten <= params.tagesziel:
                Pruefungsportion.objects.create(
                    pruefung=p,
                    stoff=stoff_von.get(stueck[0]),
                    datum=tag,
                    art=PortionArt.WIEDERHOLUNG,
                    minuten=minuten,
                    fragen=stueck,
                    pflicht=False,
                )
                belegt[tag] = belegt.get(tag, 0) + minuten
                neu += 1
                break
    return neu
