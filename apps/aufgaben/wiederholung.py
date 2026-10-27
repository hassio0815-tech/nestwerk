"""Wiederholungs- und Zeitplanmodell einer Aufgabe (nur Stammdaten + Validierung).

Reine Python-Logik ohne Datenbankzugriff. AP11 (Instanz-Erzeugung) liest den Plan über
``Aufgabe.plan`` bzw. ``Plan.aus_json`` (Vorlagen) und berechnet daraus die Fälligkeiten.

Bedeutung der Felder:
- ``art``: einmalig (genau ein Termin am ``start_datum``), woechentlich (an den Wochentagen),
  intervall (alle ``intervall_tage`` Tage ab ``start_datum``).
- ``wochentage``: Bitmaske, Bit 0 = Montag ... Bit 6 = Sonntag.
- Zeitfenster am Fälligkeitstag: ``fenster_von`` (optional), ``fenster_bis`` (Frist). Ist
  ``fenster_bis`` gesetzt, ist die Aufgabe zeitgebunden. ``fenster_tage`` verlängert das
  Fensterende um ganze Tage (Mi 18:00 bis Do 07:00 = von 18:00, bis 07:00, Tage 1).
- Limit (K10): höchstens ``limit_anzahl`` Bestätigungen je Kind und Aufgabe pro ``limit_zeitraum``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext, pgettext_lazy

EINMALIG = "einmalig"
WOECHENTLICH = "woechentlich"
INTERVALL = "intervall"
ARTEN = (
    (EINMALIG, gettext_lazy("Einmalig")),
    (WOECHENTLICH, gettext_lazy("Wöchentlich an bestimmten Wochentagen")),
    (INTERVALL, gettext_lazy("Alle paar Tage (Intervall)")),
)
ZEITRAEUME = (
    ("tag", gettext_lazy("Tag")),
    ("woche", gettext_lazy("Woche")),
    ("monat", gettext_lazy("Monat")),
)
ZEITRAUM_WOERTER = {
    "tag": gettext_lazy("Tag"),
    "woche": gettext_lazy("Woche"),
    "monat": gettext_lazy("Monat"),
}

WOCHENTAGE = (
    (0, pgettext_lazy("Wochentag kurz", "Mo"), gettext_lazy("Montag")),
    (1, pgettext_lazy("Wochentag kurz", "Di"), gettext_lazy("Dienstag")),
    (2, pgettext_lazy("Wochentag kurz", "Mi"), gettext_lazy("Mittwoch")),
    (3, pgettext_lazy("Wochentag kurz", "Do"), gettext_lazy("Donnerstag")),
    (4, pgettext_lazy("Wochentag kurz", "Fr"), gettext_lazy("Freitag")),
    (5, pgettext_lazy("Wochentag kurz", "Sa"), gettext_lazy("Samstag")),
    (6, pgettext_lazy("Wochentag kurz", "So"), gettext_lazy("Sonntag")),
)
ALLE_TAGE_MASKE = 0b1111111


def maske_aus_tagen(tage) -> int:
    """Wochentage (0 = Montag ... 6 = Sonntag) -> Bitmaske."""
    maske = 0
    for tag in tage:
        tag = int(tag)
        if not 0 <= tag <= 6:
            raise ValueError(f"Ungültiger Wochentag {tag}")
        maske |= 1 << tag
    return maske


def tage_aus_maske(maske) -> list[int]:
    return [tag for tag in range(7) if maske and maske & (1 << tag)]


def _zeit_text(wert) -> str | None:
    return wert.strftime("%H:%M") if wert else None


def _zeit_aus_text(wert) -> time | None:
    if not wert:
        return None
    if isinstance(wert, time):
        return wert
    stunde, minute = str(wert).split(":")[:2]
    return time(int(stunde), int(minute))


@dataclass(frozen=True)
class Plan:
    art: str = EINMALIG
    wochentage: int | None = None
    intervall_tage: int | None = None
    start_datum: date | None = None
    end_datum: date | None = None
    fenster_von: time | None = None
    fenster_bis: time | None = None
    fenster_tage: int | None = None
    limit_anzahl: int | None = None
    limit_zeitraum: str = ""

    @property
    def zeitgebunden(self) -> bool:
        return self.fenster_bis is not None

    @property
    def wochentage_liste(self) -> list[int]:
        return tage_aus_maske(self.wochentage)

    # --- Serialisierung (Vorlage.wiederholung); Start/Ende gehören zur konkreten Aufgabe ---
    def als_json(self) -> dict:
        return {
            "art": self.art,
            "wochentage": self.wochentage_liste,
            "intervall_tage": self.intervall_tage,
            "fenster_von": _zeit_text(self.fenster_von),
            "fenster_bis": _zeit_text(self.fenster_bis),
            "fenster_tage": self.fenster_tage,
            "limit_anzahl": self.limit_anzahl,
            "limit_zeitraum": self.limit_zeitraum,
        }

    @classmethod
    def aus_json(cls, daten) -> Plan:
        if not daten:
            return cls()
        if not isinstance(daten, dict):
            raise ValueError("Wiederholung muss ein Objekt sein")
        tage = daten.get("wochentage") or []
        return cls(
            art=daten.get("art") or EINMALIG,
            wochentage=maske_aus_tagen(tage) or None,
            intervall_tage=daten.get("intervall_tage"),
            fenster_von=_zeit_aus_text(daten.get("fenster_von")),
            fenster_bis=_zeit_aus_text(daten.get("fenster_bis")),
            fenster_tage=daten.get("fenster_tage"),
            limit_anzahl=daten.get("limit_anzahl"),
            limit_zeitraum=daten.get("limit_zeitraum") or "",
        )

    def beschreiben(self) -> str:
        """Verständliche Kurzbeschreibung, z. B. 'Jeden Mi · bis 20:00 Uhr · max. 1x pro Woche'."""
        if self.art == WOECHENTLICH:
            namen = [WOCHENTAGE[t][1] for t in self.wochentage_liste]
            teile = [
                _("Jede Woche: %(tage)s") % {"tage": ", ".join(str(n) for n in namen)}
                if namen
                else _("Wöchentlich")
            ]
        elif self.art == INTERVALL:
            n = self.intervall_tage
            teile = (
                [_("Jeden Tag")]
                if n == 1
                else [_("Alle %(n)s Tage") % {"n": n} if n else _("Intervall")]
            )
        else:
            if self.start_datum:
                teile = [
                    _("Einmalig am %(datum)s")
                    % {"datum": date_format(self.start_datum, "SHORT_DATE_FORMAT")}
                ]
            else:
                teile = [_("Einmalig")]
        if self.fenster_bis:
            bis = f"{self.fenster_bis:%H:%M}"
            fenster = _("bis %(bis)s Uhr") % {"bis": bis}
            if self.fenster_von:
                fenster = _("%(von)s bis %(bis)s Uhr") % {
                    "von": f"{self.fenster_von:%H:%M}",
                    "bis": bis,
                }
            if self.fenster_tage:
                fenster += " " + ngettext("(+%(n)s Tag)", "(+%(n)s Tage)", self.fenster_tage) % {
                    "n": self.fenster_tage
                }
            teile.append(fenster)
        if self.limit_anzahl and self.limit_zeitraum:
            teile.append(
                _("max. %(n)sx pro %(zeitraum)s und Kind")
                % {
                    "n": self.limit_anzahl,
                    "zeitraum": ZEITRAUM_WOERTER.get(self.limit_zeitraum, "?"),
                }
            )
        if self.art != EINMALIG and self.end_datum:
            teile.append(
                _("bis %(datum)s") % {"datum": date_format(self.end_datum, "SHORT_DATE_FORMAT")}
            )
        return " · ".join(teile)


def pruefen(plan: Plan) -> dict[str, str]:
    """Konsistenzprüfung. Rückgabe: ``{feldname: Meldung}`` (leer = gültig)."""
    fehler: dict[str, str] = {}
    arten = {a for a, _label in ARTEN}
    if plan.art not in arten:
        fehler["wiederholungsart"] = _("Unbekannte Wiederholungsart.")
        return fehler

    if plan.art == WOECHENTLICH:
        if not plan.wochentage:
            fehler["wochentage"] = _("Bitte mindestens einen Wochentag wählen.")
        elif not 0 < plan.wochentage <= ALLE_TAGE_MASKE:
            fehler["wochentage"] = _("Ungültige Wochentage.")
    elif plan.wochentage:
        fehler["wochentage"] = _("Wochentage gibt es nur bei wöchentlicher Wiederholung.")

    if plan.art == INTERVALL:
        if plan.intervall_tage is None or plan.intervall_tage < 1:
            fehler["intervall_tage"] = _("Bitte einen Abstand von mindestens 1 Tag angeben.")
    elif plan.intervall_tage is not None:
        fehler["intervall_tage"] = _(
            "Ein Intervall gibt es nur bei der Wiederholungsart Intervall."
        )

    if plan.start_datum and plan.end_datum and plan.end_datum < plan.start_datum:
        fehler["end_datum"] = _("Das Ende darf nicht vor dem Start liegen.")

    if plan.fenster_von and not plan.fenster_bis:
        fehler["fenster_bis"] = _("Für ein Zeitfenster fehlt die Frist (Ende).")
    if plan.fenster_tage is not None:
        if plan.fenster_tage < 0:
            fehler["fenster_tage"] = _("Die Tage dürfen nicht negativ sein.")
        elif plan.fenster_tage and not plan.fenster_bis:
            fehler["fenster_tage"] = _("Mehrere Tage gehen nur mit einer Frist.")
    if (
        plan.fenster_von
        and plan.fenster_bis
        and not plan.fenster_tage
        and plan.fenster_bis <= plan.fenster_von
    ):
        fehler["fenster_bis"] = _("Das Ende muss nach dem Beginn liegen (oder Tage > 0 wählen).")

    if (plan.limit_anzahl is None) != (not plan.limit_zeitraum):
        fehler["limit_anzahl"] = _("Limit braucht Anzahl und Zeitraum zusammen.")
    elif plan.limit_anzahl is not None:
        if plan.limit_anzahl < 1:
            fehler["limit_anzahl"] = _("Das Limit muss mindestens 1 sein.")
        elif plan.limit_zeitraum not in ZEITRAUM_WOERTER:
            fehler["limit_zeitraum"] = _("Unbekannter Zeitraum.")
    return fehler
