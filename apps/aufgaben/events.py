"""Ereignistypen von aufgaben (ARCHITECTURE 5.2) und deutsche Texte für Benachrichtigungen.

Für die Typen aus dem Ereigniskatalog liefert ``benachrichtigung.texte`` Standardtexte; hier
werden nur die Texte der zusätzlichen Typen registriert.
"""

from apps.ereignisse import registry

VERFALL_VORWARNUNG = "aufgabe.verfall_vorwarnung"
NICHT_UEBERNOMMEN = "aufgabe.nicht_uebernommen"
RESERVIERUNG_ERINNERUNG = "reservierung.erinnerung"
RESERVIERUNG_ABGELAUFEN = "reservierung.abgelaufen"

# Kinderablauf (AP12)
INTERESSE = "aufgabe.interesse"  # Kind wählt (reserviert)
KONFLIKT = "aufgabe.konflikt"  # mehrere Interessenten -> Eltern teilen zu
ZUGETEILT = "aufgabe.zugeteilt"  # Kind bekommt die Aufgabe (Eltern-Zuteilung)
VERGEBEN = "aufgabe.vergeben"  # Konflikt: an ein anderes Kind vergeben
GELOEST = "aufgabe.reservierung_geloest"  # Eltern lösen die Reservierung
ZURUECKGEGEBEN = "aufgabe.zurueckgegeben"  # Kind gibt zurück
GEMELDET = "aufgabe.gemeldet"  # Kind meldet erledigt (Eltern entscheiden)
ANTWORT = "aufgabe.antwort"  # Kind beantwortet Rückfrage
VERTRAUEN = "aufgabe.vertrauen_gutgeschrieben"  # Vertrauen: sofort gebucht (Eltern info)
BESTAETIGT = "aufgabe.bestaetigt"
ABGELEHNT = "aufgabe.abgelehnt"
RUECKFRAGE = "aufgabe.rueckfrage"
SONDERPUNKTE = "aufgabe.sonderpunkte"
KORRIGIERT = "aufgabe.korrigiert"
NACHBESSERN_ABGELAUFEN = "aufgabe.nachbessern_abgelaufen"  # Frist vorbei, keine Punkte
NACHBESSERN = "aufgabe.nachbessern"  # Eltern geben eine Vertrauens-Aufgabe zurück (Punkte zurück)
# Fakt für Phase 2 (spielregeln: Aktivität, K1). Daten: kind, instanz_id, bezugsdatum
# (= Meldedatum, lokal), gemeldet_am, bestaetigt_am, punkte. Storno: ``aufgabe.korrigiert``.
ERLEDIGT = "aufgabe.erledigt"

LINK_KIND = "/kind/aufgaben/"
LINK_ELTERN = "/eltern/meldungen/#instanz-{instanz_id}"

TEXTE = {
    ZUGETEILT: ("Die Aufgabe gehört dir!", "„{aufgabe}“ ist für dich reserviert."),
    VERGEBEN: ("Aufgabe vergeben", "„{aufgabe}“ macht diesmal jemand anderes."),
    GELOEST: ("Reservierung aufgehoben", "„{aufgabe}“ ist wieder frei."),
    ZURUECKGEGEBEN: ("{kind} hat eine Aufgabe zurückgegeben", "„{aufgabe}“ ist wieder frei."),
    ANTWORT: ("{kind} hat geantwortet", "„{aufgabe}“ wartet auf Bestätigung."),
    VERTRAUEN: (
        "{kind} hat eine Aufgabe erledigt",
        "„{aufgabe}“: {punkte} Punkte gutgeschrieben (Vertrauen).",
    ),
    SONDERPUNKTE: ("Sonderpunkte!", "+{punkte} für „{aufgabe}“: {begruendung}"),
    KORRIGIERT: ("Punkte korrigiert", "„{aufgabe}“: {punkte} Punkte abgezogen. {begruendung}"),
    NACHBESSERN: ("Bitte nachbessern", "„{aufgabe}“: {begruendung}"),
    NACHBESSERN_ABGELAUFEN: (
        "Nachbessern nicht erledigt",
        "{kind} hat „{aufgabe}“ nicht rechtzeitig nachgebessert. Keine Punkte.",
    ),
}


def typen_deklarieren():
    def typ(slug, bezeichnung, zielgruppe, kanaele=("push", "email"), **extra):
        registry.typ_deklarieren(
            slug,
            modul="aufgaben",
            bezeichnung=bezeichnung,
            zielgruppe=zielgruppe,
            standard_kanaele=list(kanaele),
            **extra,
        )

    typ(VERFALL_VORWARNUNG, "Aufgabe läuft bald ab (noch nicht übernommen)", "eltern")
    # nur Dashboard-Liste (stiller Verfall, SPEC 5.6)
    typ(NICHT_UEBERNOMMEN, "Aufgabe nicht übernommen", "eltern", kanaele=())
    typ(
        RESERVIERUNG_ERINNERUNG,
        "Erinnerung: Reservierung läuft bald ab",
        "kind",
        kanaele=("push",),
        push_ttl_sekunden=6 * 3600,
        deep_link_muster=LINK_KIND,
    )
    typ(RESERVIERUNG_ABGELAUFEN, "Reservierung abgelaufen", "eltern")

    eltern = {"deep_link_muster": LINK_ELTERN}
    kind = {"deep_link_muster": LINK_KIND}
    typ(INTERESSE, "Kind wählt eine Aufgabe", "eltern", **eltern)
    typ(KONFLIKT, "Mehrere Kinder wollen dieselbe Aufgabe", "eltern", entscheidung=True, **eltern)
    typ(ZUGETEILT, "Aufgabe zugeteilt", "kind", kanaele=("push",), **kind)
    typ(VERGEBEN, "Aufgabe an ein anderes Kind vergeben", "kind", kanaele=("push",), **kind)
    typ(GELOEST, "Reservierung von Eltern aufgehoben", "kind", kanaele=("push",), **kind)
    typ(ZURUECKGEGEBEN, "Kind gibt eine Aufgabe zurück", "eltern", **eltern)
    typ(GEMELDET, "Aufgabe als erledigt gemeldet", "eltern", entscheidung=True, **eltern)
    typ(ANTWORT, "Antwort auf Rückfrage", "eltern", entscheidung=True, **eltern)
    typ(VERTRAUEN, "Aufgabe mit Vertrauen gutgeschrieben", "eltern", **eltern)
    typ(BESTAETIGT, "Aufgabe bestätigt", "kind", kanaele=("push",), **kind)
    typ(ABGELEHNT, "Aufgabe abgelehnt", "kind", kanaele=("push",), **kind)
    typ(RUECKFRAGE, "Rückfrage zur Aufgabe", "kind", kanaele=("push",), **kind)
    typ(SONDERPUNKTE, "Sonderpunkte erhalten", "kind", kanaele=("push",), **kind)
    typ(KORRIGIERT, "Punkte einer Aufgabe korrigiert", "kind", kanaele=("push",), **kind)
    typ(NACHBESSERN, "Aufgabe zum Nachbessern zurück", "kind", kanaele=("push",), **kind)
    typ(NACHBESSERN_ABGELAUFEN, "Nachbessern nicht rechtzeitig erledigt", "eltern", **eltern)
    typ(ERLEDIGT, "Aufgabe erledigt (Aktivität)", "intern", kanaele=())


def texte_registrieren():
    from apps.benachrichtigung import texte

    for slug, (titel, text) in TEXTE.items():
        texte.text_registrieren(slug, titel=titel, text=text)
