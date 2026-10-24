"""Sondertag Ende-zu-Ende (AP27): echte Metriken aus avatar und spielregeln -> Meilenstein ->
Anspruch. Liegt außerhalb von ``apps`` (Schichtenregel: sondertag kennt avatar nicht)."""

from datetime import timedelta

from django.db import transaction

from apps.kern import zeit
from apps.sondertag import selectors
from apps.sondertag.meilensteine_start import rang_schluessel
from apps.sondertag.models import SondertagAnspruch, Status
from apps.sondertag.tests.conftest import (  # noqa: F401  (Fixtures)
    GO_LIVE,
    anna,
    mama,
    startwerte,
    uhr,
)
from apps.spielregeln import services as spielregeln


def tag(n):
    return GO_LIVE + timedelta(days=n)


def pruefen(kind):
    with transaction.atomic():
        return spielregeln.abzeichen_pruefen(kind)


def test_echte_metriken_ausbaustufe_6_in_uncommon(anna, mama, uhr):  # noqa: F811
    import itertools

    from apps.avatar import services as avatar_services
    from apps.avatar.models import ModBesitz, ModDefinition
    from apps.punkte import services as punkte
    from apps.punkte.models import Art
    from apps.spielregeln.models import Rang, RangAufstieg

    nr = itertools.count()
    uhr.stellen(tag(14))
    avatar_services.avatar_waehlen(anna, "ritter", {})
    RangAufstieg.objects.create(
        kind=anna,
        rang=Rang.objects.get(stufe=2),
        xp_bei_aufstieg=0,
        aktive_wochen_bei_aufstieg=0,
        schwelle_bei_aufstieg=0,
    )
    mods_ = ModDefinition.objects.filter(thema__schluessel="ritter", seltenheit=2)
    for i, m in enumerate(mods_):
        buchung = punkte.buchen(
            anna, Art.AUFGABE, 1, schluessel=f"e2e:{next(nr)}", quelle_modul="t", von=None
        )
        ModBesitz.objects.create(
            kind=anna,
            mod=m,
            preis_bezahlt=0,
            bauzeit_stunden=0,
            buchung=buchung,
            fertig_geplant_am=zeit.jetzt(),
            fertig_am=zeit.jetzt(),
            status="fertig",
            zaehlt_ab_iso_jahr=2026,
            zaehlt_ab_iso_woche=40 + i,  # bis KW 45 = heute
        )
        if i == 4:
            assert pruefen(anna).erreicht == []  # 5 von 6
    assert [f.regel.schluessel for f in pruefen(anna).erreicht] == [rang_schluessel(2)]
    a = SondertagAnspruch.objects.get(kind=anna)
    assert a.status == Status.VERDIENT and a.einloesbar_ab == tag(14)
    assert selectors.fortschritt(anna).art == "einloesbar"
