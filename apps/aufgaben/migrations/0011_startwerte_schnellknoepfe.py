"""Startwerte: Schnell-Knöpfe (Wiederholungsart "bei Bedarf") als Bibliotheksvorlagen.

Restmüll, Biomüll und Altglas: je 5 Punkte, Eltern bestätigen, alle dürfen drücken. Die
Vorlage "Altglas" gibt es seit 0002 (einmalige Vertrauens-Aufgabe, 15 Punkte); ist sie noch
unverändert, wird sie zum Schnell-Knopf umgewandelt (kein Doppel). Eltern legen daraus über
"Als Aufgabe" ihre Knöpfe an (eine Aufgabe braucht einen Ersteller, den es bei der
Migration noch nicht gibt).
"""

from django.db import migrations
from django.utils.translation import gettext_noop

KNOEPFE = [
    # (titel, emoji)
    (gettext_noop("Restmüll"), "🗑️"),
    (gettext_noop("Biomüll"), "🍂"),
    (gettext_noop("Altglas"), "🍾"),
]
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


def anlegen(apps, schema_editor):
    Kategorie = apps.get_model("aufgaben", "Kategorie")
    Vorlage = apps.get_model("aufgaben", "Vorlage")
    haushalt = Kategorie.objects.get(name="Haushalt")
    for titel, emoji in KNOEPFE:
        felder = {
            "punkte": 5,
            "freigabeart": "eltern",
            "kategorie": haushalt,
            "wiederholung": WIEDERHOLUNG,
            "emoji": emoji,
            "schnellknopf_wer": "alle",
        }
        vorhanden = Vorlage.objects.filter(titel=titel).first()
        if vorhanden is None:
            Vorlage.objects.create(titel=titel, aktiv=True, **felder)
        elif (
            vorhanden.wiederholung is None
            and vorhanden.punkte == 15
            and vorhanden.freigabeart == "vertrauen"
        ):
            for name, wert in felder.items():
                setattr(vorhanden, name, wert)
            vorhanden.save()


class Migration(migrations.Migration):
    dependencies = [("aufgaben", "0010_schnellknoepfe")]
    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
