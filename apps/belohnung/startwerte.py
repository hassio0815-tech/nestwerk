"""Startwerte des Belohnungskatalogs (Entscheidung 13). Per Datenmigration eingespielt.

Die Texte sind deutsche Msgids (``gettext_noop``) und werden erst bei der Anzeige übersetzt
(``kern.sprache.uebersetzt``); von Eltern geänderte Texte bleiben unverändert."""

from django.utils.translation import gettext_noop

# (Name, Symbol, Systemschlüssel)
KATEGORIEN = [
    (gettext_noop("Süßes"), "geschenk", ""),
    (gettext_noop("Fernsehzeit"), "tv", ""),
    (gettext_noop("Gaming/Computer"), "controller", ""),
    (gettext_noop("Taschengeld"), "muenze", "taschengeld"),
    (gettext_noop("Sonstiges"), "stern", ""),
]

# (Titel, Kategorie, Preis in Punkten, Geldwert in Cent)
BELOHNUNGEN = [
    (gettext_noop("Süßes klein"), gettext_noop("Süßes"), 15, None),
    (gettext_noop("Süßes groß"), gettext_noop("Süßes"), 30, None),
    (gettext_noop("30 Min Fernsehen"), gettext_noop("Fernsehzeit"), 30, None),
    (gettext_noop("30 Min Konsole"), gettext_noop("Gaming/Computer"), 45, None),
    (gettext_noop("30 Min PC"), gettext_noop("Gaming/Computer"), 45, None),
    (gettext_noop("1 € Taschengeld"), gettext_noop("Taschengeld"), 30, 100),
]
