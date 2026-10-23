FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=famko.settings.produktion \
    FAMKO_DATA_DIR=/data TZ=Europe/Berlin

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .
RUN useradd --uid 1000 --create-home famko \
    && mkdir -p /data && chown famko:famko /data \
    && FAMKO_SECRET_KEY=build python manage.py collectstatic --noinput

USER famko
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# Rolle wird in compose.yaml gesetzt; Standard = web
CMD ["gunicorn", "famko.wsgi", "-k", "gthread", "-w", "2", "--threads", "4", "-b", "0.0.0.0:8000"]
