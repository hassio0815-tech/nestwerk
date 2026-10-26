"""Zustandsautomat der Aufgaben-Instanz (DATA_MODEL 7.4, ARCHITECTURE 13.2 K1/K2/K11).

Alle erlaubten Übergänge stehen zentral in ``UEBERGAENGE``. Jeder Statuswechsel läuft über
``uebergang()``: Prüfung gegen die Tabelle, dann bedingtes ``UPDATE ... WHERE status = alt``
(parallele Klicks/Jobs: nur einer gewinnt, der andere bekommt ``UngueltigerUebergang``).

::

    offen      -> reserviert         Kind wählt (ein Interessent)
    offen      -> nicht_uebernommen  Fensterende (Job verfall_pruefen)
    reserviert -> konflikt           weiteres Kind wählt (Einstellung mitbewerben_erlaubt)
    reserviert -> offen              Ablauf (ungebunden) / Eltern lösen / Kind gibt zurück
    reserviert -> nicht_uebernommen  Ablauf am Fensterende (zeitgebunden: wieder frei ist sinnlos)
    reserviert -> gemeldet           Kind meldet erledigt (Eltern / Nachweis)
    reserviert -> bestaetigt         Kind meldet erledigt (Vertrauen: sofort Punkte)
    konflikt   -> reserviert         Eltern teilen zu / Rückzug bis auf ein Kind (K11: Frist neu)
    konflikt   -> offen              Eltern lösen
    konflikt   -> nicht_uebernommen  Fensterende ohne Zuteilung
    bestaetigt -> nachbessern        Eltern geben zurück (Punkte zurück, Frist nachbessern_bis)
    nachbessern -> gemeldet | storniert   Kind meldet erneut / Frist abgelaufen
    gemeldet   -> bestaetigt | abgelehnt | rueckfrage   Eltern entscheiden
    rueckfrage -> gemeldet           Kind antwortet
    rueckfrage -> bestaetigt | abgelehnt                Eltern entscheiden ohne Antwort
    bestaetigt -> storniert          Korrektur (Gegenbuchung, K2)

Endzustände: ``abgelehnt``, ``nicht_uebernommen``, ``storniert``.
"""

from __future__ import annotations

from .models import AufgabenInstanz, InstanzStatus

S = InstanzStatus

UEBERGAENGE: dict[str, frozenset[str]] = {
    S.OFFEN: frozenset({S.RESERVIERT, S.NICHT_UEBERNOMMEN}),
    S.RESERVIERT: frozenset({S.KONFLIKT, S.OFFEN, S.NICHT_UEBERNOMMEN, S.GEMELDET, S.BESTAETIGT}),
    S.KONFLIKT: frozenset({S.RESERVIERT, S.OFFEN, S.NICHT_UEBERNOMMEN}),
    S.GEMELDET: frozenset({S.BESTAETIGT, S.ABGELEHNT, S.RUECKFRAGE}),
    S.RUECKFRAGE: frozenset({S.GEMELDET, S.BESTAETIGT, S.ABGELEHNT}),
    S.BESTAETIGT: frozenset({S.STORNIERT, S.NACHBESSERN}),
    S.NACHBESSERN: frozenset({S.GEMELDET, S.STORNIERT}),
    S.ABGELEHNT: frozenset(),
    S.NICHT_UEBERNOMMEN: frozenset(),
    S.STORNIERT: frozenset(),
}

ENDZUSTAENDE = frozenset(s for s, ziele in UEBERGAENGE.items() if not ziele)


class AblaufFehler(ValueError):
    """Fachlicher Fehler im Kinderablauf; ``str(fehler)`` ist ein Text für die Oberfläche."""


class UngueltigerUebergang(AblaufFehler):
    """Übergang ist nicht erlaubt oder die Instanz wurde inzwischen geändert."""


def erlaubt(von: str, nach: str) -> bool:
    return nach in UEBERGAENGE.get(von, frozenset())


def pruefen(von: str, nach: str) -> None:
    if not erlaubt(von, nach):
        raise UngueltigerUebergang(
            f"Das geht gerade nicht (Status „{S(von).label}“ → „{S(nach).label}“)."
        )


def uebergang(instanz: AufgabenInstanz, nach: str, *, von=None, bedingung=None, **felder):
    """Setzt ``instanz`` (bedingt) von ``von`` (Standard: aktueller Status des Objekts; auch
    Tupel mehrerer Ausgangszustände) auf ``nach`` und schreibt ``felder`` mit.

    ``bedingung``: weitere Filter für das bedingte Update (z. B. ``{"kind": kind}``).
    Kein Treffer (paralleler Wechsel) -> ``UngueltigerUebergang``. Gibt die Instanz mit den
    neuen Werten zurück.
    """
    ausgang = (von,) if isinstance(von, str) else tuple(von or (instanz.status,))
    if instanz.status not in ausgang:
        raise UngueltigerUebergang("Die Aufgabe wurde inzwischen geändert.")
    for status in ausgang:
        pruefen(status, nach)
    treffer = AufgabenInstanz.objects.filter(
        pk=instanz.pk, status__in=ausgang, **(bedingung or {})
    ).update(status=nach, **felder)
    if not treffer:
        raise UngueltigerUebergang("Die Aufgabe wurde inzwischen geändert.")
    instanz.status = nach
    for name, wert in felder.items():
        setattr(instanz, name, wert)
    return instanz
