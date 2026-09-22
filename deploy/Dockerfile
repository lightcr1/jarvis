# J.A.R.V.I.S. AI Assistant — containerized build
# Multi-stage: frontend (node) -> runtime (python).
# The app serves the built SPA from frontend/dist (see jarvisappv4.py).

# ---- Stage 1: frontend ----
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: python runtime ----
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System libs needed by faster-whisper (ctranslate2), cryptography etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libsndfile1 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /build/dist frontend/dist

RUN mkdir -p /var/lib/jarvis /etc/jarvis

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "jarvisappv4:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
