"""Gesamt-Szenario über 52 Wochen und mehrere App-Jahre quer durch alle Module (Review AP31).

Drei Kinder mit unterschiedlichem Fleiß (Startwerte, Entscheidung 14: Planung 150–200 P/Woche),
Pausen (Kind, Familie), faule Wochen, Korrekturen, späte Bestätigungen, Mod-Käufe mit Zeitbremse,
Rangaufstiege, Abzeichen, Familienziele, Held der Woche, Sondertage. Invarianten:

- Sondertage: höchstens 2 je App-Jahr, mindestens 150 Tage Abstand (je Kind),
- Salden = Ledger, Guthaben nie negativ, jeder Mod-Kauf genau eine Buchung, Punkte je Instanz
  genau einmal,
- keine Doppelverleihungen (Abzeichen, Ränge, Meilensteine, Ansprüche),
- Neuberechnung == gespeicherter Stand,
- alle Jobs idempotent bei Doppellauf (je Woche geprüft).

``NESTWERK_KALIBRIERUNG=<datei>`` schreibt die Kalibrierungstabelle (Markdown) für das Review.
"""

import os
from collections import Counter
from datetime import timedelta

import pytest
from django.db.models import Count, Sum

from apps.kern import zeit
from apps.spielregeln import services as spielregeln

from .simulation import Profil, Simulation

pytestmark = pytest.mark.django_db

MO, DI, MI, DO, FR, SA, SO = range(7)


def _sondertage_pruefen(prot, go_live):
    for name, k in prot.kinder.items():
        daten = sorted(k.sondertag_angenommen)
        for a, b in zip(daten, daten[1:], strict=False):
            assert (b - a).days >= 150, (name, a, b)
        jahre = Counter(zeit.app_jahr(d, go_live=go_live).nummer for d in daten)
        assert all(n <= 2 for n in jahre.values()), (name, jahre)


def _ledger_pruefen(kinder):
    from apps.aufgaben.models import AufgabenInstanz
    from apps.avatar.models import ModBesitz
    from apps.punkte import selectors as punkte
    from apps.punkte.models import Buchung

    for kind in kinder:
        summe = Buchung.objects.filter(kind=kind).aggregate(
            g=Sum("guthaben_delta"), x=Sum("xp_delta")
        )
        salden = punkte.salden(kind)
        assert (salden.guthaben, salden.xp) == (summe["g"], summe["x"])
        assert salden.guthaben >= 0 and salden.xp >= 0
        # XP sinkt nie durch Ausgaben: nur Aufgaben/Bonus/Korrektur bewegen XP
        assert not Buchung.objects.filter(kind=kind, art="modkauf").exclude(xp_delta=0).exists()
        kaeufe = ModBesitz.objects.filter(kind=kind)
        assert kaeufe.count() == Buchung.objects.filter(kind=kind, art="modkauf").count()
        bezahlt = kaeufe.aggregate(s=Sum("preis_bezahlt"))["s"] or 0
        abgebucht = Buchung.objects.filter(kind=kind, art="modkauf").aggregate(
            s=Sum("guthaben_delta")
        )["s"]
        assert bezahlt == -(abgebucht or 0)
        bestaetigt = AufgabenInstanz.objects.filter(kind=kind, status="bestaetigt").count()
        basis = Buchung.objects.filter(kind=kind, art="aufgabe", storno_von__isnull=True)
        assert basis.filter(xp_delta__gt=0).count() >= bestaetigt


def _keine_doppelten():
    from apps.sondertag.models import SondertagAnspruch
    from apps.spielregeln.models import AbzeichenVerleihung, MeilensteinErreicht, RangAufstieg

    for modell, felder in (
        (AbzeichenVerleihung, ("kind", "abzeichen", "bereich")),
        (RangAufstieg, ("kind", "rang")),
        (MeilensteinErreicht, ("kind", "regel", "bereich")),
    ):
        doppelt = modell.objects.values(*felder).annotate(n=Count("id")).filter(n__gt=1)
        assert not doppelt.exists(), modell
    assert not (
        SondertagAnspruch.objects.exclude(meilenstein__isnull=True)
        .values("meilenstein")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .exists()
    )


def _kalibrierung_schreiben(prot, titel):
    ziel = os.environ.get("NESTWERK_KALIBRIERUNG")
    if not ziel:
        return
    zeilen = [
        f"### {titel}",
        "",
        "| Kind | Soll P/Woche | Ø XP/Woche | Rang 2 | Rang 3 | Rang 4 | Rang 5 | Rang 6 |"
        " Sondertage verdient (Woche) | angenommen (Woche) | je App-Jahr |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, k in prot.kinder.items():
        soll = prot.soll.get(name, "")
        avg = round(sum(k.xp_woche) / len(k.xp_woche)) if k.xp_woche else 0
        raenge = [str(k.raenge.get(s, "–")) for s in range(2, 7)]
        angenommen = [(d - prot.go_live).days // 7 + 1 for d in sorted(k.sondertag_angenommen)]
        jahre = Counter(
            zeit.app_jahr(d, go_live=prot.go_live).nummer for d in k.sondertag_angenommen
        )
        zeilen.append(
            f"| {name} | {soll} | {avg} | "
            + " | ".join(raenge)
            + f" | {', '.join(map(str, k.sondertag_verdient)) or '–'}"
            f" | {', '.join(map(str, angenommen)) or '–'}"
            f" | {', '.join(f'J{j}: {n}' for j, n in sorted(jahre.items())) or '–'} |"
        )
    zeilen += [
        "",
        f"Familienziele erreicht: {prot.familienziele}, Großziele: {prot.grossziele}, "
        f"Held-der-Woche-Titel: {prot.helden}.",
        "",
    ]
    with open(ziel, "a", encoding="utf-8") as datei:
        datei.write("\n".join(zeilen) + "\n")


def _gesamt_pruefen(sim, prot):
    assert prot.idempotenz_fehler == []
    _sondertage_pruefen(prot, sim.go_live)
    _ledger_pruefen(list(sim.kinder))
    _keine_doppelten()
    assert spielregeln.neu_berechnen() == []


def test_52_wochen_drei_kinder_alle_module(uhr, mama, anna, ben):
    from apps.konten import services as konten
    from apps.konten.tests.conftest import PIN
    from apps.spielregeln.tests.conftest import GO_LIVE

    carl = konten.kind_anlegen("Carl", PIN)
    profile = {
        anna: Profil("Anna (fleißig)", 50, (MO, MI, FR, SA)),  # 200 P
        ben: Profil(
            "Ben (mittel, Eltern-Freigabe So)",
            35,
            (DI, MI, DO, FR, SO),
            eltern_freigabe_sonntag=True,
            korrekturen=(100, 200),
        ),  # 175 P
        carl: Profil(
            "Carl (wechselhaft)",
            50,
            (MO, MI, SA),
            thema="pirat",
            pausen=((70, 83),),
            faul=(20, 21, 35),
            korrekturen=(150,),
        ),  # 150 P
    }
    sim = Simulation(uhr, mama, profile, GO_LIVE)
    sim.familien_pausen = ((210, 216),)  # Woche 31: ganze Familie im Urlaub (neutral)
    prot = sim.laufen(52)
    prot.soll = {p.name: p.soll_woche for p in profile.values()}
    _gesamt_pruefen(sim, prot)

    a = prot.kinder["Anna (fleißig)"]
    assert a.raenge.get(2) and a.raenge.get(3)  # Planungsziel: Rang 2 und 3 im ersten Jahr
    assert len(a.sondertag_angenommen) == 2
    assert prot.familienziele > 0 and prot.helden > 0
    assert prot.kinder["Carl (wechselhaft)"].raenge.get(2)
    _kalibrierung_schreiben(prot, "52 Wochen, drei Kinder (Startwerte)")


@pytest.mark.parametrize("punkte_je_woche", [150])  # Untergrenze der Planung (E14)
def test_mehrjahres_lauf_grenzen_bleiben(uhr, mama, anna, punkte_je_woche):
    """Drei App-Jahre (156 Wochen), ein Kind mit Planwert: God Mode wird erreicht, die Grenzen
    halten über App-Jahr-Wechsel hinweg."""
    from apps.spielregeln.tests.conftest import GO_LIVE

    profil = Profil(f"{punkte_je_woche} P/Woche", punkte_je_woche // 2, (MI, SA))
    sim = Simulation(uhr, mama, {anna: profil}, GO_LIVE)
    sim.sparsam = True
    prot = sim.laufen(156)
    prot.soll = {profil.name: profil.soll_woche}
    _gesamt_pruefen(sim, prot)
    k = prot.kinder[profil.name]
    assert 6 in k.raenge  # God Mode in drei Jahren
    ende = GO_LIVE + timedelta(days=156 * 7)
    assert all(d < ende for d in k.sondertag_angenommen)
    _kalibrierung_schreiben(prot, f"156 Wochen, ein Kind, {punkte_je_woche} P/Woche")
