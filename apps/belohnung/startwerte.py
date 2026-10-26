"""Startwerte des Belohnungskatalogs (Entscheidung 13). Per Datenmigration eingespielt."""

# (Name, Symbol, Systemschlüssel)
KATEGORIEN = [
    ("Süßes", "geschenk", ""),
    ("Fernsehzeit", "tv", ""),
    ("Gaming/Computer", "controller", ""),
    ("Taschengeld", "muenze", "taschengeld"),
    ("Sonstiges", "stern", ""),
]

# (Titel, Kategorie, Preis in Punkten, Geldwert in Cent)
BELOHNUNGEN = [
    ("Süßes klein", "Süßes", 15, None),
    ("Süßes groß", "Süßes", 30, None),
    ("30 Min Fernsehen", "Fernsehzeit", 30, None),
    ("30 Min Konsole", "Gaming/Computer", 45, None),
    ("30 Min PC", "Gaming/Computer", 45, None),
    ("1 € Taschengeld", "Taschengeld", 30, 100),
]
