"""Schreibende Schnittstelle von belohnung (SPEC "Einlösen und Belohnungskatalog").

- ``antrag_stellen``: das Kind beantragt eine Belohnung. Offene Anträge reservieren Guthaben
  (``selectors.offene_reservierung`` über die punkte-Registry); beantragt werden kann höchstens
  das verfügbare Guthaben. Taschengeld zählt zusätzlich gegen das Monatslimit.
- ``bestaetigen``: genau eine Buchung (Art Einlösung, Schlüssel ``antrag:<id>``) plus Ereignis.
  Mehrfaches Bestätigen (Doppelklick) ändert nichts.
- ``ablehnen`` / ``zurueckziehen``: Reservierung fällt weg, es gibt keine Buchung.

Prüfung und Schreiben laufen in einer Transaktion. SQLite startet sie mit ``BEGIN IMMEDIATE``
(Schreibsperre ab Beginn), parallele Anträge und Entscheidungen werden dadurch serialisiert.
Die Sperrregel selbst kommt aus ``punkte.services.schreibsperre`` (eine Stelle für beide).
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit
from apps.konten.models import Rolle
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte_services
from apps.punkte.services import Art

from . import selectors
from .events import ABGELEHNT, ANTRAG, BESTAETIGT
from .models import Belohnung, Einloeseantrag, Status, TaschengeldLimit

__all__ = [
    "AntragNichtOffen",
    "BelohnungFehler",
    "BelohnungInaktiv",
    "GuthabenReichtNicht",
    "LimitUeberschritten",
    "ablehnen",
    "belohnung_aktiv_setzen",
    "belohnung_speichern",
    "standard_limit_setzen",
    "antrag_stellen",
    "bestaetigen",
    "limit_setzen",
    "zurueckziehen",
]


class BelohnungFehler(ValueError):
    """Basis der fachlichen Fehler von belohnung (Meldungstext ist für Nutzer gedacht)."""


class BelohnungInaktiv(BelohnungFehler):
    pass


class GuthabenReichtNicht(BelohnungFehler):
    pass


class LimitUeberschritten(BelohnungFehler):
    pass


class AntragNichtOffen(BelohnungFehler):
    pass


def antrag_stellen(kind, belohnung):
    """Legt einen offenen Antrag an und gibt ihn zurück."""
    if getattr(kind, "rolle", None) != Rolle.KIND:
        raise PermissionDenied("Nur Kinder stellen Anträge")
    with transaction.atomic():
        punkte_services.schreibsperre(kind)
        belohnung = Belohnung.objects.select_related("kategorie").get(pk=belohnung.pk)
        if not belohnung.aktiv:
            raise BelohnungInaktiv("Diese Belohnung gibt es gerade nicht.")
        verfuegbar = punkte_selectors.verfuegbar(kind)
        if belohnung.preis_punkte > verfuegbar:
            raise GuthabenReichtNicht(
                f"Dafür fehlen dir noch {belohnung.preis_punkte - verfuegbar} Punkte."
            )
        if belohnung.kategorie.ist_taschengeld:
            frei = selectors.taschengeld_frei_cent(kind)
            if (belohnung.geldwert_cent or 0) > frei:
                raise LimitUeberschritten(
                    f"Das Taschengeld-Limit für diesen Monat ist erreicht "
                    f"(noch frei: {_euro(frei)})."
                )
        antrag = Einloeseantrag.objects.create(
            kind=kind,
            belohnung=belohnung,
            titel_snapshot=belohnung.titel,
            preis_snapshot=belohnung.preis_punkte,
            geldwert_cent_snapshot=belohnung.geldwert_cent,
        )
        audit.protokollieren(
            "belohnung.beantragt",
            akteur=kind,
            objekt=antrag,
            kind=kind,
            details=_details(antrag),
        )
        ereignisse.veroeffentlichen(
            ANTRAG,
            daten={
                "antrag": antrag.pk,
                "belohnung": antrag.titel_snapshot,
                "preis": antrag.preis_snapshot,
            },
            schluessel=f"{ANTRAG}:{antrag.pk}",
            kind=kind,
            akteur=kind,
        )
        return antrag


def bestaetigen(antrag, *, von):
    """Bucht die Einlösung genau einmal. Ist der Antrag schon bestätigt, passiert nichts."""
    _eltern_pruefen(von)
    with transaction.atomic():
        antrag = _sperren_und_laden(antrag)
        if antrag.status == Status.BESTAETIGT:
            return antrag
        _offen_pruefen(antrag)
        try:
            buchung = punkte_services.buchen(
                antrag.kind,
                Art.EINLOESUNG,
                antrag.preis_snapshot,
                schluessel=f"antrag:{antrag.pk}",
                quelle_modul="belohnung",
                referenz=antrag,
                von=von,
                verfuegbar_pruefen=False,  # der Antrag selbst reserviert die Punkte schon
            )
        except punkte_services.GuthabenUnzureichend:
            raise GuthabenReichtNicht(
                f"{antrag.kind.anzeigename} hat nicht mehr genug Punkte für diese Belohnung."
            ) from None
        antrag.status = Status.BESTAETIGT
        antrag.buchung = buchung
        _entscheiden(antrag, von)
        audit.protokollieren(
            "belohnung.bestaetigt",
            akteur=von,
            objekt=antrag,
            kind=antrag.kind,
            details={**_details(antrag), "buchung": buchung.pk},
        )
        _entscheidung_melden(antrag, BESTAETIGT, von)
        return antrag


def ablehnen(antrag, *, von, grund=""):
    """Lehnt ab: Reservierung fällt weg, keine Buchung."""
    _eltern_pruefen(von)
    grund = (grund or "").strip()[:200]
    with transaction.atomic():
        antrag = _sperren_und_laden(antrag)
        if antrag.status == Status.ABGELEHNT:
            return antrag
        _offen_pruefen(antrag)
        antrag.status = Status.ABGELEHNT
        antrag.ablehnungsgrund = grund
        _entscheiden(antrag, von)
        details = _details(antrag)
        if grund:
            details["grund"] = grund
        audit.protokollieren(
            "belohnung.abgelehnt", akteur=von, objekt=antrag, kind=antrag.kind, details=details
        )
        _entscheidung_melden(antrag, ABGELEHNT, von)
        return antrag


def zurueckziehen(antrag, *, kind):
    """Das Kind zieht seinen eigenen offenen Antrag zurück."""
    with transaction.atomic():
        punkte_services.schreibsperre(kind)
        antrag = Einloeseantrag.objects.select_related("kind").get(pk=_pk(antrag))
        if antrag.kind_id != kind.pk:
            raise PermissionDenied("Das ist nicht dein Antrag")
        if antrag.status == Status.ZURUECKGEZOGEN:
            return antrag
        _offen_pruefen(antrag)
        antrag.status = Status.ZURUECKGEZOGEN
        antrag.entschieden_am = zeit.jetzt()
        antrag.save(update_fields=["status", "entschieden_am"])
        audit.protokollieren(
            "belohnung.zurueckgezogen",
            akteur=kind,
            objekt=antrag,
            kind=kind,
            details=_details(antrag),
        )
        return antrag


def limit_setzen(kind, cent, *, von):
    """Eigenes Monatslimit eines Kindes setzen (``None`` = Standard wieder verwenden)."""
    _eltern_pruefen(von)
    with transaction.atomic():
        if cent is None:
            TaschengeldLimit.objects.filter(kind=kind).delete()
        else:
            TaschengeldLimit.objects.update_or_create(
                kind=kind, defaults={"monatslimit_cent": cent}
            )
        audit.protokollieren(
            "belohnung.limit_gesetzt",
            akteur=von,
            objekt_typ="belohnung.taschengeldlimit",
            objekt_id=str(kind.pk),
            kind=kind,
            details={"monatslimit_cent": cent},
        )


# --- intern ----------------------------------------------------------------------------------


def _pk(antrag):
    return antrag.pk if isinstance(antrag, Einloeseantrag) else antrag


def _sperren_und_laden(antrag):
    """Schreibsperre für das Kind des Antrags, dann den Antrag frisch lesen."""
    kind = Einloeseantrag.objects.select_related("kind").get(pk=_pk(antrag)).kind
    punkte_services.schreibsperre(kind)
    return Einloeseantrag.objects.select_related("kind", "belohnung").get(pk=_pk(antrag))


def _offen_pruefen(antrag):
    if antrag.status != Status.OFFEN:
        raise AntragNichtOffen(f"Der Antrag ist schon {antrag.get_status_display().lower()}.")


def _entscheiden(antrag, von):
    antrag.entschieden_von = von
    antrag.entschieden_am = zeit.jetzt()
    antrag.save()


def _entscheidung_melden(antrag, typ, von):
    ereignisse.veroeffentlichen(
        typ,
        daten={"antrag": antrag.pk, "belohnung": antrag.titel_snapshot},
        schluessel=f"{typ}:{antrag.pk}",
        kind=antrag.kind,
        akteur=von,
    )


def _details(antrag):
    return {
        "antrag": antrag.pk,
        "belohnung": antrag.titel_snapshot,
        "preis": antrag.preis_snapshot,
        "geldwert_cent": antrag.geldwert_cent_snapshot,
    }


def _eltern_pruefen(von):
    if getattr(von, "rolle", None) != Rolle.ELTERN:
        raise PermissionDenied("Nur Eltern entscheiden über Anträge")


def _euro(cent):
    return f"{cent // 100},{cent % 100:02d} €"


# --- Katalogpflege (Eltern) --------------------------------------------------------------------


def belohnung_speichern(form, *, von):
    """Speichert ein validiertes ``BelohnungForm`` (neu oder bearbeitet) mit Audit."""
    _eltern_pruefen(von)
    neu = form.instance.pk is None
    with transaction.atomic():
        belohnung = form.save()
        audit.protokollieren(
            "belohnung.katalog_angelegt" if neu else "belohnung.katalog_geaendert",
            akteur=von,
            objekt=belohnung,
            details={
                "titel": belohnung.titel,
                "preis": belohnung.preis_punkte,
                "geldwert_cent": belohnung.geldwert_cent,
                "aktiv": belohnung.aktiv,
            },
        )
    return belohnung


def belohnung_aktiv_setzen(belohnung, aktiv, *, von):
    """(De-)aktiviert einen Katalogeintrag. Offene Anträge bleiben gültig (Snapshot)."""
    _eltern_pruefen(von)
    with transaction.atomic():
        if belohnung.aktiv != aktiv:
            belohnung.aktiv = aktiv
            belohnung.save(update_fields=["aktiv"])
            audit.protokollieren(
                "belohnung.katalog_aktiv",
                akteur=von,
                objekt=belohnung,
                details={"titel": belohnung.titel, "aktiv": aktiv},
            )
    return belohnung


def standard_limit_setzen(cent, *, von):
    """Standard-Monatslimit (Einstellung ``belohnung.taschengeld_limit_cent``)."""
    _eltern_pruefen(von)
    return einstellungen.setzen(selectors.LIMIT_SCHLUESSEL, cent, akteur=von)
