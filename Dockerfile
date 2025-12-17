# ============================================
# Dockerfile Production - ValoMaison
# Multi-stage build optimise
# ============================================

# Stage 1: Build des dependances
FROM python:3.11-slim as builder

WORKDIR /app

# Installer les dependances de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dependances
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# Stage 2: Image de production
FROM python:3.11-slim

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

WORKDIR /app

# Installer les dependances runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copier les wheels et installer
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/* && rm -rf /wheels

# Copier le code source
COPY --chown=appuser:appuser . .

# Changer vers utilisateur non-root
USER appuser

# Port expose
EXPOSE 5000

# Healthcheck avec curl (plus fiable)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Commande de demarrage
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
