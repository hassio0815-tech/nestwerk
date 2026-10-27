"""Symbol-Schlüssel für Kategorien (Icons aus templates/komponenten/_sprite.html)."""

from django.utils.translation import gettext_lazy

SYMBOLE = (
    ("home", gettext_lazy("Haus")),
    ("kueche", gettext_lazy("Küche")),
    ("waesche", gettext_lazy("Wäsche")),
    ("garten", gettext_lazy("Garten")),
    ("schule", gettext_lazy("Schule")),
    ("liste", gettext_lazy("Liste")),
    ("stern", gettext_lazy("Stern")),
    ("geschenk", gettext_lazy("Geschenk")),
    ("kalender", gettext_lazy("Kalender")),
    ("muenze", gettext_lazy("Münze")),
)
