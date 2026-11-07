"""Die gewählte Lernstrategie bekommt eine Funktion (Etappe 14, W-8.5).

Statt nur "Dein Plan: ..." zu zeigen, erinnert die Frageseite an den ersten Schritt der
Strategie. Mathe hat eigene Sätze (keine "Wörter"); die Strategie "Beispiel" klappt dort
zusätzlich den Rechen-Tipp mit Beispiel auf. Rein rechnend, ohne Datenbank.
"""

from django.utils.translation import gettext, gettext_noop

from .models import Strategie

# (Vokabeln und Fragen, Mathe)
_HINWEISE = {
    Strategie.LAUT: (
        gettext_noop("Sprich das Wort laut aus, bevor du tippst."),
        gettext_noop("Sprich die Aufgabe und jeden Schritt laut, bevor du tippst."),
    ),
    Strategie.ABDECKEN: (
        gettext_noop("Denk erst in Ruhe nach. Dann tippst du."),
        gettext_noop("Denk erst in Ruhe nach. Dann tippst du."),
    ),
    Strategie.BILD: (
        gettext_noop("Stell dir zuerst ein Bild dazu vor."),
        gettext_noop("Mal dir kurz eine Skizze oder ein Bild zur Aufgabe vor."),
    ),
    Strategie.SATZ: (
        gettext_noop("Denk dir einen kurzen Satz dazu aus."),
        gettext_noop("Denk dir eine kleine Geschichte zur Aufgabe aus."),
    ),
    Strategie.AUFSCHREIBEN: (
        gettext_noop("Nimm ein Blatt und schreib es erst auf Papier auf. Dann tippst du."),
        gettext_noop("Nimm ein Blatt und rechne erst auf Papier. Dann tippst du das Ergebnis."),
    ),
    Strategie.BEISPIEL: (
        gettext_noop("Denk an ein Beispiel, das du schon kennst. Dann tippst du."),
        gettext_noop("Schau zuerst das Beispiel im Rechen-Tipp an. Dann rechnest du."),
    ),
}

# Diese Strategie klappt den Rechen-Tipp samt Beispiel von selbst auf
_KARTE_OFFEN = frozenset({Strategie.BEISPIEL})


def hinweis(strategie, *, mathe):
    """Der Hinweis zur Strategie (unübersetzt; Vorlage und Test übersetzen)."""
    texte = _HINWEISE.get(strategie)
    return gettext(texte[1 if mathe else 0]) if texte else ""


def karte_offen(strategie):
    return strategie in _KARTE_OFFEN
