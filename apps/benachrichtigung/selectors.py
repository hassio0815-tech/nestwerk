"""Lesende Schnittstelle von benachrichtigung."""

from apps.ereignisse import registry as ereignis_registry
from apps.ereignisse import selectors as ereignis_selectors
from apps.ereignisse.models import Zielgruppe
from apps.konten.models import Rolle

from . import registry
from .models import (
    Benachrichtigung,
    BenachrichtigungsProfil,
    Kanal,
    Popup,
    Praeferenz,
    Ruhezeit,
    SmtpKonto,
)

LISTE_STANDARD_LIMIT = 50


def liste(benutzer, limit=LISTE_STANDARD_LIMIT):
    """Neueste Benachrichtigungen mit allen Zustellungen (auch unterdrückte)."""
    return list(
        Benachrichtigung.objects.filter(empfaenger=benutzer)
        .select_related("ereignis")
        .prefetch_related("zustellungen__kanal")[:limit]
    )


def ungelesen(benutzer):
    return Benachrichtigung.objects.filter(empfaenger=benutzer, gelesen_am__isnull=True).count()


def smtp_konto():
    return SmtpKonto.objects.first()


def ruhezeiten(benutzer):
    return list(Ruhezeit.objects.filter(benutzer=benutzer).order_by("id"))


def profil(benutzer):
    return BenachrichtigungsProfil.objects.filter(benutzer=benutzer).first()


def mail_nur_entscheidungen(benutzer):
    p = profil(benutzer)
    return bool(p and p.mail_nur_entscheidungen)


def ungesehene_popups(kind):
    return list(Popup.objects.filter(empfaenger=kind, gesehen_am__isnull=True).order_by("id"))


def kanaele_fuer(rolle):
    """Registrierte und global aktive Kanäle, die für die Rolle gelten."""
    abgeschaltet = set(Kanal.objects.filter(aktiv=False).values_list("slug", flat=True))
    return [k for k in registry.kanaele() if rolle in k.rollen and k.slug not in abgeschaltet]


def typen_fuer(rolle):
    """Aktive Ereignistypen, die einen Empfänger dieser Rolle erreichen können."""
    ziele = {Zielgruppe.BEIDE, Zielgruppe.ELTERN if rolle == Rolle.ELTERN else Zielgruppe.KIND}
    return [t for t in ereignis_selectors.ereignistypen() if t.zielgruppe in ziele]


# Entscheidungen der Eltern laut Ereigniskatalog; Module können zusätzlich
# ``typ_deklarieren(..., entscheidung=True)`` setzen.
ENTSCHEIDUNGS_TYPEN = frozenset(
    {
        "aufgabe.interesse",
        "aufgabe.konflikt",
        "aufgabe.gemeldet",
        "belohnung.antrag",
        "sondertag.wunsch",
        "familienziel.abstimmung_gleichstand",
    }
)


def ist_entscheidung(typ):
    """Müssen die Eltern bei diesem Ereignistyp (``EreignisTyp``) etwas entscheiden?"""
    if typ.slug in ENTSCHEIDUNGS_TYPEN:
        return True
    try:
        return ereignis_registry.typ(typ.slug).entscheidung
    except ereignis_registry.UnbekannterEintrag:
        return False


def wirksame_praeferenz(benutzer, typ, kanal_slug, vorhandene=None):
    """Gilt der Kanal für diesen Benutzer und Ereignistyp (ohne Ruhezeit und Profil)?

    ``vorhandene``: optional ``{(typ_slug, kanal_slug): aktiv}`` (vermeidet Abfragen)."""
    if vorhandene is None:
        vorhandene = praeferenz_zeilen(benutzer)
    explizit = vorhandene.get((typ.slug, kanal_slug))
    return explizit if explizit is not None else kanal_slug in (typ.standard_kanaele or [])


def praeferenz_zeilen(benutzer):
    return {
        (t, k): a
        for t, k, a in Praeferenz.objects.filter(benutzer=benutzer).values_list(
            "ereignistyp_id", "kanal_id", "aktiv"
        )
    }


def praeferenz_matrix(benutzer):
    """Zeilen für die Präferenzen-Seite: je Typ die Zellen aller passenden Kanäle."""
    kanaele = kanaele_fuer(benutzer.rolle)
    zeilen = praeferenz_zeilen(benutzer)
    nur_entscheidungen = mail_nur_entscheidungen(benutzer)
    ergebnis = []
    for typ in typen_fuer(benutzer.rolle):
        zellen = []
        for k in kanaele:
            an = wirksame_praeferenz(benutzer, typ, k.slug, zeilen)
            gesperrt = k.slug == "email" and nur_entscheidungen and not ist_entscheidung(typ)
            zellen.append({"kanal": k, "typ": typ, "aktiv": an, "durch_profil_aus": gesperrt})
        ergebnis.append({"typ": typ, "zellen": zellen})
    return ergebnis, kanaele
