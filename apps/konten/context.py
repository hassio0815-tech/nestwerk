"""Template-Kontext: Akzentfarbe des angemeldeten Kindes und Leerlauf-Werte für das Kiosk-Tablet."""

from apps.kern import einstellungen

from . import akzent, sitzung
from .models import Rolle


def konten(request):
    user = getattr(request, "user", None)
    kontext = {}
    if user is None or not user.is_authenticated:
        return kontext
    if user.rolle == Rolle.KIND:
        kontext["akzent"] = akzent.akzent_name(user)
    if sitzung.ist_kiosk_sitzung(request):
        werte = einstellungen.werte(
            "konten.kiosk_leerlauf_sekunden", "konten.kiosk_warnung_sekunden"
        )
        kontext["kiosk_leerlauf_sekunden"] = werte["konten.kiosk_leerlauf_sekunden"]
        kontext["kiosk_warnung_sekunden"] = werte["konten.kiosk_warnung_sekunden"]
    return kontext
