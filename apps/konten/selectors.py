"""Lesende Abfragen von konten (für Anmeldeseiten und andere Apps)."""

from apps.kern import zeit

from . import moods, sperre
from .models import (
    Benutzer,
    ElternProfil,
    ElternZugang,
    Geraet,
    KindProfil,
    MoodAusgeblendet,
    MoodEigen,
    MoodVorschlag,
    Rolle,
    VorschlagStatus,
)


def aktive_kinder():
    return Benutzer.objects.filter(rolle=Rolle.KIND, aktiv=True).select_related("kindprofil")


def aktive_eltern():
    return Benutzer.objects.filter(rolle=Rolle.ELTERN, aktiv=True)


def kind_gesperrt_bis(kind):
    """Sperrende der PIN-Eingabe oder ``None`` (z. B. für Eltern-Dashboard und Kachel)."""
    # frisch aus der DB, nicht über ein evtl. veraltetes ``kind.kindprofil``
    profil = KindProfil.objects.get(benutzer=kind)
    return sperre.kind_gesperrt_bis(profil, zeit.jetzt())


def gesperrte_kinder():
    jetzt = zeit.jetzt()
    return [k for k in aktive_kinder() if sperre.kind_gesperrt_bis(k.kindprofil, jetzt)]


def geraete(nur_aktive=True):
    qs = Geraet.objects.select_related("registriert_von")
    return qs.filter(aktiv=True) if nur_aktive else qs


def eltern_email(benutzer):
    """E-Mail-Adresse eines Elternteils oder ``""``."""
    return ElternProfil.objects.filter(pk=benutzer.pk).values_list("email", flat=True).first() or ""


def eltern_passwort_gesetzt():
    """Gibt es ein Eltern-Passwort? (Der Hash selbst verlässt konten nie.)"""
    return ElternZugang.objects.filter(pk=1).exists()


# --- Moods -------------------------------------------------------------------------------------


def moods_ausgeblendet():
    return set(MoodAusgeblendet.objects.values_list("schluessel", flat=True))


def moods_eigene(nur_aktive=True):
    qs = MoodEigen.objects.all()
    return qs.filter(aktiv=True) if nur_aktive else qs


def mood_auswahl():
    """Moods, die ein Kind wählen kann: ``[(schluessel, "🦥 Text", gruppe)]``. Katalog ohne
    ausgeblendete, danach die eigenen der Familie (Gruppe ``eigen``)."""
    aus = moods_ausgeblendet()
    liste = [
        (m.schluessel, moods.anzeige(m), m.gruppe) for m in moods.KATALOG if m.schluessel not in aus
    ]
    liste += [(e.schluessel, f"⭐ {e.text}", "eigen") for e in moods_eigene()]
    return liste


def mood_texte(benutzer):
    """``{benutzer.pk: "🦥 Faultier-Modus"}`` für Benutzer mit einem gültigen Mood (eine
    Abfrage je Quelle, nicht je Benutzer). Ausgeblendete oder entfernte Moods fehlen."""
    gueltig = {schluessel: text for schluessel, text, _gruppe in mood_auswahl()}
    return {b.pk: gueltig[b.mood] for b in benutzer if b.mood in gueltig}


def mood_text(benutzer):
    """Mood-Zeile eines Benutzers oder ``""``."""
    return mood_texte([benutzer]).get(benutzer.pk, "")


def mood_vorschlaege(status=VorschlagStatus.OFFEN):
    return MoodVorschlag.objects.filter(status=status).select_related("kind")


def mood_vorschlaege_offen_anzahl():
    return MoodVorschlag.objects.filter(status=VorschlagStatus.OFFEN).count()


def mood_vorschlaege_von(kind):
    """Offene Vorschläge eines Kindes (für dessen Einstellungen)."""
    return MoodVorschlag.objects.filter(kind=kind, status=VorschlagStatus.OFFEN)
