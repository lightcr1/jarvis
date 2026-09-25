# Executor-Dienst: minimal, nur jarvis.executor + Zonen-/Capability-Policy.
# Spricht ausschliesslich mit dem eingeschraenkten Docker-Socket-Proxy.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/executor/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY jarvis/ ./jarvis/
COPY config/ ./config/
COPY services/executor/app.py ./
EXPOSE 8120
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8120/health', timeout=3)" || exit 1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8120"]
