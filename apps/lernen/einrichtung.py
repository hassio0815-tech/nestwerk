"""Schritte "Lernen" im Einrichtungs-Assistenten (Etappe 8).

Vier optionale Schritte, jeder überspringbar ("Später in den Einstellungen"). Sie hängen sich über
``kern.registry`` ein (``einrichtung_registrieren``); ``einrichtung`` fragt nur die Registry.
Jede Funktion ``(request, absenden) -> Kontext | None`` liefert den Kontext zum Anzeigen oder
``None``, wenn gespeichert oder übersprungen wurde. Die Fachlogik steht in
``einrichtung_services``; hier wird nur gelesen und geprüft, was im Formular steht.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.kern.registry import EinrichtungsSchritt, einrichtung_registrieren

from . import einrichtung_services as dienste
from . import selectors
from .models import KiAufgabe, KiTyp

TAGESZIEL_MIN, TAGESZIEL_MAX = 1, 240


def _ueberspringen(request, absenden):
    return absenden and request.POST.get("aktion") == "ueberspringen"


def _zahl(text, minimum, maximum):
    try:
        zahl = int(str(text).strip())
    except ValueError:
        return None
    return zahl if minimum <= zahl <= maximum else None


# --- Grundwerte ---------------------------------------------------------------------------------


def grund(request, absenden):
    if _ueberspringen(request, absenden):
        return None
    fehler = []
    stand = dienste.grundwerte()
    faecher = [(f.schluessel, f.name) for f, _an in stand["faecher"]]
    if absenden:
        p = request.POST
        werte = {
            "faecher": p.getlist("faecher"),
            "tagesziel": p.get("tagesziel", "").strip(),
            "lernpunkte": p.get("lernpunkte") == "1",
            "tutor": p.get("tutor") == "1",
        }
        ziel = _zahl(werte["tagesziel"], TAGESZIEL_MIN, TAGESZIEL_MAX)
        if ziel is None:
            fehler.append(
                gettext("Das Tagesziel muss eine Zahl von %(von)s bis %(bis)s sein.")
                % {"von": TAGESZIEL_MIN, "bis": TAGESZIEL_MAX}
            )
        else:
            try:
                dienste.grundwerte_speichern(
                    faecher=werte["faecher"],
                    tagesziel=ziel,
                    lernpunkte=werte["lernpunkte"],
                    tutor=werte["tutor"],
                )
                return None
            except ValidationError as exc:
                fehler = exc.messages
    else:
        werte = {
            "faecher": [f.schluessel for f, an in stand["faecher"] if an],
            "tagesziel": stand["tagesziel"],
            "lernpunkte": stand["lernpunkte"],
            "tutor": stand["tutor"],
        }
    return {"werte": werte, "faecher": faecher, "fehler": fehler}


# --- Speicher -----------------------------------------------------------------------------------


def speicher(request, absenden):
    if _ueberspringen(request, absenden):
        return None
    fehler = []
    if absenden:
        werte = {
            "modus": request.POST.get("modus", "volume"),
            "pfad": request.POST.get("pfad", "").strip(),
        }
        try:
            dienste.speicher_speichern(modus=werte["modus"], pfad=werte["pfad"])
            return None
        except ValidationError as exc:
            fehler = exc.messages
    else:
        werte = dienste.speicher_werte()
    return {"werte": werte, "fehler": fehler}


# --- Kinder -------------------------------------------------------------------------------------


def _kind_feld(pk, name):
    return f"kind-{pk}-{name}"


def kinder(request, absenden):
    if _ueberspringen(request, absenden):
        return None
    profile = dienste.kinder_profile()
    faecher = [(f.schluessel, f.name) for f in selectors.faecher()]
    zeilen = []
    for profil in profile:
        pk = profil.kind.pk
        if absenden:
            p = request.POST
            werte = {
                "klassenstufe": p.get(_kind_feld(pk, "klasse"), "").strip(),
                "schulform": p.get(_kind_feld(pk, "schulform"), ""),
                "stufen": {k: p.get(_kind_feld(pk, f"stufe-{k}"), "") for k, _n in faecher},
                "sofort": p.get(_kind_feld(pk, "freigabe")) == "sofort",
            }
        else:
            werte = {
                "klassenstufe": profil.klassenstufe or "",
                "schulform": profil.schulform,
                "stufen": {k: profil.stufen.get(k, "") for k, _n in faecher},
                "sofort": profil.sofort,
            }
        zeilen.append(
            {
                "kind": profil.kind,
                "werte": werte,
                "stufen": [(k, n, werte["stufen"][k]) for k, n in faecher],
                "fehler": [],
            }
        )
    if absenden:
        if _kinder_speichern(zeilen):
            return None
    return {"zeilen": zeilen, "stufenwahl": list(dienste.STUFEN.items())}


def _kinder_speichern(zeilen):
    """Prüft zuerst alle Kinder, speichert dann alle; ``True`` = alles gespeichert."""
    for z in zeilen:
        w = z["werte"]
        try:
            dienste.kind_pruefen(
                klassenstufe=w["klassenstufe"], schulform=w["schulform"], stufen=w["stufen"]
            )
        except ValidationError as exc:
            z["fehler"] = exc.messages
    if any(z["fehler"] for z in zeilen):
        return False
    try:
        with transaction.atomic():
            for z in zeilen:
                w = z["werte"]
                dienste.kind_speichern(
                    z["kind"],
                    klassenstufe=w["klassenstufe"],
                    schulform=w["schulform"],
                    stufen=w["stufen"],
                    sofort=w["sofort"],
                )
    except ValidationError as exc:
        for z in zeilen:
            z["fehler"] = exc.messages
        return False
    return True


# --- KI -----------------------------------------------------------------------------------------


def ki(request, absenden):
    aktion = request.POST.get("aktion", "") if absenden else ""
    if aktion == "ueberspringen":
        return None
    fehler = []
    ergebnis = None
    werte = dienste.ki_werte()
    if absenden:
        p = request.POST
        eingabe = {
            "modus": p.get("modus", dienste.KEINE_KI),
            "name": p.get("name", ""),
            "basis_url": p.get("basis_url", ""),
            "modell": p.get("modell", ""),
            "einwilligung": p.get("einwilligung") == "1",
            "aufgaben": p.getlist("aufgaben"),
        }
        try:
            # der Schlüssel geht nur hier durch und wird nie in den Kontext übernommen
            ergebnis = dienste.ki_einrichten(
                **eingabe, api_key=p.get("api_key", ""), testen=aktion == "testen"
            )
            if aktion != "testen":
                return None
            werte = dienste.ki_werte()
        except ValidationError as exc:
            fehler = exc.messages
            werte = {**werte, **eingabe}
    return {
        "werte": werte,
        "typen": [(w, t) for w, t in KiTyp.choices],
        "aufgaben": list(KiAufgabe.choices),
        "fehler": fehler,
        "ergebnis": ergebnis,
        "kein_wert": dienste.KEINE_KI,
    }


# --- Registrierung ------------------------------------------------------------------------------


def einrichtung_registrieren_alle():
    schritte = [
        ("lernen_grund", _("Lernen: Grundwerte"), "grund", grund, dienste.zusammenfassung),
        ("lernen_speicher", _("Lernen: Speicher"), "speicher", speicher, None),
        ("lernen_kinder", _("Lernen: Kinder"), "kinder", kinder, None),
        ("lernen_ki", _("Lernen: KI"), "ki", ki, None),
    ]
    for nr, (schluessel, titel, vorlage, funktion, summe) in enumerate(schritte):
        einrichtung_registrieren(
            EinrichtungsSchritt(
                schluessel=schluessel,
                modul="lernen",
                titel=titel,
                template=f"lernen/einrichtung/{vorlage}.html",
                verarbeiten=funktion,
                zusammenfassung=summe,
                reihenfolge=10 * (nr + 1),
            )
        )
