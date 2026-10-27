# Ein neues Modul anlegen

🇬🇧 [English](en/EXTENDING-MODULES.md) · 🇩🇪 **Deutsch**

Diese Anleitung zeigt am Beispiel **`lernen`** (Schicht 3), wie ein neues Fach-Modul in Nestwerk entsteht. Die Architektur steht in `docs/ARCHITECTURE.md`, die Regeln für Datenmodell und Startwerte in `docs/DATA_MODEL.md`.

**Grundregel:** Ein neues Modul ist eine neue Django-App im selben Image. Es braucht **keine Änderung** an `oberflaeche` und keine Änderung an anderen Fach-Modulen.

---

## 1. Schichten und Abhängigkeiten

| Du darfst importieren | Du darfst **nicht** importieren |
|---|---|
| `kern` (Einstellungen, Registry, Zeit, Audit) | andere Fach-Module (`aufgaben`, `belohnung`, `avatar`, `sondertag`, `familienziel`) |
| `konten.selectors` (Benutzer lesen) | fremde `models.py` (auch nicht von `punkte` oder `spielregeln`) |
| `punkte.services` (Guthaben buchen) | `spielregeln.abzeichen`, `spielregeln.raenge` und andere Interna |
| `spielregeln.services`, `.selectors`, `.registry`, `.events` | |
| `ereignisse.services`, `ereignisse.registry` | |

Kommunikation mit anderen Modulen läuft nur über **Domain-Ereignisse** und die **Registry** in `kern`.

Beispiel: Lernen soll als aktive Woche zählen. Das Modul ruft `spielregeln.services.aktivitaet_erfassen(kind, datum, modul="lernen", referenz=...)` auf.

---

## 2. App anlegen

```bash
mkdir -p apps/lernen && cd apps/lernen
touch __init__.py models.py services.py selectors.py events.py registry.py einstellungen.py apps.py
mkdir -p migrations tests templates/lernen/kacheln
touch migrations/__init__.py tests/__init__.py
```

**`apps/lernen/apps.py`:** Alle Registrierungen gehören in `ready()`, wie bei `sondertag`:

```python
from django.apps import AppConfig


class LernenConfig(AppConfig):
    name = "apps.lernen"
    label = "lernen"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Lernen"

    def ready(self):
        from . import events, registry
        from .einstellungen import einstellungen_definieren

        einstellungen_definieren()
        events.typen_deklarieren()
        events.texte_registrieren()
        registry.kacheln_registrieren()
        registry.metriken_registrieren()
        # Handler für fremde Ereignisse: siehe Abschnitt 4
```

**App aktivieren:** `"apps.lernen"` in `INSTALLED_APPS` in `nestwerk/settings/basis.py` eintragen (neben `"apps.sondertag"`).

**Schichtenvertrag:** In `pyproject.toml` steht `(lernen)` bereits in der Schicht-3-Zeile des Import-Linter-Vertrags. Der Eintrag in Klammern erlaubt, dass die App optional fehlt. Prüfen mit `lint-imports`.

---

## 3. Einstellungen (`kern.einstellungen`)

Alle Werte liegen in der Datenbank. Im Code stehen nur die Definitionen.

```python
# apps/lernen/einstellungen.py
from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "lernen.tagesziel_minuten": 20,
}


def einstellungen_definieren():
    definieren(
        "lernen.tagesziel_minuten",
        Typ.GANZZAHL,
        "Tagesziel Lernzeit",
        beschreibung="Wie viele Minuten pro Tag als Ziel gelten.",
        einheit="Minuten",
        minimum=1,
        maximum=240,
    )
```

- **Startwerte** kommen über eine Datenmigration (`migrations/0002_startwerte.py`), wie bei `sondertag`. Die Laufzeit liest nie einen Code-Default.
- **Lesen:** `from apps.kern.einstellungen import wert` und dann `wert("lernen.tagesziel_minuten")`.

---

## 4. Ereignisse (`ereignisse` und `benachrichtigung`)

**`events.py`**: Ereignistypen, Texte und Ziele:

```python
# apps/lernen/events.py
from apps.benachrichtigung.texte import text_registrieren
from apps.ereignisse.registry import typ_deklarieren

LERNZIEL_ERREICHT = "lernen.ziel_erreicht"


def typen_deklarieren():
    typ_deklarieren(
        LERNZIEL_ERREICHT,
        modul="lernen",
        bezeichnung="Lernziel erreicht",
        zielgruppe="eltern",  # "kind", "eltern" oder "intern"
        standard_kanaele=["push"],  # E-Mail, Push, Pop-up
    )


def texte_registrieren():
    text_registrieren(
        LERNZIEL_ERREICHT,
        titel="Lernziel erreicht",
        text="Das Tagesziel für die Lernzeit ist erreicht.",
    )
```

**Ereignis veröffentlichen** (in `services.py`, in derselben Transaktion wie die Fachänderung):

```python
from apps.ereignisse import services as ereignisse

ereignisse.veroeffentlichen(
    LERNZIEL_ERREICHT,
    kind=kind,
    daten={"minuten": minuten},
    schluessel=f"lernen.ziel:{kind.pk}:{datum.isoformat()}",  # verhindert Doppelungen
)
```

**Handler** (reagiert auf fremde Ereignisse), in `ready()` registrieren:

```python
from apps.ereignisse import registry as ereignis_registry

ereignis_registry.handler_registrieren(
    "punkte.gebucht",
    services.nach_punktebuchung,
    name="lernen.nach_punktebuchung",
    synchron=False,  # asynchron über den Worker; synchron nur für zwingende Folgen in Schicht 2
)
```

---

## 5. Kacheln und Metriken (`kern.registry`)

**Kacheln** erscheinen automatisch im Kinder- oder Eltern-Dashboard. `oberflaeche` muss dafür nicht geändert werden.

```python
# apps/lernen/registry.py
from apps.kern.registry import (
    ELTERN,
    KIND,
    Kachel,
    Metrik,
    Provider,
    kachel_registrieren,
    metrik_registrieren,
    provider_registrieren,
)

MODUL = "lernen"


def _kind_kontext(request):
    return {"minuten_heute": 0}  # später aus selectors


def kacheln_registrieren():
    kachel_registrieren(
        Kachel(
            "lernen.kind",
            MODUL,
            "Lernen",
            "lernen/kacheln/kind_lernen.html",
            frozenset({KIND}),
            _kind_kontext,
            reihenfolge=12,
        )
    )


def metriken_registrieren():
    metrik_registrieren(Metrik("vokabeln_gesamt", MODUL, "Vokabeln gesamt", einheit="Stk"))
    provider_registrieren(
        Provider("metrik.vokabeln_gesamt", MODUL, "Vokabeln gesamt", lambda kind: 0)
    )
```

- **Kachel-Template** liegt in `apps/lernen/templates/lernen/kacheln/kind_lernen.html`.
- **Metrik** ist ein Katalogeintrag (Name, Einheit). **Provider** liefert den Wert je Kind. Der Schlüssel des Providers ist immer `metrik.<schluessel>`.
- Die Zielgruppen sind `KIND` und `ELTERN` aus `kern.registry`.

---

## 6. Abzeichen und Meilensteine

Abzeichen und Meilensteine sind **Daten**, keine Code-Logik. Die Engine in `spielregeln` wertet sie generisch aus.

- **Abzeichen (`AbzeichenDefinition`):** Schlüssel, Name, Symbol, **Metrik** (z. B. `lernen.vokabeln_gesamt`), Schwelle, Wiederholbarkeit (`einmalig`, `je_quartal`, `je_rang`), Modul, aktiv.
- **Meilenstein (`MeilensteinRegel`):** Metrik, Bedingung (JSON), Belohnungsart (z. B. `sondertag`), Wiederholbarkeit.
- Beide legst du über eine **Datenmigration** an, wie `spielregeln/migrations/0008_abzeichen_startwerte.py`. Die Eltern können Werte danach über die Oberfläche ändern.
- **Symbol:** eigener Entwurf, keine fremden Marken (siehe `CONTRIBUTING.de.md`).

Test-Hinweis: Ein neues Abzeichen soll ohne Änderung der Engine funktionieren. Das prüft ein Test mit einem Testmodul (Muster: `spielregeln/tests/test_abzeichen.py`).

---

## 7. Migrationen und Tests

```bash
python manage.py makemigrations lernen
python manage.py migrate
pytest apps/lernen                 # Modultests
pytest                             # alles
ruff check . && ruff format --check .
lint-imports                       # Schichten prüfen
```

Regeln für Migrationen:

- **Additiv:** Neue Spalten und Tabellen. Löschen und Umbenennen erst in einem späteren Schritt (expand/contract). So bleibt ein Rollback nach einem Update möglich.
- **Startwerte** nur über Datenmigrationen, nie im Code.

---

## Checkliste für ein neues Modul

- [ ] App unter `apps/<name>/` mit `apps.py`, `services.py`, `selectors.py`, `events.py`, `registry.py`, `einstellungen.py`
- [ ] In `INSTALLED_APPS` eingetragen
- [ ] Im Import-Linter-Vertrag (Schicht 3) geführt
- [ ] Einstellungen definiert, Startwerte per Datenmigration
- [ ] Ereignistypen und Texte registriert, Handler gesetzt
- [ ] Kacheln und Metriken über `kern.registry` registriert
- [ ] Abzeichen und Meilensteine als Daten angelegt
- [ ] Tests für Schichtenregeln (`lint-imports`) und Modul grün
- [ ] Keine Importe zwischen Fach-Modulen
