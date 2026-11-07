"""Ereignistypen und Texte von lernen (SPEC 21.12, ARCHITECTURE 5.2).

Ereignis-Daten enthalten keine fertigen Sätze, sondern msgid + Parameter (docs/i18n.md); erst
beim Rendern wird in der Sprache des Empfängers übersetzt.
"""

from django.utils.translation import gettext_noop

from apps.benachrichtigung import texte
from apps.ereignisse import registry

LERNZIEL_ERREICHT = "lernen.ziel_erreicht"  # Kind: kleines Pop-up "Tagesziel geschafft"

PRUEFUNG_VORBEREITET = "lernen.pruefung_vorbereitet"  # Kind: "Prüfungsplan eingehalten"

# Eltern-Ausnahmen (Etappe 13): Push, nie Dauerstrom; Dedupe über den Schlüssel des Ereignisses
MATERIAL_WARTET = "lernen.material_wartet"  # Material wartet auf Freigabe
KIND_STILL = "lernen.kind_still"  # 3 Tage ohne Mindesttag (nicht in Pause/Ferien)
FEHLERHAEUFUNG = "lernen.fehlerhaeufung"  # gleiche Rechenart öfter falsch diese Woche
TUTOR_MARKIERUNG = "lernen.tutor_markierung"  # Tutor: Rollenwechsel oder Antwort zurückgehalten
PRUEFUNG_RUESTET = "lernen.pruefung_ruestet"  # Prüfung in höchstens 3 Tagen, Plan unter 50 %
WOCHENBILD = "lernen.wochenbild"  # Wochen-Digest

LINK_KIND = "/kind/lernen/"
LINK_PRUEFUNG = "/kind/lernen/pruefung/"
LINK_MATERIAL = "/eltern/lernen/material/?kind={kind_id}"  # wählt die Einträge des Kindes vor
LINK_WOCHE = "/eltern/lernen/woche/"
LINK_TUTOR = "/eltern/lernen/tutor/{gespraech}/"
LINK_ELTERN_PRUEFUNG = "/eltern/lernen/pruefung/{pruefung}/"


def typen_deklarieren():
    registry.typ_deklarieren(
        LERNZIEL_ERREICHT,
        modul="lernen",
        bezeichnung=gettext_noop("Lernziel erreicht"),
        zielgruppe="kind",
        standard_kanaele=["popup"],
        deep_link_muster=LINK_KIND,
    )
    registry.typ_deklarieren(
        PRUEFUNG_VORBEREITET,
        modul="lernen",
        bezeichnung=gettext_noop("Prüfung vorbereitet"),
        zielgruppe="kind",
        standard_kanaele=["popup"],
        deep_link_muster=LINK_PRUEFUNG,
    )
    _eltern_typen_deklarieren()


def _eltern_typen_deklarieren():
    for slug, bezeichnung, link in (
        (MATERIAL_WARTET, gettext_noop("Material wartet auf Freigabe"), LINK_MATERIAL),
        (KIND_STILL, gettext_noop("Kind hat länger nicht geübt"), LINK_WOCHE),
        (FEHLERHAEUFUNG, gettext_noop("Fehlerhäufung bei einer Rechenart"), LINK_WOCHE),
        (TUTOR_MARKIERUNG, gettext_noop("Auffälligkeit im Tutor-Gespräch"), LINK_TUTOR),
        (PRUEFUNG_RUESTET, gettext_noop("Prüfung steht bald an"), LINK_ELTERN_PRUEFUNG),
        (WOCHENBILD, gettext_noop("Lernwoche (Zusammenfassung)"), LINK_WOCHE),
    ):
        registry.typ_deklarieren(
            slug,
            modul="lernen",
            bezeichnung=bezeichnung,
            zielgruppe="eltern",
            standard_kanaele=["push"],
            deep_link_muster=link,
        )


def texte_registrieren():
    texte.text_registrieren(
        LERNZIEL_ERREICHT,
        titel=gettext_noop("Tagesziel geschafft!"),
        text="{hinweis}",  # der Satz steckt in hinweis_msgid + hinweis_parameter
    )
    texte.text_registrieren(
        PRUEFUNG_VORBEREITET,
        titel=gettext_noop("Prüfungsplan eingehalten!"),
        text="{hinweis}",
    )
    # Eltern-Meldungen (Texte X1-X5): kurze Angebote für ein Gespräch, nie ein Vorwurf
    texte.text_registrieren(
        MATERIAL_WARTET, titel=gettext_noop("Material wartet"), text="{hinweis}"
    )
    texte.text_registrieren(
        KIND_STILL,
        titel=gettext_noop("Mal nachfragen?"),
        text=gettext_noop(
            "{kind} hat seit 3 Tagen nicht geübt. Vielleicht mal nachfragen, ob alles passt?"
        ),
    )
    texte.text_registrieren(
        FEHLERHAEUFUNG,
        titel=gettext_noop("Hilfe beim Rechnen"),
        text=gettext_noop(
            "{kind} stolpert diese Woche öfter bei {rechenart}. "
            "Die Erklärkarte {karte} könnte helfen."
        ),
    )
    texte.text_registrieren(
        TUTOR_MARKIERUNG, titel=gettext_noop("Hinweis aus dem Tutor"), text="{hinweis}"
    )
    texte.text_registrieren(
        PRUEFUNG_RUESTET,
        titel=gettext_noop("Prüfung steht bald an"),
        text=gettext_noop(
            "{kind}: Die Prüfung „{titel}“ ist bald. Vom Plan sind {prozent} Prozent geschafft. "
            "Vielleicht mal gemeinsam draufschauen?"
        ),
    )
    texte.text_registrieren(WOCHENBILD, titel=gettext_noop("Lernwoche {kw}"), text="{zeilen}")
