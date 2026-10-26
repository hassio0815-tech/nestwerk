"""Rate-Limit und Sperren (ARCHITECTURE 4.2/4.3, O11). Zustand liegt in der DB.

- Kind: Zähler je Kind (``KindProfil``), nicht je IP (das Tablet ist geteilt). Nach N
  Fehlversuchen Sperre; jede weitere Sperre verdoppelt die Dauer bis zum Höchstwert.
  Erfolg oder Entsperren durch Eltern setzt alles zurück.
- Eltern: Fehlversuche je IP im Zählfenster (``AnmeldeVersuch``). Versuche während einer
  Sperre werden nicht gezählt, die Sperre verlängert sich also nicht durch Angreifer.
"""

from datetime import timedelta

from django.db.models import Max

from apps.kern import einstellungen

from .models import AnmeldeArt, AnmeldeVersuch


def kind_gesperrt_bis(profil, jetzt):
    """Ende der Sperre oder ``None``, wenn nicht gesperrt."""
    if profil.pin_gesperrt_bis and profil.pin_gesperrt_bis > jetzt:
        return profil.pin_gesperrt_bis
    return None


def kind_sperrdauer(stufe):
    cfg = einstellungen.werte(
        "konten.kind_pin_sperre_minuten", "konten.kind_pin_sperre_max_minuten"
    )
    basis = cfg["konten.kind_pin_sperre_minuten"]
    hoechst = cfg["konten.kind_pin_sperre_max_minuten"]
    # Exponent deckeln, damit nichts überläuft; der Höchstwert greift ohnehin früher
    return timedelta(minutes=min(basis * 2 ** min(max(stufe, 1) - 1, 20), hoechst))


def kind_fehlversuch_erfassen(profil, jetzt):
    """Zählt einen Fehlversuch (Aufrufer hält die Transaktion). Gibt das Sperrende zurück,
    wenn dieser Versuch eine Sperre ausgelöst hat, sonst ``None``."""
    limit = einstellungen.wert("konten.kind_pin_fehlversuche")
    profil.pin_fehlversuche += 1
    gesperrt = None
    if profil.pin_fehlversuche >= limit:
        profil.pin_sperrstufe += 1
        profil.pin_fehlversuche = 0
        gesperrt = jetzt + kind_sperrdauer(profil.pin_sperrstufe)
        profil.pin_gesperrt_bis = gesperrt
    profil.save(update_fields=["pin_fehlversuche", "pin_sperrstufe", "pin_gesperrt_bis"])
    return gesperrt


def kind_zuruecksetzen(profil):
    """Erfolg oder Entsperren: Zähler, Stufe und Sperre löschen."""
    if profil.pin_fehlversuche or profil.pin_sperrstufe or profil.pin_gesperrt_bis:
        profil.pin_fehlversuche = 0
        profil.pin_sperrstufe = 0
        profil.pin_gesperrt_bis = None
        profil.save(update_fields=["pin_fehlversuche", "pin_sperrstufe", "pin_gesperrt_bis"])


def eltern_gesperrt_bis(ip, jetzt):
    """Ende der Sperre für diese IP (``None`` = unbekannte Adresse) oder ``None``."""
    cfg = einstellungen.werte("konten.eltern_fehlversuche", "konten.eltern_sperre_minuten")
    limit = cfg["konten.eltern_fehlversuche"]
    dauer = timedelta(minutes=cfg["konten.eltern_sperre_minuten"])
    versuche = AnmeldeVersuch.objects.filter(art=AnmeldeArt.ELTERN, ip=ip, zeit__gt=jetzt - dauer)
    seit = versuche.filter(erfolgreich=True).aggregate(m=Max("zeit"))["m"]
    fehler = versuche.filter(erfolgreich=False)
    if seit:
        fehler = fehler.filter(zeit__gt=seit)
    zeiten = list(fehler.order_by("-zeit").values_list("zeit", flat=True)[:limit])
    if len(zeiten) >= limit and zeiten[0] + dauer > jetzt:
        return zeiten[0] + dauer
    return None
