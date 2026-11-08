"""Datenmigration 0009: Eltern-Wappen werden zu Eltern-Moods (vorwärts und rückwärts)."""

import pytest


@pytest.mark.django_db(transaction=True)
def test_migration_uebernimmt_wappen_als_mood_und_ist_reversibel():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    vorher = [("konten", "0008_kind_einstellungen_moods")]
    nachher = [("konten", "0009_eltern_moods")]

    def migrieren(ziel):
        ex = MigrationExecutor(connection)
        ex.migrate(ziel)
        return ex.loader.project_state(ziel).apps

    try:
        alt = migrieren(vorher)
        B = alt.get_model("konten", "Benutzer")
        E = alt.get_model("konten", "MoodEigen")
        B.objects.create(anzeigename="Mama", rolle="eltern", wappen="nachteule")
        B.objects.create(anzeigename="Papa", rolle="eltern", wappen="")
        B.objects.create(anzeigename="Anna", rolle="kind", mood="faultier")
        E.objects.create(text="Alt")
        neu = migrieren(nachher)
        B, E = neu.get_model("konten", "Benutzer"), neu.get_model("konten", "MoodEigen")
        assert B.objects.get(anzeigename="Mama").mood == "nachteule"
        assert B.objects.get(anzeigename="Papa").mood == ""
        assert B.objects.get(anzeigename="Anna").mood == "faultier"
        assert E.objects.get(text="Alt").zielgruppe == "kind"
        B.objects.filter(anzeigename="Papa").update(mood="geek")
        alt = migrieren(vorher)
        B = alt.get_model("konten", "Benutzer")
        assert B.objects.get(anzeigename="Mama").wappen == "nachteule"
        assert B.objects.get(anzeigename="Papa").wappen == ""  # geek gibt es dort nicht
        assert B.objects.get(anzeigename="Anna").mood == "faultier"
    finally:
        migrieren(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_rueckweg_mit_gleichem_text_bei_kindern_und_eltern_und_ohne_avatar_tabelle():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    def migrieren(ziel):
        ex = MigrationExecutor(connection)
        ex.migrate(ziel)
        return ex.loader.project_state(ziel).apps

    try:
        neu = migrieren([("konten", "0009_eltern_moods")])
        E = neu.get_model("konten", "MoodEigen")
        E.objects.create(text="Doppelt", zielgruppe="kind")
        E.objects.create(text="Doppelt", zielgruppe="eltern")
        alt = migrieren([("konten", "0008_kind_einstellungen_moods")])
        E = alt.get_model("konten", "MoodEigen")
        assert list(E.objects.values_list("text", flat=True)) == ["Doppelt"]
    finally:
        migrieren(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_avatar_hash_hook_ueberspringt_fehlende_eltern_tabelle():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.avatar import services as avatar_services

    try:
        MigrationExecutor(connection).migrate([("avatar", "0007_avatar_name")])
        assert "avatar_elternavatar" not in connection.introspection.table_names()
        avatar_services.hashes_aktualisieren()  # darf nicht crashen
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
