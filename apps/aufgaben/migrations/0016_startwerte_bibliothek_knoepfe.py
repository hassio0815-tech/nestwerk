"""Bibliothek -> Schnell-Knöpfe (Datenmigration).

- Vorlage "Zimmer gründlich" -> "Zimmer gründlich reinigen und aufräumen", 50 Punkte.
- Vorlage "Zimmer aufräumen" (falls vorhanden) -> 20 Punkte.
- Neue Vorlagen "Zimmer saugen" (15 Punkte) und "Waschmaschine ausräumen" (10 Punkte).
- Bestehende Knöpfe mit "Jedes-Kind"-Titel bekommen den Standard-Modus ``jedes``.
- Aus jeder aktiven Vorlage ohne gleichnamigen Knopf entsteht ein Knopf (Aufgabe "bei Bedarf").
  Eine Aufgabe braucht einen Ersteller: den ersten aktiven Elternteil. Gibt es noch keinen
  (frische Installation), passiert nichts, und der Job ``schnellknoepfe_sicherstellen`` holt es
  nach (Merker ``aufgaben.knoepfe_aus_bibliothek``). Wiederkehrende Aufgaben bleiben unberührt.

Die Seed-Titel stehen mit ``gettext_noop`` im Code: die DB speichert die deutsche Msgid, die
Oberfläche übersetzt sie (``|uebersetzt``, docs/i18n.md).
"""

from django.db import migrations
from django.utils.translation import gettext_noop

from apps.aufgaben import knoepfe_start
from apps.aufgaben.einstellungen import STARTWERTE_KNOEPFE_BIBLIOTHEK
from apps.kern.einstellungen import startwerte_schreiben

ALT = "Zimmer gründlich"
NEU = gettext_noop("Zimmer gründlich reinigen und aufräumen")
WIEDERHOLUNG = {
    "art": "bei_bedarf",
    "wochentage": [],
    "intervall_tage": None,
    "fenster_von": None,
    "fenster_bis": None,
    "fenster_tage": None,
    "limit_anzahl": None,
    "limit_zeitraum": "",
}
NEUE_VORLAGEN = [
    # (titel, punkte, kategorie, emoji)
    (gettext_noop("Zimmer saugen"), 15, gettext_noop("Haushalt"), "🧹"),
    (gettext_noop("Waschmaschine ausräumen"), 10, gettext_noop("Wäsche"), "🧺"),
]


def umwandeln(apps, schema_editor):
    Kategorie = apps.get_model("aufgaben", "Kategorie")
    Vorlage = apps.get_model("aufgaben", "Vorlage")
    Aufgabe = apps.get_model("aufgaben", "Aufgabe")
    Benutzer = apps.get_model("konten", "Benutzer")
    AuditEintrag = apps.get_model("kern", "AuditEintrag")
    Einstellung = apps.get_model("kern", "Einstellung")

    Vorlage.objects.filter(titel=ALT).update(titel=NEU, punkte=50)
    # Nutzer-Entscheidung 2026-11-07: normales Zimmer aufräumen = 20 P (gründlich = 50 P)
    Vorlage.objects.filter(titel="Zimmer aufräumen").update(punkte=20)
    for titel, punkte, kategorie, emoji in NEUE_VORLAGEN:
        if Vorlage.objects.filter(titel=titel).exists():
            continue
        Vorlage.objects.create(
            titel=titel,
            punkte=punkte,
            freigabeart="eltern",
            kategorie=Kategorie.objects.filter(name=kategorie).first(),
            wiederholung=WIEDERHOLUNG,
            emoji=emoji,
            schnellknopf_wer="alle",
            aktiv=True,
        )

    knoepfe_start.modus_der_knoepfe_setzen(Aufgabe)

    ersteller = (
        Benutzer.objects.filter(rolle="eltern", aktiv=True)
        .order_by("reihenfolge", "anzeigename")
        .first()
    )
    if ersteller is None:
        return

    def protokoll(aufgabe):
        AuditEintrag.objects.create(
            akteur=None,
            akteur_name="System",
            rolle="system",
            aktion="aufgabe.angelegt",
            objekt_typ="aufgaben.aufgabe",
            objekt_id=str(aufgabe.pk),
            details={
                "titel": aufgabe.titel,
                "punkte": aufgabe.punkte,
                "quelle": "bibliothek_umwandlung",
            },
        )

    knoepfe_start.aus_bibliothek_anlegen(Aufgabe, Vorlage, ersteller, protokoll)
    Einstellung.objects.filter(schluessel="aufgaben.knoepfe_aus_bibliothek").update(wert=True)


def merker(apps, schema_editor):
    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE_KNOEPFE_BIBLIOTHEK)


class Migration(migrations.Migration):
    dependencies = [
        ("kern", "0005_joblauf_aufbewahrung"),
        ("konten", "0008_kind_einstellungen_moods"),
        ("aufgaben", "0015_schnellknopf_modus"),
    ]

    # Reverse: bewusst nichts zurückbauen (angelegte Knöpfe sind Eltern-Inhalt)
    operations = [
        migrations.RunPython(merker, migrations.RunPython.noop),
        migrations.RunPython(umwandeln, migrations.RunPython.noop),
    ]
