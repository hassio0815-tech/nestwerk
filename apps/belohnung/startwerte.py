"""Startwerte des Belohnungskatalogs (Entscheidung 13). Per Datenmigration eingespielt."""

# (Name, Symbol, Systemschlüssel)
KATEGORIEN = [
    ("Süßes", "geschenk", ""),
    ("Fernsehzeit", "uhr", ""),
    ("Gaming/Computer", "funke", ""),
    ("Taschengeld", "muenze", "taschengeld"),
    ("Sonstiges", "stern", ""),
]

# (Titel, Kategorie, Preis in Punkten, Geldwert in Cent)
BELOHNUNGEN = [
    ("Süßes klein", "Süßes", 15, None),
    ("Süßes groß", "Süßes", 30, None),
    ("30 Min Fernsehen", "Fernsehzeit", 30, None),
    ("30 Min Gaming/PC", "Gaming/Computer", 45, None),
    ("1 € Taschengeld", "Taschengeld", 30, 100),
]
