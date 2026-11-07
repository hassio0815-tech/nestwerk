"""Lesende Daten für die Dashboards. oberflaeche besitzt keine Tabellen: alles kommt aus den
öffentlichen Schnittstellen (selectors/services) der darunterliegenden Apps, nie aus deren
Modellen (ARCHITECTURE 2.2; Vertrag in pyproject.toml)."""

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.aufgaben import selectors as aufgaben
from apps.belohnung import selectors as belohnung
from apps.ereignisse import selectors as ereignisse
from apps.kern import jobs, zeit
from apps.konten import selectors as konten
from apps.punkte import selectors as punkte

LAUFENDE_ANZEIGE = ("rueckfrage", "nachbessern", "reserviert", "konflikt", "gemeldet")
AUSZUG_OFFENE = 4
VERLAUF_ANZAHL = 5
SICHERUNGS_JOBS = ("db_sichern", "backup_pruefen")


def kind_konto(kind):
    """Guthaben, XP und reservierter Anteil eines Kindes."""
    saldo = punkte.salden(kind)
    return {
        "guthaben": saldo.guthaben,
        "xp": saldo.xp,
        "reserviert": punkte.reserviert(kind),
        "verlauf": list(punkte.buchungen(kind)[:VERLAUF_ANZAHL]),
    }


def kind_offene_auszug(kind, anzahl=AUSZUG_OFFENE):
    offene = aufgaben.kind_offene(kind)
    return {"aufgaben": offene[:anzahl], "gesamt": len(offene)}


SERIE_ZIEL_TAGE = 7


def kind_balken(kind):
    """Mini-Übersicht der Kinder-Startseite: Serie, Übungswoche, Sondertag, Familienziel.
    Jede Zeile ``{"schluessel", "label", "text", "wert", "max"}``; was ein Modul nicht liefert,
    fehlt in der Liste (die Startseite bleibt dann trotzdem benutzbar)."""
    from apps.familienziel import selectors as familienziel
    from apps.sondertag import selectors as sondertag
    from apps.spielregeln import selectors as spielregeln

    zeilen = []
    try:
        stand = spielregeln.stand(kind)
        tage = stand.tagesserie
        zeilen.append(
            {
                "schluessel": "serie",
                "label": _("Serie"),
                "text": ngettext("%(n)s Tag", "%(n)s Tage", tage) % {"n": tage},
                "wert": min(tage, SERIE_ZIEL_TAGE),
                "max": SERIE_ZIEL_TAGE,
            }
        )
        zeilen.append(
            {
                "schluessel": "uebungswoche",
                "label": _("Übungswoche"),
                "text": _("geschafft") if stand.woche_aktiv else _("noch offen"),
                "wert": int(bool(stand.woche_aktiv)),
                "max": 1,
            }
        )
    except Exception:  # ohne Spielregeln bleiben die übrigen Balken nutzbar
        pass
    try:
        f = sondertag.fortschritt(kind)
        zeilen.append(
            {
                "schluessel": "sondertag",
                "label": _("Sondertag"),
                "text": f"{f.mods_ist}/{f.mods_ziel}" if f.mods_ziel else "–",
                "wert": f.mods_ist if f.mods_ziel else 0,
                "max": f.mods_ziel or 1,
            }
        )
    except Exception:
        pass
    try:
        stand = familienziel.ansicht().stand
        zeilen.append(
            {
                "schluessel": "familienziel",
                "label": _("Familienziel"),
                "text": f"{stand.prozent} %",
                "wert": stand.prozent,
                "max": 100,
            }
        )
    except Exception:
        pass
    return zeilen


LERNEN_PROVIDER = "lernen.kind_faecher"


def kind_lernen(kind):
    """Fächer und letzte Aktivität für die Kinder-Startseite. Das Lern-Modul registriert dazu
    einen Provider ``lernen.kind_faecher(kind)`` (``kern.registry.Provider``), der eine Liste
    ``{"name", "zuletzt": datetime | None}`` liefert. Ohne Provider: leere Liste."""
    from apps.kern import registry

    if not registry.provider_vorhanden(LERNEN_PROVIDER):
        return []
    try:
        return list(registry.fortschritt(LERNEN_PROVIDER, kind))
    except Exception:
        return []


def kind_laufende(kind):
    return [i for i in aufgaben.kind_eigene(kind) if i.anzeige_status in LAUFENDE_ANZEIGE]


def offene_anzahl(kind):
    return len(aufgaben.kind_offene(kind))


START_INFOZEILE_MAX = 8


def start_infozeile(anzahl=START_INFOZEILE_MAX):
    """Offene/heute fällige Aufgaben für die Infozeile der Anmeldeseite."""
    offene = aufgaben.start_offene()
    return {"aufgaben": offene[:anzahl], "weitere": max(len(offene) - anzahl, 0)}


def start_woche():
    """Kalenderleiste der Anmeldeseite: 7 Tage mit ``anzahl`` fester Aufgaben; ``aufgaben`` je Tag
    sind für das Popup des Tages."""
    tage = aufgaben.start_woche()
    for tag in tage:
        tag["anzahl"] = len(tag["aufgaben"])
    return {"tage": tage, "mit_aufgaben": [t for t in tage if t["aufgaben"]]}


def uebernehmen_absicht(aufgabe_id, datum):
    """Die vorgemerkte Aufgabe (Banner der Anmeldeseite) oder ``None``, wenn sie nicht (mehr)
    zur Wochenvorschau gehört."""
    return aufgaben.start_woche_aufgabe(aufgabe_id, datum)


def eltern_entscheidungen():
    """Zähler offener Entscheidungen: Meldungen, Konflikte, Einlöseanträge, Mood-Vorschläge."""
    daten = aufgaben.eltern_entscheidungen()
    zaehler = {
        "meldungen": len(daten["meldungen"]),
        "konflikte": len(daten["konflikte"]),
        "antraege": belohnung.offene_antraege().count(),
        "moods": konten.mood_vorschlaege_offen_anzahl(),
    }
    zaehler["gesamt"] = sum(zaehler.values())
    return zaehler


def kinder_uebersicht(jetzt=None):
    """Je aktivem Kind: Guthaben, XP, laufende und heute erledigte Aufgaben (3 Abfragen
    für die Aufgaben, unabhängig von der Kinderzahl)."""
    jetzt = jetzt or zeit.jetzt()
    von, bis = zeit.tag_intervall(zeit.heute(jetzt))
    kinder = list(konten.aktive_kinder())
    zahlen = aufgaben.zahlen_je_kind(kinder, von, bis)
    zeilen = []
    for kind in kinder:
        z = zahlen.get(kind.pk, {})
        zeilen.append(
            {
                "kind": kind,
                **kind_konto(kind),
                "laufend": z.get("laufend", 0),
                "heute": z.get("heute", 0),
            }
        )
    return zeilen


def system_status():
    """Worker/Ereignis-Kennzahlen plus letzter Lauf der Sicherungs-Jobs."""
    status = ereignisse.systemstatus()
    laeufe = {}
    for name in SICHERUNGS_JOBS:
        laeufe[name] = jobs.letzter_lauf(name)
    status["jobs"] = laeufe
    return status
