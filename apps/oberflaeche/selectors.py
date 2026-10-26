"""Lesende Daten für die Dashboards. oberflaeche besitzt keine Tabellen: alles kommt aus den
öffentlichen Schnittstellen (selectors/services) der darunterliegenden Apps, nie aus deren
Modellen (ARCHITECTURE 2.2; Vertrag in pyproject.toml)."""

from apps.aufgaben import selectors as aufgaben
from apps.belohnung import selectors as belohnung
from apps.ereignisse import selectors as ereignisse
from apps.kern import jobs, zeit
from apps.konten import selectors as konten
from apps.punkte import selectors as punkte

LAUFENDE_ANZEIGE = ("rueckfrage", "nachbessern", "reserviert", "konflikt", "gemeldet")
AUSZUG_OFFENE = 4
SICHERUNGS_JOBS = ("db_sichern", "backup_pruefen")


def kind_konto(kind):
    """Guthaben, XP und reservierter Anteil eines Kindes."""
    saldo = punkte.salden(kind)
    return {
        "guthaben": saldo.guthaben,
        "xp": saldo.xp,
        "reserviert": punkte.reserviert(kind),
    }


def kind_offene_auszug(kind, anzahl=AUSZUG_OFFENE):
    offene = aufgaben.kind_offene(kind)
    return {"aufgaben": offene[:anzahl], "gesamt": len(offene)}


def kind_laufende(kind):
    return [i for i in aufgaben.kind_eigene(kind) if i.anzeige_status in LAUFENDE_ANZEIGE]


def offene_anzahl(kind):
    return len(aufgaben.kind_offene(kind))


def eltern_entscheidungen():
    """Zähler offener Entscheidungen: Meldungen, Konflikte, Einlöseanträge."""
    daten = aufgaben.eltern_entscheidungen()
    zaehler = {
        "meldungen": len(daten["meldungen"]),
        "konflikte": len(daten["konflikte"]),
        "antraege": belohnung.offene_antraege().count(),
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
