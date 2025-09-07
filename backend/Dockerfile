# ---- Base image
FROM python:3.10-slim

# ---- System deps (+ CA certs & utils réseau)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tzdata \
    libxml2 \
    libxslt1.1 \
    libfreetype6 \
    libpng16-16 \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ---- Env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Zurich

WORKDIR /app

# ---- Dépendances Python
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel certifi \
 && pip install --prefer-binary --timeout 240 --retries 5 -r requirements.txt

# ---- Réseau
EXPOSE 5000

# ---- Healthcheck basique (API doit répondre)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "import json,urllib.request,sys; \
u=urllib.request.urlopen('http://127.0.0.1:5000/api/status',timeout=3); \
j=json.load(u); sys.exit(0 if isinstance(j,dict) and ('symbol' in j or 'paper' in j) else 1)" || \
exit 1

# ---- Lancement
CMD ["python", "app.py"]

