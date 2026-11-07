"""Karte und Historie (Etappe 11, W-3): stabile Kennung der Wiederholungseinheit und die
Zusatzangaben, die ein Versuch für spätere Auswertungen mitbekommt. Rein lesend und
anlegend, ohne Wirkung auf Ablauf oder Punkte."""

from django.db.models import OuterRef, Subquery

from apps.kern import zeit

from .models import Frage, Karte, Lernstand, Versuch


def schluessel(frage, richtung):
    """Mathe: Rechenart und Aufgabentyp (die erzeugte Zeile wechselt, die Karte bleibt).
    Sonst: die Frage mit Richtung."""
    if frage.generiert:
        return f"m:{frage.generator}:{(frage.gen_daten or {}).get('typ', '')}"[:160]
    return f"f:{frage.pk}:{richtung}"


def karte_holen(kind, frage, richtung):
    """Die Karte des Kindes zu dieser Aufgabe (wird bei Bedarf angelegt)."""
    karte, _neu = Karte.objects.get_or_create(
        kind=kind, fach_id=frage.thema.fach_id, schluessel=schluessel(frage, richtung)
    )
    return karte


def versuch_felder(kind, frage, richtung):
    """Karte, Thema, Abstand in Tagen seit dem Versuch davor und der geplante Tag für den
    neuen Versuch. Vor dem Buchen des Lernstands aufrufen."""
    felder = {
        "karte": karte_holen(kind, frage, richtung),
        "thema_id": frage.thema_id,
        "abstand_tage": None,
        "geplant_am": None,
    }
    stand = Lernstand.objects.filter(kind=kind, frage=frage, richtung=richtung).first()
    if stand is not None:
        felder["geplant_am"] = stand.faellig_am
        if stand.zuletzt is not None:
            felder["abstand_tage"] = max(0, (zeit.jetzt() - stand.zuletzt).days)
    return felder


def karten_nachtragen():
    """Datenmigration und Reparatur: legt zu Lernständen und Versuchen ohne Karte die Karte an
    und setzt das Thema. Idempotent. Gibt die Zahl der geänderten Zeilen zurück."""
    geaendert = 0
    for stand in Lernstand.objects.filter(karte__isnull=True).select_related("frage__thema"):
        stand.karte = karte_holen(stand.kind, stand.frage, stand.richtung)
        stand.save(update_fields=["karte"])
        geaendert += 1
    offen = Versuch.objects.filter(frage__isnull=False).filter(karte__isnull=True)
    for v in offen.select_related("frage__thema", "sitzung"):
        v.karte = karte_holen(v.sitzung.kind, v.frage, v.richtung)
        v.thema_id = v.frage.thema_id
        v.save(update_fields=["karte", "thema"])
        geaendert += 1
    thema = Subquery(Frage.objects.filter(pk=OuterRef("frage_id")).values("thema_id")[:1])
    geaendert += Versuch.objects.filter(thema__isnull=True, frage__isnull=False).update(
        thema_id=thema
    )
    return geaendert
