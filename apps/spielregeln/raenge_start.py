"""Startwerte der Ränge (Entscheidung 14, SPEC 18.1; Bauzeiten O4 in Tagen x 24)."""

from django.utils.translation import gettext_noop as _

# (stufe, schluessel, name, xp_schwelle, min_aktive_wochen, mod_preis, bauzeit_tage, farbe)
RAENGE = (
    (1, "common", _("Common"), 0, 0, 40, 2, "#9ca3af"),
    (2, "uncommon", _("Uncommon"), 2000, 20, 60, 3, "#34d670"),
    (3, "rare", _("Rare"), 5000, 42, 90, 4, "#3b82f6"),
    (4, "epic", _("Epic"), 9000, 64, 130, 5, "#a855f7"),
    (5, "legendary", _("Legendary"), 14000, 90, 180, 7, "#facc15"),
    (6, "godmode", _("God Mode"), 20000, 120, 250, 7, "#ff6bd6"),
)


def anlegen(rang_modell, kalibrierung_modell):
    """Legt fehlende Ränge und die globale Kalibrierung (1,00) an; überschreibt nie."""
    for stufe, schluessel, name, xp, wochen, preis, tage, farbe in RAENGE:
        rang_modell.objects.get_or_create(
            schluessel=schluessel,
            defaults={
                "stufe": stufe,
                "name": name,
                "xp_schwelle": xp,
                "min_aktive_wochen": wochen,
                "mod_preis": preis,
                "bauzeit_stunden": tage * 24,
                "farbe": farbe,
                "ist_endstufe": schluessel == "godmode",
            },
        )
    if not kalibrierung_modell.objects.filter(kind__isnull=True).exists():
        kalibrierung_modell.objects.create(kind=None)
