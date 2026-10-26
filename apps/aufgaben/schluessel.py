"""Buchungs- und Aktivitätsschlüssel einer Instanz. Nach dem Nachbessern beginnt eine neue Runde
(``nachbessern_anzahl``): Runde 0 behält die alten Schlüssel, danach hängt ``:n<Runde>`` an, damit
die Idempotenz der Punktebuchung die erneute Gutschrift nicht verschluckt."""


def suffix(anzahl) -> str:
    return f":n{anzahl}" if anzahl else ""


def buchung(instanz_pk, art, anzahl=0) -> str:
    return f"aufgabe:{instanz_pk}:{art}{suffix(anzahl)}"


def aktivitaet(instanz_pk, anzahl=0) -> str:
    return f"{instanz_pk}{suffix(anzahl)}"
