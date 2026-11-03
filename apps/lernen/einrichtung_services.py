"""Lernen im Einrichtungs-Assistenten (SPEC 21.5, 21.6, 21.8, 21.11, Etappe 8).

Schreibt nur über vorhandene Services: Einstellungen (``kern``), ``ki_services`` für Anbieter,
Verbindungstest und Zuordnung, ``services``/``material_services`` für Lernmappe, Leistungsstufe
und Freigabe. Jede Funktion läuft in einer Transaktion und ist idempotent (erneutes Speichern
legt nichts doppelt an). Alles Familienspezifische kommt von den Eltern; hier steht nichts davon.

API-Schlüssel gehen nur als Argument durch und direkt in ``anbieter_speichern`` (Verschlüsselung);
sie landen weder in Rückgabewerten noch in Meldungen, Audit oder Log.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.kern import audit, einstellungen
from apps.konten import selectors as konten_selectors

from . import ki_selectors, ki_services, selectors, services, speicher
from .ki import KiEinwilligungFehlt
from .ki_texte import fehlertext
from .models import Fach, KiAufgabe, KiTyp, Leistungsstufe, Lernmappe

KEINE_KI = "keine"
# Erlaubte Bezeichnungen der Leistungsstufe; gespeichert wird der Schlüssel (sprachunabhängig)
STUFEN = {
    "Grundniveau": gettext_lazy("Grundniveau"),
    "Erweiterungsniveau": gettext_lazy("Erweiterungsniveau"),
}
KLASSE_MIN, KLASSE_MAX = 1, 13
SCHULFORM_MAX = 60
STANDARD_AUFGABEN = (KiAufgabe.AUSLESEN, KiAufgabe.FRAGEN_ERZEUGEN, KiAufgabe.BEWERTEN)


def _setzen(schluessel, wert_):
    try:
        einstellungen.setzen(schluessel, wert_, akteur=None)
    except einstellungen.EinstellungFehler as exc:
        raise ValidationError(str(exc)) from exc


# --- Grundwerte ---------------------------------------------------------------------------------


def grundwerte():
    """Aktueller Stand für das Formular (Fächer als Liste ``(Fach, aktiv)``)."""
    return {
        "faecher": [(f, f.aktiv) for f in selectors.faecher(nur_aktive=False)],
        "tagesziel": einstellungen.wert("lernen.tagesziel_minuten"),
        "lernpunkte": einstellungen.wert("lernen.lernpunkte_aktiv"),
        "tutor": einstellungen.wert("lernen.tutor_aktiv"),
    }


def grundwerte_speichern(*, faecher, tagesziel, lernpunkte, tutor):
    """Aktiviert genau die gewählten Fächer und setzt Tagesziel, Lernpunkte und Tutor."""
    schluessel = set(faecher)
    vorhandene = set(Fach.objects.values_list("schluessel", flat=True))
    if not schluessel or not schluessel <= vorhandene:
        raise ValidationError(_("Bitte mindestens ein Fach wählen."))
    with transaction.atomic():
        Fach.objects.filter(schluessel__in=schluessel).update(aktiv=True)
        Fach.objects.exclude(schluessel__in=schluessel).update(aktiv=False)
        _setzen("lernen.tagesziel_minuten", tagesziel)
        _setzen("lernen.lernpunkte_aktiv", bool(lernpunkte))
        _setzen("lernen.tutor_aktiv", bool(tutor))
        audit.protokollieren(
            "lernen.einrichtung_grundwerte",
            akteur=None,
            details={
                "faecher": len(schluessel),
                "lernpunkte": bool(lernpunkte),
                "tutor": bool(tutor),
            },
        )


# --- Speicher -----------------------------------------------------------------------------------


def speicher_werte():
    pfad = speicher.konfigurierter_pfad()
    return {"modus": "pfad" if pfad else "volume", "pfad": pfad}


def speicher_speichern(*, modus, pfad=""):
    """``volume`` = Standard (Docker-Volume). ``pfad`` = gemounteter Ordner: vorhanden,
    beschreibbar und kein Systemordner, sonst Fehler und nichts wird gespeichert."""
    if modus == "volume":
        ziel = ""
    elif modus == "pfad":
        try:
            ziel = str(speicher.pfad_pruefen(pfad))
        except speicher.PfadFehler as exc:
            raise ValidationError(str(exc)) from None
    else:
        raise ValidationError(_("Bitte eine Auswahl treffen."))
    with transaction.atomic():
        _setzen("lernen.speicher_pfad", ziel)
        audit.protokollieren(
            "lernen.einrichtung_speicher", akteur=None, details={"gemountet": bool(ziel)}
        )


# --- Kinder: Klassenstufe, Schulform, Leistungsstufen, Freigabe ---------------------------------


@dataclass
class KindProfil:
    kind: object
    klassenstufe: int | None
    schulform: str
    stufen: dict  # {Fach-Schlüssel: Stufe}
    sofort: bool


def kinder_profile():
    """Je Kind der gespeicherte Stand (leer, solange noch nichts eingetragen ist)."""
    faecher = list(selectors.faecher())
    ergebnis = []
    for kind in konten_selectors.aktive_kinder().order_by("anzeigename"):
        mappe = Lernmappe.objects.filter(kind=kind).first()
        eintraege = {s.fach_id: s for s in Leistungsstufe.objects.filter(kind=kind)}
        klassen = [e.klassenstufe for e in eintraege.values() if e.klassenstufe is not None]
        ergebnis.append(
            KindProfil(
                kind=kind,
                klassenstufe=klassen[0] if klassen else None,
                schulform=mappe.schulform if mappe else "",
                stufen={f.schluessel: eintraege[f.pk].stufe for f in faecher if f.pk in eintraege},
                sofort=services.fragen_sofort_nutzbar(kind),
            )
        )
    return ergebnis


def kind_pruefen(*, klassenstufe, schulform, stufen):
    """Bereinigt die Eingaben eines Kindes. ``klassenstufe`` ist Text oder Zahl oder leer.
    Gibt ``(klassenstufe, schulform, stufen)`` zurück oder wirft ``ValidationError``."""
    fehler = []
    klasse = None
    if str(klassenstufe or "").strip():
        try:
            klasse = int(str(klassenstufe).strip())
        except ValueError:
            klasse = None
        if klasse is None or not KLASSE_MIN <= klasse <= KLASSE_MAX:
            fehler.append(
                _("Die Klassenstufe muss eine Zahl von %(von)s bis %(bis)s sein.")
                % {"von": KLASSE_MIN, "bis": KLASSE_MAX}
            )
    schulform = " ".join((schulform or "").split())
    if len(schulform) > SCHULFORM_MAX:
        fehler.append(_("Die Schulform ist zu lang."))
    sauber = {}
    for fach, stufe in stufen.items():
        if stufe and stufe not in STUFEN:
            fehler.append(_("Unbekannte Leistungsstufe."))
        sauber[fach] = stufe or ""
    if fehler:
        raise ValidationError(fehler)
    return klasse, schulform, sauber


def kind_speichern(kind, *, klassenstufe, schulform, stufen, sofort):
    """Legt Lernmappe und je aktivem Fach eine Leistungsstufe an (oder aktualisiert sie).
    Ohne Stufe und ohne Klassenstufe entsteht kein Eintrag (ein alter wird entfernt)."""
    from . import material_services

    if getattr(kind, "rolle", None) != "kind":
        raise ValidationError(_("Das ist kein Kind."))
    klasse, schulform, stufen = kind_pruefen(
        klassenstufe=klassenstufe, schulform=schulform, stufen=stufen
    )
    try:
        with transaction.atomic():
            mappe = services.lernmappe_sicherstellen(kind)
            mappe.schulform = schulform
            mappe.save(update_fields=["schulform"])
            material_services.sofort_nutzbar_setzen(kind, sofort)
            for fach in selectors.faecher():
                stufe = stufen.get(fach.schluessel, "")
                if stufe or klasse is not None:
                    services.leistungsstufe_setzen(kind, fach, stufe, klasse)
                else:
                    Leistungsstufe.objects.filter(kind=kind, fach=fach).delete()
            audit.protokollieren(
                "lernen.einrichtung_kind",
                akteur=None,
                kind=kind,
                details={"stufen": sum(1 for s in stufen.values() if s), "sofort": bool(sofort)},
            )
    except OSError:
        raise ValidationError(
            _("Der Ordner für die Lernmappe konnte nicht angelegt werden. Speicherort prüfen.")
        ) from None


# --- KI -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class KiErgebnis:
    anbieter: object
    test: object  # ``ki_services.TestErgebnis`` oder ``None``
    test_text: str = ""


def _anbieter():
    """Der eine Anbieter, den der Assistent verwaltet (der erste vorhandene)."""
    return ki_selectors.anbieter_liste().first()


def ki_werte():
    """Stand für das Formular. Der Schlüssel ist nie dabei, nur ob einer gespeichert ist."""
    anbieter = _anbieter()
    zugeordnet = ki_selectors.zuordnungen()
    if anbieter is None:
        aufgaben = [a.value for a in STANDARD_AUFGABEN]
        if einstellungen.wert("lernen.tutor_aktiv"):
            aufgaben.append(KiAufgabe.TUTOR.value)
        return {
            "modus": KEINE_KI,
            "name": "",
            "basis_url": "",
            "modell": "",
            "aufgaben": aufgaben,
            "hat_schluessel": False,
            "einwilligung": False,
            "ist_cloud": False,
        }
    return {
        "modus": anbieter.typ if anbieter.aktiv else KEINE_KI,
        "name": anbieter.name,
        "basis_url": anbieter.basis_url,
        "modell": anbieter.modell,
        "aufgaben": [a for a, p in zugeordnet.items() if p is not None and p.pk == anbieter.pk],
        "hat_schluessel": anbieter.hat_schluessel,
        "einwilligung": anbieter.einwilligung_am is not None,
        "ist_cloud": anbieter.ist_cloud,
    }


def ki_abschalten():
    """ "Keine KI jetzt": Zuordnungen des Anbieters lösen und ihn ausschalten."""
    anbieter = _anbieter()
    if anbieter is None:
        return
    with transaction.atomic():
        for aufgabe, zugeordnet in ki_selectors.zuordnungen().items():
            if zugeordnet is not None and zugeordnet.pk == anbieter.pk:
                ki_services.zuordnung_setzen(aufgabe, None, akteur=None)
        if anbieter.aktiv:
            ki_services.anbieter_deaktivieren(anbieter, akteur=None)


def ki_einrichten(
    *,
    modus,
    name="",
    basis_url="",
    modell="",
    api_key="",
    einwilligung=False,
    aufgaben=(),
    testen=False,
):
    """Speichert den Anbieter, schaltet ihn ein (Cloud nur mit Einwilligung) und ordnet die
    gewählten Aufgaben zu. Alles oder nichts; der Verbindungstest läuft danach und ändert nichts
    an dem, was gespeichert wurde. Fehler: ``ValidationError``."""
    if modus == KEINE_KI:
        ki_abschalten()
        return KiErgebnis(None, None)
    if modus not in KiTyp.values:
        raise ValidationError(_("Bitte eine Auswahl treffen."))
    gewaehlt = {a for a in aufgaben if a in KiAufgabe.values}
    with transaction.atomic():
        anbieter = ki_services.anbieter_speichern(
            anbieter=_anbieter(),
            name=name,
            typ=modus,
            basis_url=basis_url,
            modell=modell,
            api_key=api_key,
            akteur=None,
        )
        try:
            ki_services.anbieter_aktivieren(anbieter, einwilligung=einwilligung, akteur=None)
        except KiEinwilligungFehlt:
            raise ValidationError(
                _("Für einen Cloud-Anbieter braucht es zuerst eure Einwilligung (Häkchen).")
            ) from None
        for aufgabe, zugeordnet in ki_selectors.zuordnungen().items():
            if aufgabe in gewaehlt:
                ki_services.zuordnung_setzen(aufgabe, anbieter, akteur=None)
            elif zugeordnet is not None and zugeordnet.pk == anbieter.pk:
                ki_services.zuordnung_setzen(aufgabe, None, akteur=None)
    test = ki_services.verbindung_testen(anbieter) if testen else None
    text = ""
    if test is not None:
        text = _("Verbindung steht.") if test.ok else fehlertext(test.art)
    return KiErgebnis(anbieter, test, str(text))


# --- Zusammenfassung ----------------------------------------------------------------------------


def _ja_nein(wert_):
    return _("an") if wert_ else _("aus")


def zusammenfassung():
    """Was der Assistent für ``lernen`` eingestellt hat und was später nachholbar ist."""
    grund = grundwerte()
    aktiv = [f.name for f, an in grund["faecher"] if an]
    zeilen = [
        (_("Fächer"), ", ".join(aktiv) or _("keine")),
        (_("Tagesziel"), _("%(n)s Minuten") % {"n": grund["tagesziel"]}),
        (_("Lernpunkte"), _ja_nein(grund["lernpunkte"])),
        (_("Tutor"), _ja_nein(grund["tutor"])),
    ]
    pfad = speicher.konfigurierter_pfad()
    zeilen.append(
        (_("Speicherort"), pfad if pfad else _("Docker-Volume (Standard)")),
    )
    ki = ki_werte()
    if ki["modus"] == KEINE_KI:
        zeilen.append((_("KI"), _("aus (keine KI eingerichtet)")))
    else:
        namen = dict(KiAufgabe.choices)
        zeilen.append(
            (
                _("KI"),
                _("%(name)s (%(art)s), für: %(aufgaben)s")
                % {
                    "name": ki["name"],
                    "art": dict(KiTyp.choices)[ki["modus"]],
                    "aufgaben": ", ".join(str(namen[a]) for a in ki["aufgaben"]) or _("nichts"),
                },
            )
        )
    fachnamen = {f.schluessel: f.name for f, _an in grund["faecher"]}
    for p in kinder_profile():
        teile = []
        if p.klassenstufe:
            teile.append(_("Klasse %(n)s") % {"n": p.klassenstufe})
        if p.schulform:
            teile.append(p.schulform)
        teile += [
            f"{fachnamen.get(fach, fach)}: {STUFEN.get(s, s)}"
            for fach, s in sorted(p.stufen.items())
            if s
        ]
        teile.append(_("Fragen aus Uploads sofort nutzbar") if p.sofort else _("Eltern geben frei"))
        zeilen.append((p.kind.anzeigename, ", ".join(str(t) for t in teile)))
    return {
        "titel": _("Lernen"),
        "zeilen": zeilen,
        "spaeter": [
            (_("KI-Anbieter, Schlüssel und Zuordnung"), reverse("lernen:ki")),
            (_("Tutor an- und ausschalten"), reverse("lernen:eltern_tutor")),
            (_("Freigabe der Fragen pro Kind"), reverse("lernen:eltern_material")),
            (_("Lernen: Übersicht für die Eltern"), reverse("lernen:eltern")),
        ],
    }
