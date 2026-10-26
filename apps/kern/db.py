"""DB-Hilfen: insert-only-Tabellen (Modell-, QuerySet- und Trigger-Sperre), Wartungsmodus.

Insert-only (DATA_MODEL 0) wird dreifach durchgesetzt:
- Modell: ``save()`` auf bestehender Zeile und ``delete()`` werfen ``NurEinfuegenFehler``.
- QuerySet: ``update()``, ``delete()``, ``bulk_update()`` werfen ``NurEinfuegenFehler``.
- SQLite-Trigger: ``BEFORE UPDATE/DELETE -> RAISE(ABORT)`` (greift auch bei Roh-SQL).

Ausnahme nur für DELETE im Wartungsmodus (``wartung()``), z. B. Test-Flush. Der Trigger fragt
dazu die SQL-Funktion ``nestwerk_wartung()`` ab, die nur Django-Verbindungen kennen. Fremde
Verbindungen (sqlite3-CLI) kennen sie nicht und scheitern damit ebenfalls (fail closed).
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import migrations, models

_wartung: ContextVar[bool] = ContextVar("nestwerk_wartung", default=False)


class NurEinfuegenFehler(Exception):
    """Änderung oder Löschung einer insert-only-Zeile."""


@contextmanager
def wartung():
    """Erlaubt DELETE auf insert-only-Tabellen (nur Test-Flush/Wartung, nie im Fachcode)."""
    token = _wartung.set(True)
    try:
        yield
    finally:
        _wartung.reset(token)


def _wartung_aktiv():
    return 1 if _wartung.get() else 0


def sql_funktionen_registrieren(sender, connection, **kwargs):
    """Signal-Handler für ``connection_created``: SQL-Funktion ``nestwerk_wartung()``."""
    if connection.vendor == "sqlite":
        connection.connection.create_function("nestwerk_wartung", 0, _wartung_aktiv)


def nur_einfuegen_trigger(tabelle):
    """Migrations-Operation: Trigger, die UPDATE und DELETE auf ``tabelle`` abbrechen."""
    meldung = f"{tabelle} ist insert-only"
    return migrations.RunSQL(
        sql=[
            f"CREATE TRIGGER {tabelle}_kein_update BEFORE UPDATE ON {tabelle} "
            f"BEGIN SELECT RAISE(ABORT, '{meldung}'); END;",
            f"CREATE TRIGGER {tabelle}_kein_delete BEFORE DELETE ON {tabelle} "
            f"WHEN nestwerk_wartung() = 0 "
            f"BEGIN SELECT RAISE(ABORT, '{meldung}'); END;",
        ],
        reverse_sql=[
            f"DROP TRIGGER IF EXISTS {tabelle}_kein_update;",
            f"DROP TRIGGER IF EXISTS {tabelle}_kein_delete;",
        ],
    )


class NurEinfuegenQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise NurEinfuegenFehler(f"{self.model.__name__} ist insert-only (update)")

    def delete(self):
        raise NurEinfuegenFehler(f"{self.model.__name__} ist insert-only (delete)")

    def bulk_update(self, objs, fields, batch_size=None):
        raise NurEinfuegenFehler(f"{self.model.__name__} ist insert-only (bulk_update)")

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise NurEinfuegenFehler(f"{self.model.__name__} ist insert-only (update_or_create)")


class NurEinfuegenModell(models.Model):
    """Abstrakte Basis für insert-only-Tabellen (``kern.AuditEintrag``, ``punkte.Buchung``).

    Die Tabelle braucht zusätzlich ``nur_einfuegen_trigger(<tabelle>)`` in einer Migration.
    """

    objects = NurEinfuegenQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise NurEinfuegenFehler(f"{type(self).__name__} ist insert-only (save)")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NurEinfuegenFehler(f"{type(self).__name__} ist insert-only (delete)")
