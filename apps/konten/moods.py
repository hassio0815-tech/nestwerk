"""Mood-Kataloge (feste Kataloge, reine Daten), getrennt nach Zielgruppe: ``kind`` und ``eltern``.
Jeder wählt seinen Mood in den Einstellungen; er erscheint als kleine Zeile unter dem Namen.
Eltern können Katalog-Moods ausblenden und eigene ergänzen (``services.mood_*``), je Zielgruppe
getrennt; zugelassene Kinder-Vorschläge gelten für alle Kinder."""

import random
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

# Schlüssel eigener Moods (aus der Datenbank): ``eigen-<id>``
EIGEN_PRAEFIX = "eigen-"
TEXT_MAX = 40

# Zielgruppen (Werte von ``MoodEigen.zielgruppe``)
KIND = "kind"
ELTERN = "eltern"
ZIELGRUPPEN = (KIND, ELTERN)


@dataclass(frozen=True)
class Mood:
    schluessel: str
    emoji: str
    text: str
    gruppe: str
    spruch: str = ""

    @property
    def titel(self):
        return self.text

    @property
    def anzeige(self):
        """``"🦥 Faultier-Modus"``."""
        return f"{self.emoji} {self.text}"


G_TREND = "trend"
G_FILM = "film"
G_MUEDE = "muede"
G_GUT = "gut"
G_GRUMMELIG = "grummelig"
G_RUHIG = "ruhig"
G_ELTERN = "eltern"

GRUPPEN = (
    (G_TREND, _("Meme und Trends")),
    (G_FILM, _("Filme und Figuren")),
    (G_MUEDE, _("Müde und chillig")),
    (G_GUT, _("Gut drauf")),
    (G_GRUMMELIG, _("Grummelig")),
    (G_RUHIG, _("Ruhig und besonders")),
)

KATALOG = (
    # Meme / Trends
    Mood("six_seven", "6️⃣", _("Six Seven"), G_TREND),
    Mood("skibidi", "🚽", _("Skibidi-Laune"), G_TREND),
    Mood("sigma", "🐺", _("Sigma-Modus"), G_TREND),
    Mood("aura", "✨", _("Aura +1000"), G_TREND),
    Mood("lowkey_muede", "🥱", _("Lowkey müde"), G_TREND),
    Mood("cooken", "🍳", _("Gerade am Cooken"), G_TREND),
    Mood("no_cap", "🧢", _("No cap heute top"), G_TREND),
    Mood("rizz", "😎", _("Rizz-Level hoch"), G_TREND),
    Mood("brainrot", "🧠", _("Brainrot aktiv"), G_TREND),
    Mood("npc", "🤖", _("NPC-Modus"), G_TREND),
    # Filme / Figuren
    Mood("griesgram", "🎄", _("Grüner Griesgram"), G_FILM),
    Mood("bananen", "🍌", _("Gelbes Bananen-Chaos"), G_FILM),
    Mood("sumpf", "🧅", _("Sumpf-Laune"), G_FILM),
    Mood("drachen", "🐲", _("Drachenzähmer"), G_FILM),
    Mood("ninja", "🥷", _("Ninja im Training"), G_FILM),
    Mood("zauberlehrling", "🪄", _("Zauberlehrling"), G_FILM),
    Mood("superheld_pause", "🦸", _("Superheld auf Pause"), G_FILM),
    Mood("pirat", "🏴‍☠️", _("Piratenkapitän"), G_FILM),
    Mood("meister", "🧘", _("Weiser Meister"), G_FILM),
    Mood("einhorn", "🦄", _("Einhorn-Glitzer"), G_FILM),
    # Müde / chillig
    Mood("faultier", "🦥", _("Faultier-Modus"), G_MUEDE),
    Mood("kissenburg", "🛏️", _("Kissenburg-Bewohner"), G_MUEDE),
    Mood("akku_1", "🪫", _("Akku bei 1 %"), G_MUEDE),
    Mood("sofa_held", "🛋️", _("Sofa-Held"), G_MUEDE),
    Mood("kakao", "☕", _("Kaffee? Kakao!"), G_MUEDE),
    Mood("winterschlaf", "🐻", _("Winterschlaf light"), G_MUEDE),
    Mood("villain", "😏", _("Ich chille ich villain"), G_MUEDE),
    Mood("gaehn_meister", "😴", _("Gähn-Meister"), G_MUEDE),
    # Gut drauf
    Mood("eichhoernchen", "🐿️", _("Hyperaktives Eichhörnchen"), G_GUT),
    Mood("keks", "🍪", _("Keks-Laune"), G_GUT),
    Mood("pizza", "🍕", _("Pizza-Power"), G_GUT),
    Mood("regenbogen", "🌈", _("Regenbogen-Stimmung"), G_GUT),
    Mood("raketenstart", "🚀", _("Raketenstart"), G_GUT),
    Mood("konfetti", "🎉", _("Konfetti im Kopf"), G_GUT),
    Mood("level_up", "🎮", _("Level-Up-Laune"), G_GUT),
    Mood("boss", "👑", _("Boss-Modus"), G_GUT),
    Mood("tanzmaus", "💃", _("Tanzmaus"), G_GUT),
    Mood("ohne_ende", "🔋", _("Energie ohne Ende"), G_GUT),
    # Grummelig
    Mood("nicht_fuettern", "🦖", _("Bitte nicht füttern"), G_GRUMMELIG),
    Mood("gewitter", "⛈️", _("Gewitterwolke"), G_GRUMMELIG),
    Mood("toast", "🍞", _("Wütender Toast"), G_GRUMMELIG),
    Mood("kaktus", "🌵", _("Kaktus-Laune"), G_GRUMMELIG),
    Mood("bissig", "🦈", _("Heute bissig"), G_GRUMMELIG),
    Mood("drama_lama", "🦙", _("Drama-Lama"), G_GRUMMELIG),
    # Ruhig / besonders
    Mood("zen_panda", "🐼", _("Zen-Panda"), G_RUHIG),
    Mood("detektiv", "🕵️", _("Detektiv unterwegs"), G_RUHIG),
    Mood("zocker", "🕹️", _("Zocker-Fokus"), G_RUHIG),
    Mood("buecherwurm", "📚", _("Bücherwurm"), G_RUHIG),
    Mood("zimmer_mission", "🧹", _("Mission: Zimmer aufräumen"), G_RUHIG),
    Mood("flow", "🌊", _("Gerade im Flow"), G_RUHIG),
)
NACH_SCHLUESSEL = {m.schluessel: m for m in KATALOG}

# Eltern-Katalog: die früheren Wappen (Schlüssel unverändert, damit die Wahl bestehen bleibt)
# plus „Geek“. Eine Gruppe, mit Spruch.
GRUPPEN_ELTERN = ((G_ELTERN, _("Moods für Eltern")),)
KATALOG_ELTERN = (
    Mood("hausdrache", "🐉", _("Hausdrache"), G_ELTERN, _("Bewacht den Kühlschrank")),
    Mood("rudelchef", "🦁", _("Rudelchef"), G_ELTERN, _("Hat das letzte Wort … meistens")),
    Mood(
        "kuechenchef", "🍳", _("Küchenchef"), G_ELTERN, _("Heute gibt's, was auf den Tisch kommt")
    ),
    Mood("familientaxi", "🚕", _("Familien-Taxi"), G_ELTERN, _("24/7 im Einsatz")),
    Mood("bank", "🏦", _("Bank of Mama/Papa"), G_ELTERN, _("Kein Dispo!")),
    Mood("grillmeister", "🔥", _("Grillmeister"), G_ELTERN, _("Fasst die Zange nicht ab")),
    Mood("nachteule", "🦉", _("Nachteule"), G_ELTERN, _("Sieht alles, auch nach 22 Uhr")),
    Mood("sockenfinder", "🧦", _("Sockenfinder"), G_ELTERN, _("Kennt jeden verlorenen Socken")),
    Mood("burgherr", "🛡️", _("Burgherr/Burgfrau"), G_ELTERN, _("Hüter des Nests")),
    Mood("geek", "🤓", _("Geek"), G_ELTERN, _("Hat für alles ein Kabel")),
)
NACH_SCHLUESSEL_ELTERN = {m.schluessel: m for m in KATALOG_ELTERN}


def katalog(zielgruppe=KIND):
    return KATALOG_ELTERN if zielgruppe == ELTERN else KATALOG


def gruppen(zielgruppe=KIND):
    return GRUPPEN_ELTERN if zielgruppe == ELTERN else GRUPPEN


def nach_schluessel(zielgruppe=KIND):
    return NACH_SCHLUESSEL_ELTERN if zielgruppe == ELTERN else NACH_SCHLUESSEL


def info(schluessel, zielgruppe=KIND):
    return nach_schluessel(zielgruppe).get(schluessel)


def zufaellig_eltern(belegt=()):
    """Zufälliger Eltern-Mood, möglichst einer, den andere Eltern nicht schon haben."""
    frei = [m for m in KATALOG_ELTERN if m.schluessel not in set(belegt)]
    return random.choice(frei or KATALOG_ELTERN).schluessel


def anzeige(mood):
    """``"🦥 Faultier-Modus"`` für einen Katalog-Mood."""
    return f"{mood.emoji} {mood.text}"
