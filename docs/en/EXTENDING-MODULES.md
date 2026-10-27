# Creating a new module

🇬🇧 **English** · 🇩🇪 [Deutsch](../MODULE-ERWEITERN.md)

This guide uses the example module **`lernen`** (learning, layer 3) to show how a new feature module is created in Nestwerk. The architecture is described in [`docs/ARCHITECTURE.md` (German)](../ARCHITECTURE.md), and the rules for the data model and default values in [`docs/DATA_MODEL.md` (German)](../DATA_MODEL.md).

**Basic rule:** a new module is a new Django app in the same image. It needs **no changes** to `oberflaeche` and no changes to other feature modules.

---

## 1. Layers and dependencies

| You may import | You must **not** import |
|---|---|
| `kern` (settings, registry, time, audit) | other feature modules (`aufgaben`, `belohnung`, `avatar`, `sondertag`, `familienziel`) |
| `konten.selectors` (read users) | other modules' `models.py` (not even from `punkte` or `spielregeln`) |
| `punkte.services` (post balance) | `spielregeln.abzeichen`, `spielregeln.raenge` and other internals |
| `spielregeln.services`, `.selectors`, `.registry`, `.events` | |
| `ereignisse.services`, `ereignisse.registry` | |

Modules communicate with each other only through **domain events** and the **registry** in `kern`.

Example: learning should count as an active week. The module calls `spielregeln.services.aktivitaet_erfassen(kind, datum, modul="lernen", referenz=...)`.

---

## 2. Creating the app

```bash
mkdir -p apps/lernen && cd apps/lernen
touch __init__.py models.py services.py selectors.py events.py registry.py einstellungen.py apps.py
mkdir -p migrations tests templates/lernen/kacheln
touch migrations/__init__.py tests/__init__.py
```

**`apps/lernen/apps.py`:** all registrations belong in `ready()`, as in `sondertag`:

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
        # Handlers for events from other modules: see section 4
```

**Activate the app:** add `"apps.lernen"` to `INSTALLED_APPS` in `nestwerk/settings/basis.py` (next to `"apps.sondertag"`).

**Layer contract:** `pyproject.toml` already lists `(lernen)` in the layer 3 line of the import-linter contract. The brackets allow the app to be absent. Check with `lint-imports`.

---

## 3. Settings (`kern.einstellungen`)

All values live in the database. The code only holds the definitions.

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

- **Default values** come from a data migration (`migrations/0002_startwerte.py`), as in `sondertag`. The runtime never reads a code default.
- **Reading:** `from apps.kern.einstellungen import wert` and then `wert("lernen.tagesziel_minuten")`.

---

## 4. Events (`ereignisse` and `benachrichtigung`)

**`events.py`**: event types, texts and targets:

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
        zielgruppe="eltern",  # "kind", "eltern" or "intern"
        standard_kanaele=["push"],  # email, push, pop-up
    )


def texte_registrieren():
    text_registrieren(
        LERNZIEL_ERREICHT,
        titel="Lernziel erreicht",
        text="Das Tagesziel für die Lernzeit ist erreicht.",
    )
```

**Publish an event** (in `services.py`, in the same transaction as the domain change):

```python
from apps.ereignisse import services as ereignisse

ereignisse.veroeffentlichen(
    LERNZIEL_ERREICHT,
    kind=kind,
    daten={"minuten": minuten},
    schluessel=f"lernen.ziel:{kind.pk}:{datum.isoformat()}",  # prevents duplicates
)
```

**Handler** (reacts to events from other modules), register in `ready()`:

```python
from apps.ereignisse import registry as ereignis_registry

ereignis_registry.handler_registrieren(
    "punkte.gebucht",
    services.nach_punktebuchung,
    name="lernen.nach_punktebuchung",
    synchron=False,  # async via the worker; sync only for mandatory follow-up steps in layer 2
)
```

---

## 5. Tiles and metrics (`kern.registry`)

**Tiles** appear automatically on the kids' or parent dashboard. `oberflaeche` does not need to be changed for this.

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
    return {"minuten_heute": 0}  # later from selectors


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

- **Tile template** lives in `apps/lernen/templates/lernen/kacheln/kind_lernen.html`.
- **Metric** is a catalogue entry (name, unit). A **provider** supplies the value per child. The provider key is always `metrik.<schluessel>`.
- The target groups are `KIND` and `ELTERN` from `kern.registry`.

---

## 6. Badges and milestones

Badges and milestones are **data**, not code logic. The engine in `spielregeln` evaluates them generically.

- **Badge (`AbzeichenDefinition`):** key, name, symbol, **metric** (e.g. `lernen.vokabeln_gesamt`), threshold, repeatability (`einmalig`, `je_quartal`, `je_rang`), module, active.
- **Milestone (`MeilensteinRegel`):** metric, condition (JSON), reward type (e.g. `sondertag`), repeatability.
- You create both via a **data migration**, like `spielregeln/migrations/0008_abzeichen_startwerte.py`. Parents can change the values afterwards in the interface.
- **Symbol:** your own design, no third-party brands (see [CONTRIBUTING.md](../../CONTRIBUTING.md)).

Test note: a new badge should work without changing the engine. A test with a test module checks this (pattern: `spielregeln/tests/test_abzeichen.py`).

---

## 7. Migrations and tests

```bash
python manage.py makemigrations lernen
python manage.py migrate
pytest apps/lernen                 # module tests
pytest                             # everything
ruff check . && ruff format --check .
lint-imports                       # check layers
```

Migration rules:

- **Additive only:** new columns and tables. Delete and rename only in a later step (expand/contract). This keeps a rollback possible after an update.
- **Default values** only via data migrations, never in code.

---

## Checklist for a new module

- [ ] App under `apps/<name>/` with `apps.py`, `services.py`, `selectors.py`, `events.py`, `registry.py`, `einstellungen.py`
- [ ] Added to `INSTALLED_APPS`
- [ ] Listed in the import-linter contract (layer 3)
- [ ] Settings defined, default values via data migration
- [ ] Event types and texts registered, handlers set
- [ ] Tiles and metrics registered via `kern.registry`
- [ ] Badges and milestones created as data
- [ ] Tests for layer rules (`lint-imports`) and module tests passing
- [ ] No imports between feature modules
