FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=nestwerk.settings.produktion \
    NESTWERK_DATA_DIR=/data NESTWERK_BACKUP_ZIEL=/backup TZ=Europe/Berlin

# supercronic (Scheduler-Rolle): Version gepinnt, SHA-256 beim Build geprüft (nur linux/amd64;
# Prüfsumme aus der GitHub-Release-API, Update: Version + Prüfsumme gemeinsam ändern).
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ADD --checksum=sha256:${SUPERCRONIC_SHA256} --chmod=755 \
    https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64 \
    /usr/local/bin/supercronic

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .
RUN useradd --uid 1000 --create-home nestwerk \
    && mkdir -p /data /backup && chown nestwerk:nestwerk /data /backup \
    && NESTWERK_SECRET_KEY=build python manage.py collectstatic --noinput

USER nestwerk
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# Rolle wird in compose.yaml gesetzt; Standard = web
CMD ["gunicorn", "nestwerk.wsgi", "-k", "gthread", "-w", "2", "--threads", "4", "-b", "0.0.0.0:8000"]
