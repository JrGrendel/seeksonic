FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DB_PATH=/app/data/sync_state.db

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

COPY --chown=appuser:appuser app.py /app/app.py
COPY --chown=appuser:appuser seeksonic/ /app/seeksonic/
COPY --chown=appuser:appuser static/ /app/static/

USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()"

CMD ["python", "-u", "/app/app.py"]
