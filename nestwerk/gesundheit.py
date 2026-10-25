"""Healthcheck /gesundheit/.

- **503** nur, wenn die Datenbank nicht lesbar ist oder Migrationen offen sind: Dann kann die
  App nicht arbeiten, und ein Neustart des Containers kann helfen.
- **200 mit ``status: degradiert``**, wenn der Ereignis-Worker keinen Herzschlag mehr meldet:
  Die Oberfläche funktioniert weiter (Ereignisse bleiben in der Outbox und werden nachgeholt).
  Ein 503 würde den Web-Container grundlos neu starten bzw. aus dem Proxy nehmen, obwohl der
  Fehler im Worker-Container liegt. Der Zustand steht im JSON und im Systemstatus.
"""

from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.ereignisse import selectors as ereignis_selectors


@require_GET
def gesundheit(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        executor = MigrationExecutor(connection)
        offen = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not offen:
            herzschlag = ereignis_selectors.worker_herzschlag()
            lebt = ereignis_selectors.worker_lebt()
    except DatabaseError as exc:
        return JsonResponse(
            {"status": "fehler", "grund": f"db: {exc.__class__.__name__}"}, status=503
        )
    if offen:
        return JsonResponse({"status": "fehler", "grund": "migrationen offen"}, status=503)
    return JsonResponse(
        {
            "status": "ok" if lebt else "degradiert",
            "worker": {"lebt": lebt, "herzschlag": herzschlag.isoformat() if herzschlag else None},
        }
    )
