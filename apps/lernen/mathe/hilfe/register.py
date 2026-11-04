"""Anmeldung der Hilfe-Definitionen: je Generator eine Funktion ``(aufgabe) -> Hilfe``."""

_HILFEN = {}


def hilfe(generator_schluessel):
    """Decorator: meldet die Hilfe-Definition einer Rechenart an."""

    def anmelden(funktion):
        if generator_schluessel in _HILFEN:
            raise ValueError(f"Hilfe doppelt: {generator_schluessel}")
        _HILFEN[generator_schluessel] = funktion
        return funktion

    return anmelden


def definition(generator_schluessel):
    return _HILFEN.get(generator_schluessel)


def schluessel_alle():
    return tuple(_HILFEN)
