"""Demo-Daten für die Oberflächen-Screenshots (läuft mit Django-Code gegen die Demo-DB).

Aufruf (setzt die Umgebung der Demo-Instanz voraus, siehe screenshots.py):
    python tools/oberflaeche/demo_daten.py
"""

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nestwerk.settings.entwicklung")

import django  # noqa: E402

django.setup()

from apps.aufgaben import ablauf, instanzen, selectors  # noqa: E402
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, Freigabeart  # noqa: E402
from apps.avatar import services as avatar  # noqa: E402
from apps.belohnung import services as belohnung  # noqa: E402
from apps.belohnung.models import Belohnung  # noqa: E402
from apps.konten.models import Benutzer  # noqa: E402
from apps.punkte import services as punkte  # noqa: E402
from apps.punkte.models import Art  # noqa: E402


def main():
    eltern = Benutzer.objects.filter(rolle="eltern").order_by("pk").first()
    kinder = {k.anzeigename: k for k in Benutzer.objects.filter(rolle="kind")}
    a, b = kinder["Kind A"], kinder["Kind B"]
    # Avatare (AP24): A Ritter (Mods kauft A unten, AP26), B Weltraum-Forscher, C wählt im Browser
    avatar.avatar_waehlen(a, "ritter", {"haut": "haut3", "haar": "haar2", "frisur": "struppig"})
    avatar.avatar_waehlen(b, "weltraum", {"haut": "haut5", "haar": "haar7", "frisur": "lang"})

    arten = [Freigabeart.ELTERN, Freigabeart.VERTRAUEN, Freigabeart.ELTERN, Freigabeart.NACHWEIS]
    for nr, vorlage in enumerate(list(selectors.vorlagen())[:6]):
        Aufgabe.objects.create(
            titel=vorlage.titel,
            beschreibung=vorlage.beschreibung,
            punkte=vorlage.punkte,
            kategorie=vorlage.kategorie,
            freigabeart=arten[nr % len(arten)],
            erstellt_von=eltern,
            start_datum=date.today(),
            wiederholungsart="intervall",
            intervall_tage=1 + nr % 3,
        )
    instanzen.instanzen_erzeugen()

    offene = list(AufgabenInstanz.objects.filter(status="offen").order_by("pk"))
    mit_meldung = [i for i in offene if i.aufgabe.freigabeart == Freigabeart.ELTERN] or offene
    erste = mit_meldung[0]
    ablauf.interesse_zeigen(erste, a)
    erste.refresh_from_db()
    ablauf.erledigt_melden(erste, a, text="Habe ich heute Morgen gemacht.")
    # eine zweite Aufgabe nur reservieren
    rest = [i for i in AufgabenInstanz.objects.filter(status="offen") if i.pk != erste.pk]
    if rest:
        ablauf.interesse_zeigen(rest[0], a)

    punkte.buchen(b, Art.AUFGABE, 120, schluessel="demo:b", quelle_modul="aufgaben")
    punkte.buchen(a, Art.AUFGABE, 40, schluessel="demo:a", quelle_modul="aufgaben")
    wunsch = Belohnung.objects.filter(aktiv=True).order_by("preis_punkte").first()
    if wunsch:
        belohnung.antrag_stellen(b, wunsch)
    # Mod-Shop (AP26): A kauft 4 Common-Mods (Eltern stellen sie sofort fertig, Zeitbremse
    # -> einer zählt diese Woche, drei warten) und hat einen Mod im Bau
    punkte.buchen(a, Art.AUFGABE, 260, schluessel="demo:a-mods", quelle_modul="aufgaben")
    for slot in ("kopf", "koerper", "hand", "begleiter"):
        besitz = avatar.mod_kaufen(a, f"ritter-{slot}-1")
        avatar.bau_sofort_fertigstellen(besitz, von=eltern)
    avatar.mod_kaufen(a, "ritter-ruecken-1")
    print("Demo-Daten erzeugt.")


if __name__ == "__main__":
    main()
