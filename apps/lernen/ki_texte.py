"""Anzeigetexte zu KI-Fehlern und -Aufgaben (DE als msgid, EN in der .po-Datei).

Die Texte nennen nie Inhalte, Adressen oder Schlüssel; sie hängen nur am Fehlercode ``art``.
"""

from django.utils.translation import gettext_lazy as _

FEHLERTEXTE = {
    "konfiguration": _(
        "Die Einstellungen sind unvollständig oder ungültig (Adresse, Modell, Schlüssel)."
    ),
    "verbindung": _("Der KI-Server ist nicht erreichbar. Adresse und Netzwerk prüfen."),
    "zeitueberschreitung": _("Der KI-Server hat nicht rechtzeitig geantwortet."),
    "auth": _("Der KI-Server hat den Zugang abgelehnt. API-Schlüssel prüfen."),
    "limit": _("Der KI-Server meldet ein Limit (zu viele Anfragen oder Kontingent erschöpft)."),
    "server": _("Der KI-Server meldet einen eigenen Fehler. Später noch einmal versuchen."),
    "anfrage": _("Der KI-Server hat die Anfrage abgelehnt. Modellname und Adresse prüfen."),
    "ausgabe": _("Die Antwort war leer oder nicht lesbar."),
    "aus": _("Für diese Aufgabe ist keine KI eingeschaltet."),
    "einwilligung": _("Für diesen Cloud-Anbieter fehlt die Einwilligung der Eltern."),
    "intern": _("Unerwarteter Fehler."),
}


def fehlertext(art):
    return FEHLERTEXTE.get(art, FEHLERTEXTE["intern"])
