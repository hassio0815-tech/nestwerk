"""Ereignistypen von aufgaben (ARCHITECTURE 5.2). Weitere Typen (Interesse, Meldung ...) in AP12."""

from apps.ereignisse import registry

VERFALL_VORWARNUNG = "aufgabe.verfall_vorwarnung"
NICHT_UEBERNOMMEN = "aufgabe.nicht_uebernommen"
RESERVIERUNG_ERINNERUNG = "reservierung.erinnerung"
RESERVIERUNG_ABGELAUFEN = "reservierung.abgelaufen"


def typen_deklarieren():
    registry.typ_deklarieren(
        VERFALL_VORWARNUNG,
        modul="aufgaben",
        bezeichnung="Aufgabe läuft bald ab (noch nicht übernommen)",
        zielgruppe="eltern",
        standard_kanaele=["push", "email"],
    )
    registry.typ_deklarieren(
        NICHT_UEBERNOMMEN,
        modul="aufgaben",
        bezeichnung="Aufgabe nicht übernommen",
        zielgruppe="eltern",
        standard_kanaele=[],  # nur Dashboard-Liste (stiller Verfall, SPEC 5.6)
    )
    registry.typ_deklarieren(
        RESERVIERUNG_ERINNERUNG,
        modul="aufgaben",
        bezeichnung="Erinnerung: Reservierung läuft bald ab",
        zielgruppe="kind",
        standard_kanaele=["push"],
        push_ttl_sekunden=6 * 3600,
    )
    registry.typ_deklarieren(
        RESERVIERUNG_ABGELAUFEN,
        modul="aufgaben",
        bezeichnung="Reservierung abgelaufen",
        zielgruppe="eltern",
        standard_kanaele=["push", "email"],
    )
