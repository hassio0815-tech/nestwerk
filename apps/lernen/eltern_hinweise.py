"""Meldungen an die Eltern bei Ausnahmen (Etappe 13, E-1): wenig und ruhig.

Eltern sollen nicht ständig nachsehen müssen, aber auch nicht zugeschüttet werden. Darum:

- Jede Meldung ist ein Ereignis mit festem Schlüssel: dasselbe Ereignis entsteht im gleichen
  Zeitraum nie zweimal (Dedupe über ``Ereignis.schluessel``, auch bei wiederholtem Joblauf).
- Der Ton ist ein Angebot für ein Gespräch (Texte X1 bis X4), nie ein Vorwurf.
- Im Zweifel keine Meldung: kein Hinweis in Pause und Ferien, nicht für Kinder, die nie geübt
  haben, nicht für inaktive Kinder.
- Ein Schalter (``lernen.eltern_hinweise_aktiv``) schaltet alle Ausnahme-Meldungen ab. Kanal und
  Empfänger wählt jedes Elternteil selbst bei den Benachrichtigungen.

Die Aufrufe laufen im Tagesjob ``lernen_eltern_hinweise``; nur die Tutor-Markierung geschieht
sofort, in der Transaktion der Tutor-Nachricht.
"""

import hashlib
from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.utils.translation import gettext_noop, ngettext

from apps.ereignisse import services as ereignisse
from apps.ereignisse.models import Ereignis
from apps.kern import zeit
from apps.kern.einstellungen import wert
from apps.konten import selectors as konten

from . import events, material_selectors, plan_selectors, tagesziel
from .mathe import registry as mathe_registry
from .mathe.hilfe import karten
from .models import Ergebnis, Lerntag, Markierung, Versuch

STILL_TAGE = 3  # so viele volle Tage ohne Mindesttag
AKTIV_FENSTER_TAGE = 21  # wer länger nicht geübt hat, gilt als nicht mehr dabei: keine Meldung
FEHLER_FENSTER_TAGE = 7
PRUEFUNG_TAGE = 3
PRUEFUNG_PROZENT = 50
MATERIAL_EINZAHL = "%(n)s neues Material von %(kind)s wartet auf dein OK."
MATERIAL_MEHRZAHL = "%(n)s neue Materialien von %(kind)s warten auf dein OK."
GEMELDETE_MARKIERUNGEN = (Markierung.ROLLENWECHSEL, Markierung.LECK)


def _msgids_fuer_makemessages(n):
    """Nur damit ``makemessages`` das Paar als Mehrzahl findet; die Texte selbst stehen in
    ``MATERIAL_EINZAHL``/``MATERIAL_MEHRZAHL`` und werden beim Zustellen übersetzt (X1)."""
    return ngettext(
        "%(n)s neues Material von %(kind)s wartet auf dein OK.",
        "%(n)s neue Materialien von %(kind)s warten auf dein OK.",
        n,
    )


def _aktiv():
    return bool(wert("lernen.eltern_hinweise_aktiv"))


def _woche(tag):
    jahr, woche, _ = tag.isocalendar()
    return f"{jahr}-W{woche:02d}"


@transaction.atomic
def _melden(typ, kind, daten, schluessel):
    """Veröffentlicht das Ereignis, außer es gibt es schon. Gibt 1 (neu) oder 0 zurück."""
    if Ereignis.objects.filter(schluessel=schluessel).exists():
        return 0
    ereignisse.veroeffentlichen(typ, kind=kind, daten=daten, schluessel=schluessel)
    return 1


# --- X1: Material wartet ------------------------------------------------------------------------


def material_wartet(heute=None):
    """Je Kind eine Meldung, solange sich der Stand der wartenden Materialien ändert. Derselbe
    Stand wird nicht erneut gemeldet; kommt etwas dazu, gibt es eine neue Zahl."""
    if not _aktiv():
        return 0
    kinder = {k.pk: k for k in konten.aktive_kinder()}
    wartend = {}
    for pk, kind_id in material_selectors.warten_auf_eltern().values_list("pk", "kind_id"):
        if kind_id in kinder:
            wartend.setdefault(kind_id, []).append(pk)
    neu = 0
    for kind_id, ids in sorted(wartend.items()):
        kind = kinder[kind_id]
        stand = hashlib.sha1(",".join(map(str, sorted(ids))).encode()).hexdigest()[:12]
        neu += _melden(
            events.MATERIAL_WARTET,
            kind,
            {
                "n": len(ids),
                "hinweis_msgid": MATERIAL_EINZAHL,
                "hinweis_msgid_plural": MATERIAL_MEHRZAHL,
                "hinweis_parameter": {"n": len(ids), "kind": kind.anzeigename},
            },
            f"{events.MATERIAL_WARTET}:{kind.pk}:{stand}",
        )
    return neu


# --- X2: Kind still -----------------------------------------------------------------------------


def kind_still(heute=None):
    """Kind hat seit drei vollen Tagen den Mindesttag nicht erreicht (aber vorher geübt).
    Nie in Pause oder Ferien. Höchstens einmal je Woche und Kind."""
    if not _aktiv():
        return 0
    heute = heute or zeit.heute()
    if wert("lernen.ferien_schalter"):
        return 0
    neu = 0
    for kind in konten.aktive_kinder():
        letzter = (
            Lerntag.objects.filter(kind=kind, mindesttag=True, datum__lte=heute)
            .order_by("-datum")
            .values_list("datum", flat=True)
            .first()
        )
        if letzter is None or letzter > heute - timedelta(days=STILL_TAGE + 1):
            continue
        if letzter < heute - timedelta(days=AKTIV_FENSTER_TAGE):
            continue
        if tagesziel.pausentage(kind, heute - timedelta(days=STILL_TAGE), heute):
            continue
        neu += _melden(
            events.KIND_STILL,
            kind,
            {"tage": STILL_TAGE},
            f"{events.KIND_STILL}:{kind.pk}:{_woche(heute)}",
        )
    return neu


# --- X3: Fehlerhäufung --------------------------------------------------------------------------


def _haeufigste_rechenart(kind, heute):
    """``(generator, anzahl)`` der Rechenart mit den meisten Fehlversuchen in den letzten sieben
    Tagen, ab der Schwelle der Wochenansicht und nur mit Erklärkarte; sonst ``None``."""
    von = zeit.tag_beginn(heute - timedelta(days=FEHLER_FENSTER_TAGE - 1))
    bis = zeit.tag_beginn(heute + timedelta(days=1))
    zaehler = Counter(
        Versuch.objects.filter(
            sitzung__kind=kind,
            ergebnis=Ergebnis.NOCH_NICHT,
            erstellt__gte=von,
            erstellt__lt=bis,
            frage__isnull=False,
        )
        .exclude(frage__generator="")
        .values_list("frage__generator", flat=True)
    )
    mindest = wert("lernen.woche_schwaeche_fehler")
    kandidaten = [
        (g, n)
        for g, n in zaehler.items()
        if n >= mindest and karten.karte_fuer(g) is not None and g in mathe_registry.alle()
    ]
    kandidaten.sort(key=lambda x: (-x[1], x[0]))
    return kandidaten[0] if kandidaten else None


def fehlerhaeufung(heute=None):
    """Eine Rechenart war diese Woche öfter falsch: Hinweis mit passender Erklärkarte.
    Höchstens einmal je Woche und Kind."""
    if not _aktiv():
        return 0
    heute = heute or zeit.heute()
    neu = 0
    for kind in konten.aktive_kinder():
        treffer = _haeufigste_rechenart(kind, heute)
        if treffer is None:
            continue
        generator, anzahl = treffer
        neu += _melden(
            events.FEHLERHAEUFUNG,
            kind,
            {
                "generator": generator,
                "rechenart": mathe_registry.holen(generator).name,
                "karte": karten.karte_fuer(generator).titel,
                "anzahl": anzahl,
            },
            f"{events.FEHLERHAEUFUNG}:{kind.pk}:{_woche(heute)}",
        )
    return neu


# --- Prüfung rüstet -----------------------------------------------------------------------------


def pruefung_ruestet(heute=None):
    """Prüfung in höchstens drei Tagen, der Plan ist zu weniger als der Hälfte geschafft.
    Einmal je Prüfung. Prüfungen ohne Plan stehen im Wochenbild, nicht hier."""
    if not _aktiv():
        return 0
    heute = heute or zeit.heute()
    neu = 0
    for kind in konten.aktive_kinder():
        kommende = plan_selectors.aktive_pruefungen(kind).filter(
            termin__gt=heute, termin__lte=heute + timedelta(days=PRUEFUNG_TAGE), plan_ok=True
        )
        for p in kommende:
            prozent = plan_selectors.fortschritt(p).prozent
            if prozent >= PRUEFUNG_PROZENT:
                continue
            neu += _melden(
                events.PRUEFUNG_RUESTET,
                kind,
                {"pruefung": p.pk, "titel": p.titel, "prozent": prozent},
                f"{events.PRUEFUNG_RUESTET}:{p.pk}",
            )
    return neu


# --- Tagesjob -----------------------------------------------------------------------------------


def hinweise_pruefen(heute=None):
    """Alle Tagesprüfungen; gibt die Zahl neuer Meldungen zurück."""
    heute = heute or zeit.heute()
    return sum(f(heute) for f in (material_wartet, kind_still, fehlerhaeufung, pruefung_ruestet))


# --- X4: Tutor-Markierung (sofort) --------------------------------------------------------------

_TUTOR_HINWEIS = {
    Markierung.ROLLENWECHSEL: gettext_noop(
        "Im Tutor-Gespräch von %(kind)s wurde ein Rollenwechsel erkannt."
    ),
    Markierung.LECK: gettext_noop(
        "Im Tutor-Gespräch von %(kind)s wurde eine Antwort zurückgehalten, "
        "weil sie die Lösung verraten könnte."
    ),
}


def tutor_markierung_melden(gespraech, markierung):
    """Rollenwechsel oder zurückgehaltene Antwort gehen sofort an die Eltern. Je Gespräch und Art
    nur einmal. Muss in einer Transaktion laufen (Teil der Tutor-Nachricht)."""
    if markierung not in GEMELDETE_MARKIERUNGEN or not _aktiv():
        return 0
    if Ereignis.objects.filter(
        schluessel=f"{events.TUTOR_MARKIERUNG}:{gespraech.pk}:{markierung}"
    ).exists():
        return 0
    kind = gespraech.kind
    ereignisse.veroeffentlichen(
        events.TUTOR_MARKIERUNG,
        kind=kind,
        daten={
            "gespraech": gespraech.pk,
            "markierung": str(markierung),
            "hinweis_msgid": _TUTOR_HINWEIS[markierung],
            "hinweis_parameter": {"kind": kind.anzeigename},
        },
        schluessel=f"{events.TUTOR_MARKIERUNG}:{gespraech.pk}:{markierung}",
    )
    return 1
