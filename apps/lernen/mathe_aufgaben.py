"""Mathe-Aufgaben im Üben (SPEC 21.13, Etappe 10a): wählen, anlegen, wiederholen, aufräumen.

Die Aufgabe wird beim Abrufen als ``Frage``-Zeile angelegt (``generiert=True``, ``quelle=system``,
ohne Kind), mit Seed, Typ, Parametern und der berechneten Lösung in ``gen_daten``. So laufen
Versuch, Lernstand, Wiederholung und Prüfungsplan unverändert. Die Zeile enthält nichts
Persönliches; was dem Kind gehört (Versuche, Lernstand), hängt am Kind.

Wiederholung: Ist ein Lernstand fällig, bekommt das Kind eine gleichartige NEUE Aufgabe (gleicher
Generator, gleiche Stufe, möglichst gleicher Typ, andere Zahlen); der Lernstand wandert auf die neue
Zeile und behält seine Box. Die Auswahl der Schwierigkeit steht rein in ``mathe.schwierigkeit``.
"""

import hashlib
from collections import defaultdict
from datetime import timedelta

from apps.kern import zeit
from apps.kern.einstellungen import wert

from . import mathe_ki, selectors
from .mathe import registry, schwierigkeit, textaufgaben
from .models import (
    Ergebnis,
    Frage,
    FrageTyp,
    Freigabe,
    Intensitaet,
    Lernstand,
    ProbePruefung,
    Pruefungsportion,
    PruefungStatus,
    Quelle,
    Thema,
    Versuch,
    Vorhaben,
)

VERLAUF_MAX = 400  # so viele letzte Antworten werden für die Anpassung gelesen
GLEICHER_TYP_VERSUCHE = 25
ZIEHEN_VERSUCHE = 30
GEMISCHT_VORJAHR = 0.15  # Gewicht von Rechenarten früherer Stufen in "alles gemischt"
SCHWAECHE_FAKTOR = 2.5  # Gewicht einer Rechenart, bei der das Kind unter dem Zielbereich liegt
GLEICHES_THEMA_FAKTOR = 0.2  # Themenmischung statt Blöcken
GLEICHER_GENERATOR_FAKTOR = 0.05


# --- Anlegen --------------------------------------------------------------------------------------


def als_textaufgabe(aufgabe):
    """Kommt diese Aufgabe als Textaufgabe? Der Seed entscheidet gleichmäßig nach dem Anteil in
    ``lernen.mathe_textaufgaben_prozent`` (Standard 0); nur Rechenarten mit Vorlage zählen."""
    anteil = wert("lernen.mathe_textaufgaben_prozent")
    return bool(anteil) and aufgabe.seed % 100 < anteil and textaufgaben.hat_vorlage(aufgabe)


def speichern(aufgabe, thema):
    """Legt die Aufgabe als Frage-Zeile an (siehe Modulbeschreibung).

    Kommt die Aufgabe als Textaufgabe (Einstellung ``lernen.mathe_textaufgaben_prozent``), steht
    die lokale Vorlage als Text da; mit Opt-in der Eltern wird zusätzlich die KI-Einkleidung in
    die Warteschlange gestellt (``mathe_ki``). Zahlen und Lösung bleiben die des Generators."""
    text, daten = aufgabe.text, aufgabe.to_dict()
    textfassung = als_textaufgabe(aufgabe)
    if textfassung:
        lokal = textaufgaben.lokal(aufgabe)
        if lokal:
            text = lokal
            daten["einkleidung"] = {"quelle": "lokal"}
    frage = Frage.objects.create(
        thema=thema,
        typ=FrageTyp.FRAGE,
        frage=text[:300],
        antwort=aufgabe.loesung.anzeige[:300],
        quelle=Quelle.SYSTEM,
        freigabe=Freigabe.FREIGEGEBEN,
        generiert=True,
        generator=aufgabe.generator,
        gen_schwierigkeit=aufgabe.schwierigkeit,
        gen_daten=daten,
    )
    if textfassung:
        mathe_ki.einreihen(frage, aufgabe)
    return frage


def _thema(fach, schluessel, cache):
    if schluessel not in cache:
        cache[schluessel] = Thema.objects.filter(fach=fach, schluessel=schluessel).first()
    return cache[schluessel]


def nutzt_generator(sitzung):
    """Übt diese Sitzung mit erzeugten Aufgaben? Nicht in Prüfungsportionen (feste Aufgaben)
    und nicht bei Themen ohne Generator (dort stehen Fragen von Eltern oder aus Material)."""
    if sitzung.portion_id:
        return False
    if sitzung.thema_id:
        return selectors.ist_generatorthema(sitzung.thema)
    return any(
        selectors.ist_generatorthema(t) for t in selectors.themen_fuer(sitzung.kind, sitzung.fach)
    )


def aufgaben_je_runde(fach):
    """Einstellung "Aufgaben je Runde" für Fächer mit Generator; 0 oder kein Generator: ``None``."""
    n = wert("lernen.mathe_aufgaben_je_runde")
    if n and Thema.objects.filter(fach=fach).exclude(schluessel="").exists():
        return n
    return None


# --- Auswählen ------------------------------------------------------------------------------------


def _verlauf(kind, fach):
    """``{generator: [(schwierigkeit, richtig), ...]}``, älteste zuerst (richtig und noch nicht)."""
    zeilen = list(
        Versuch.objects.filter(
            sitzung__kind=kind,
            frage__generiert=True,
            frage__thema__fach=fach,
            ergebnis__in=[Ergebnis.RICHTIG, Ergebnis.NOCH_NICHT],
        )
        .order_by("-id")
        .values_list("frage__generator", "frage__gen_schwierigkeit", "ergebnis")[:VERLAUF_MAX]
    )
    verlauf = defaultdict(list)
    for gen, stufe, ergebnis in reversed(zeilen):
        verlauf[gen].append((stufe or 1, ergebnis == Ergebnis.RICHTIG))
    return verlauf


def _parameter():
    return {
        "ziel_von": wert("lernen.mathe_ziel_von_prozent"),
        "ziel_bis": wert("lernen.mathe_ziel_bis_prozent"),
        "fenster": wert("lernen.mathe_fenster"),
    }


def stufe_fuer(kind, fach, sitzung, generator_key, verlauf):
    """Schwierigkeit der nächsten Aufgabe dieser Rechenart (Niveau, Intensität, Verlauf, Frust)."""
    return schwierigkeit.schwierigkeit(
        selectors.niveau(kind, fach),
        sitzung.intensitaet,
        verlauf.get(generator_key, []),
        frust=sitzung.frust_erkannt,
        **_parameter(),
    )


def _schwach(verlauf_g, params):
    """Liegt das Kind bei dieser Rechenart unter dem Zielbereich?"""
    letzte = verlauf_g[-params["fenster"] :]
    if len(letzte) < 4:
        return False
    return schwierigkeit.quote(letzte) * 100 < params["ziel_von"]


def _ziehen(generator_key, stufe, zufall, kontext, gesehen, typ=None):
    """Erzeugt eine Aufgabe, die in dieser Sitzung noch nicht dran war (und möglichst vom
    gewünschten Typ)."""
    aufgabe = None
    for i in range(ZIEHEN_VERSUCHE):
        aufgabe = registry.erzeugen(generator_key, stufe, zufall.getrandbits(48), kontext)
        if aufgabe.text in gesehen:
            continue
        if typ and aufgabe.typ != typ and i < GLEICHER_TYP_VERSUCHE:
            continue
        return aufgabe
    return aufgabe


def _gewichte(gens, *, band, gemischt, verlauf, letzter_gen, letztes_thema, params):
    gewichte = []
    for g in gens:
        w = 1.0
        if gemischt and g.klassenstufe < band:
            w *= GEMISCHT_VORJAHR
        if _schwach(verlauf.get(g.schluessel, []), params):
            w *= SCHWAECHE_FAKTOR
        if g.thema == letztes_thema:
            w *= GLEICHES_THEMA_FAKTOR
        if g.schluessel == letzter_gen:
            w *= GLEICHER_GENERATOR_FAKTOR
        gewichte.append(w)
    return gewichte


def _faellige(kind, fach, aktiv, heute, ausgeschlossen):
    staende = list(
        Lernstand.objects.filter(
            kind=kind,
            frage__generiert=True,
            frage__thema__fach=fach,
            frage__generator__in=aktiv,
            faellig_am__lte=heute,
        )
        .exclude(frage_id__in=ausgeschlossen)
        .select_related("frage__thema")
    )
    stolper = [s for s in staende if s.box == 0 and s.versuche > s.richtige]
    return staende, stolper


def naechste(sitzung, *, zufall, jetzt):
    """Die nächste Aufgabe als ``Frage``-Zeile, oder ``None`` (keine Rechenart in Reichweite).

    Reihenfolge der Töpfe wie bei den Vokabeln (Vorhaben): fällige Wiederholungen (als gleichartige
    neue Aufgabe), Stolperstellen, Neues. Neues mischt die Themen: dasselbe Thema und dieselbe
    Rechenart direkt hintereinander werden selten, Rechenarten mit Schwäche öfter.
    """
    kind, fach = sitzung.kind, sitzung.fach
    heute = zeit.heute(jetzt)
    aktiv = selectors.mathe_rechenarten()
    kontext = selectors.mathe_kontext()
    verlauf = _verlauf(kind, fach)
    params = _parameter()
    ausgeschlossen = set(sitzung.antworten.values_list("frage_id", flat=True))
    gesehen = set(sitzung.antworten.values_list("frage__frage", flat=True))
    letzter = sitzung.antworten.order_by("-id").select_related("frage").first()
    letzter_gen = letzter.frage.generator if letzter and letzter.frage.generiert else ""
    letztes_thema = registry.holen(letzter_gen).thema if letzter_gen in aktiv else ""
    cache = {}

    faellig, stolper = _faellige(kind, fach, aktiv, heute, ausgeschlossen)
    topf_neu = "neu"
    reihenfolge = {
        Vorhaben.NEU: (topf_neu, faellig),
        Vorhaben.WIEDERHOLEN: (faellig, topf_neu),
        Vorhaben.STOLPERSTELLEN: (stolper, faellig, topf_neu),
    }.get(sitzung.vorhaben, (faellig, topf_neu))
    for topf in reihenfolge:
        if topf is topf_neu:
            frage = _neue_aufgabe(
                sitzung,
                aktiv,
                kontext,
                verlauf,
                params,
                gesehen,
                letzter_gen,
                letztes_thema,
                zufall,
                cache,
            )
            if frage is not None:
                return frage
            continue
        if not topf:
            continue
        zufall.shuffle(topf)
        topf.sort(
            key=lambda s: (
                registry.holen(s.frage.generator).thema == letztes_thema,
                s.frage.generator == letzter_gen,
            )
        )
        return _wiederholen(topf[0], sitzung, kontext, gesehen, zufall)
    return None


def _wiederholen(stand, sitzung, kontext, gesehen, zufall):
    """Gleichartige neue Aufgabe zu einem fälligen Lernstand; der Stand wandert mit."""
    alt = stand.frage
    niedrig, hoch = schwierigkeit.bereich(
        selectors.niveau(sitzung.kind, sitzung.fach), sitzung.intensitaet
    )
    stufe = max(niedrig, min(hoch, alt.gen_schwierigkeit or niedrig))
    aufgabe = _ziehen(
        alt.generator, stufe, zufall, kontext, gesehen | {alt.frage}, typ=alt.gen_daten.get("typ")
    )
    neu = speichern(aufgabe, alt.thema)
    stand.frage = neu
    stand.save(update_fields=["frage"])
    return neu


def _neue_aufgabe(
    sitzung, aktiv, kontext, verlauf, params, gesehen, letzter_gen, letztes_thema, zufall, cache
):
    kind, fach = sitzung.kind, sitzung.fach
    if sitzung.thema_id:
        gens = [
            g
            for g in registry.generatoren_fuer(thema=sitzung.thema.schluessel)
            if g.schluessel in aktiv
        ]
        gemischt = False
    else:
        schluessel = {t.schluessel for t in selectors.themen_fuer(kind, fach) if t.schluessel}
        gens = [
            g for g in registry.alle().values() if g.thema in schluessel and g.schluessel in aktiv
        ]
        gemischt = True
    if not gens:
        return None
    band = registry.band(selectors.klassenstufe(kind, fach))
    gewichte = _gewichte(
        gens,
        band=band,
        gemischt=gemischt,
        verlauf=verlauf,
        letzter_gen=letzter_gen,
        letztes_thema=letztes_thema,
        params=params,
    )
    gen = zufall.choices(gens, weights=gewichte)[0]
    stufe = stufe_fuer(kind, fach, sitzung, gen.schluessel, verlauf)
    aufgabe = _ziehen(gen.schluessel, stufe, zufall, kontext, gesehen)
    thema = _thema(fach, gen.thema, cache)
    if thema is None:  # Startdaten fehlen: Thema nachlegen wäre Sache der Migration
        return None
    return speichern(aufgabe, thema)


# --- Prüfungsplan: feste Aufgaben je Thema -------------------------------------------------------


def _pool_seed(kind_id, thema_id, index):
    roh = hashlib.sha256(f"mathe-pool:{kind_id}:{thema_id}:{index}".encode()).hexdigest()
    return int(roh[:12], 16)


def pruefungspool(thema, kind):
    """IDs fester, erzeugter Aufgaben zu einem Mathe-Thema für den Prüfungsplan (Portionen und
    Probe-Prüfung ziehen daraus). Legt fehlende Zeilen an; derselbe Aufruf liefert dieselben
    Aufgaben (Seeds aus Kind und Thema), solange Rechenarten und Einstellungen gleich bleiben."""
    aktiv = selectors.mathe_rechenarten()
    gens = sorted(
        (g for g in registry.generatoren_fuer(thema=thema.schluessel) if g.schluessel in aktiv),
        key=lambda g: g.schluessel,
    )
    if not gens:
        return []
    kontext = selectors.mathe_kontext()
    stufe = schwierigkeit.start_stufe(selectors.niveau(kind, thema.fach), Intensitaet.NORMAL)
    plan = [
        (gens[i % len(gens)], _pool_seed(kind.pk, thema.pk, i))
        for i in range(wert("lernen.mathe_pruefung_aufgaben"))
    ]
    vorhanden = {
        (f.generator, f.gen_daten.get("seed")): f
        for f in Frage.objects.filter(
            thema=thema, generiert=True, gen_daten__seed__in=[s for _g, s in plan]
        )
    }
    ids = []
    for gen, seed in plan:
        frage = vorhanden.get((gen.schluessel, seed))
        if frage is None:
            frage = speichern(registry.erzeugen(gen.schluessel, stufe, seed, kontext), thema)
        ids.append(frage.pk)
    return ids


# --- Aufräumen ------------------------------------------------------------------------------------


def _geschuetzt():
    """Frage-IDs, die ein laufender Prüfungsplan oder eine offene Probe noch braucht."""
    aktiv = [PruefungStatus.GEPLANT, PruefungStatus.AKTIV]
    ids = set()
    for liste in Pruefungsportion.objects.filter(pruefung__status__in=aktiv).values_list(
        "fragen", flat=True
    ):
        ids.update(liste)
    for liste in ProbePruefung.objects.filter(pruefung__status__in=aktiv).values_list(
        "fragen", flat=True
    ):
        ids.update(liste)
    return ids


def aufraeumen(jetzt):
    """Alte erzeugte Aufgaben löschen (Einstellung ``lernen.mathe_aufbewahren_tage``).

    - Lernstände erzeugter Aufgaben, die seit dem Dreifachen der Frist nicht mehr dran waren,
    - erzeugte Zeilen ohne Lernstand, die älter als die Frist sind, mit ihren Versuchen.
    Aufgaben eines geplanten oder laufenden Prüfungsplans bleiben. Gibt die Zahl gelöschter
    Aufgaben zurück.
    """
    if not Frage.objects.filter(generiert=True).exists():
        return 0
    tage = wert("lernen.mathe_aufbewahren_tage")
    Lernstand.objects.filter(
        frage__generiert=True, faellig_am__lt=zeit.heute(jetzt) - timedelta(days=3 * tage)
    ).delete()
    alt = Frage.objects.filter(
        generiert=True, erstellt__lt=jetzt - timedelta(days=tage), staende__isnull=True
    ).exclude(pk__in=_geschuetzt())
    anzahl = alt.count()
    alt.delete()
    return anzahl
