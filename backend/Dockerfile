FROM python:3.12-slim

WORKDIR /repo

# Dependencies first for layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Layout mirrors the repo so data/demo_alerts.json resolves at runtime
# (app/main.py -> parents[2] / "data" / "demo_alerts.json").
COPY backend/app ./backend/app
COPY data ./data

WORKDIR /repo/backend

# Railway injects $PORT; default to 8000 for local docker runs.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8000') + '/health', timeout=4).status == 200 else 1)"
