"""Ereignistypen von aufgaben (ARCHITECTURE 5.2) und deutsche Texte für Benachrichtigungen.

Für die Typen aus dem Ereigniskatalog liefert ``benachrichtigung.texte`` Standardtexte; hier
werden nur die Texte der zusätzlichen Typen registriert.
"""

from django.utils.translation import gettext_noop

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
    ZUGETEILT: (
        gettext_noop("Die Aufgabe gehört dir!"),
        gettext_noop("„{aufgabe}“ ist für dich reserviert."),
    ),
    VERGEBEN: (
        gettext_noop("Aufgabe vergeben"),
        gettext_noop("„{aufgabe}“ macht diesmal jemand anderes."),
    ),
    GELOEST: (
        gettext_noop("Reservierung aufgehoben"),
        gettext_noop("„{aufgabe}“ ist wieder frei."),
    ),
    ZURUECKGEGEBEN: (
        gettext_noop("{kind} hat eine Aufgabe zurückgegeben"),
        gettext_noop("„{aufgabe}“ ist wieder frei."),
    ),
    ANTWORT: (
        gettext_noop("{kind} hat geantwortet"),
        gettext_noop("„{aufgabe}“ wartet auf Bestätigung."),
    ),
    VERTRAUEN: (
        gettext_noop("{kind} hat eine Aufgabe erledigt"),
        gettext_noop("„{aufgabe}“: {punkte} Punkte gutgeschrieben (Vertrauen)."),
    ),
    SONDERPUNKTE: (
        gettext_noop("Sonderpunkte!"),
        gettext_noop("+{punkte} für „{aufgabe}“: {begruendung}"),
    ),
    KORRIGIERT: (
        gettext_noop("Punkte korrigiert"),
        gettext_noop("„{aufgabe}“: {punkte} Punkte abgezogen. {begruendung}"),
    ),
    NACHBESSERN: (gettext_noop("Bitte nachbessern"), gettext_noop("„{aufgabe}“: {begruendung}")),
    NACHBESSERN_ABGELAUFEN: (
        gettext_noop("Nachbessern nicht erledigt"),
        gettext_noop("{kind} hat „{aufgabe}“ nicht rechtzeitig nachgebessert. Keine Punkte."),
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

    typ(VERFALL_VORWARNUNG, gettext_noop("Aufgabe läuft bald ab (noch nicht übernommen)"), "eltern")
    # nur Dashboard-Liste (stiller Verfall, SPEC 5.6)
    typ(NICHT_UEBERNOMMEN, gettext_noop("Aufgabe nicht übernommen"), "eltern", kanaele=())
    typ(
        RESERVIERUNG_ERINNERUNG,
        gettext_noop("Erinnerung: Reservierung läuft bald ab"),
        "kind",
        kanaele=("push",),
        push_ttl_sekunden=6 * 3600,
        deep_link_muster=LINK_KIND,
    )
    typ(RESERVIERUNG_ABGELAUFEN, gettext_noop("Reservierung abgelaufen"), "eltern")

    eltern = {"deep_link_muster": LINK_ELTERN}
    kind = {"deep_link_muster": LINK_KIND}
    typ(INTERESSE, gettext_noop("Kind wählt eine Aufgabe"), "eltern", **eltern)
    typ(
        KONFLIKT,
        gettext_noop("Mehrere Kinder wollen dieselbe Aufgabe"),
        "eltern",
        entscheidung=True,
        **eltern,
    )
    typ(ZUGETEILT, gettext_noop("Aufgabe zugeteilt"), "kind", kanaele=("push",), **kind)
    typ(
        VERGEBEN,
        gettext_noop("Aufgabe an ein anderes Kind vergeben"),
        "kind",
        kanaele=("push",),
        **kind,
    )
    typ(
        GELOEST,
        gettext_noop("Reservierung von Eltern aufgehoben"),
        "kind",
        kanaele=("push",),
        **kind,
    )
    typ(ZURUECKGEGEBEN, gettext_noop("Kind gibt eine Aufgabe zurück"), "eltern", **eltern)
    typ(
        GEMELDET,
        gettext_noop("Aufgabe als erledigt gemeldet"),
        "eltern",
        entscheidung=True,
        **eltern,
    )
    typ(ANTWORT, gettext_noop("Antwort auf Rückfrage"), "eltern", entscheidung=True, **eltern)
    typ(VERTRAUEN, gettext_noop("Aufgabe mit Vertrauen gutgeschrieben"), "eltern", **eltern)
    typ(BESTAETIGT, gettext_noop("Aufgabe bestätigt"), "kind", kanaele=("push",), **kind)
    typ(ABGELEHNT, gettext_noop("Aufgabe abgelehnt"), "kind", kanaele=("push",), **kind)
    typ(RUECKFRAGE, gettext_noop("Rückfrage zur Aufgabe"), "kind", kanaele=("push",), **kind)
    typ(SONDERPUNKTE, gettext_noop("Sonderpunkte erhalten"), "kind", kanaele=("push",), **kind)
    typ(
        KORRIGIERT,
        gettext_noop("Punkte einer Aufgabe korrigiert"),
        "kind",
        kanaele=("push",),
        **kind,
    )
    typ(
        NACHBESSERN,
        gettext_noop("Aufgabe zum Nachbessern zurück"),
        "kind",
        kanaele=("push",),
        **kind,
    )
    typ(
        NACHBESSERN_ABGELAUFEN,
        gettext_noop("Nachbessern nicht rechtzeitig erledigt"),
        "eltern",
        **eltern,
    )
    typ(ERLEDIGT, gettext_noop("Aufgabe erledigt (Aktivität)"), "intern", kanaele=())


def texte_registrieren():
    from apps.benachrichtigung import texte

    for slug, (titel, text) in TEXTE.items():
        texte.text_registrieren(slug, titel=titel, text=text)
