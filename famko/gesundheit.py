"""Healthcheck /gesundheit/: DB lesbar und alle Migrationen angewendet.
(Worker-Herzschlag kommt mit AP05.)"""

from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def gesundheit(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        executor = MigrationExecutor(connection)
        offen = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except DatabaseError as exc:
        return JsonResponse(
            {"status": "fehler", "grund": f"db: {exc.__class__.__name__}"}, status=503
        )
    if offen:
        return JsonResponse({"status": "fehler", "grund": "migrationen offen"}, status=503)
    return JsonResponse({"status": "ok"})
