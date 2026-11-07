"""Datenmigration Etappe 11: bestehende Lernstände und Versuche bekommen ihre Karte und das
Thema. Idempotent, ohne Wirkung auf leere Datenbanken. Die Schlüsselregel steht in
``apps.lernen.historie.schluessel`` (hier bewusst als Kopie, damit die Migration stabil bleibt)."""

from django.db import migrations


def _schluessel(frage, richtung):
    if frage.generiert:
        return f"m:{frage.generator}:{(frage.gen_daten or {}).get('typ', '')}"[:160]
    return f"f:{frage.pk}:{richtung}"


def vorwaerts(apps, schema_editor):
    Karte = apps.get_model("lernen", "Karte")
    Lernstand = apps.get_model("lernen", "Lernstand")
    Versuch = apps.get_model("lernen", "Versuch")
    cache = {}

    def karte(kind_id, frage, richtung):
        schluessel = (kind_id, frage.thema.fach_id, _schluessel(frage, richtung))
        if schluessel not in cache:
            cache[schluessel], _ = Karte.objects.get_or_create(
                kind_id=kind_id, fach_id=schluessel[1], schluessel=schluessel[2]
            )
        return cache[schluessel]

    for stand in Lernstand.objects.filter(karte__isnull=True).select_related("frage__thema"):
        stand.karte = karte(stand.kind_id, stand.frage, stand.richtung)
        stand.save(update_fields=["karte"])
    offen = Versuch.objects.filter(frage__isnull=False, karte__isnull=True)
    for v in offen.select_related("frage__thema", "sitzung"):
        v.karte = karte(v.sitzung.kind_id, v.frage, v.richtung)
        v.thema_id = v.frage.thema_id
        v.save(update_fields=["karte", "thema"])
    for v in Versuch.objects.filter(thema__isnull=True, frage__isnull=False).select_related(
        "frage"
    ):
        v.thema_id = v.frage.thema_id
        v.save(update_fields=["thema"])


class Migration(migrations.Migration):
    dependencies = [("lernen", "0020_karte_historie")]

    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
