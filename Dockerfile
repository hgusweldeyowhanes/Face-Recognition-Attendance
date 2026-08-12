# Presence — Face Recognition Attendance
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    HOST=0.0.0.0 \
    PORT=5000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p known_faces uploads \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')" || exit 1

CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=4", "wsgi:app"]
