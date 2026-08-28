# syntax=docker/dockerfile:1

# --- base -------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Kathmandu

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer: only invalidated when pyproject.toml changes.
COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel \
    && python - <<'PY' > /tmp/reqs.txt
import tomllib
with open("pyproject.toml", "rb") as fh:
    data = tomllib.load(fh)
print("\n".join(data["project"]["dependencies"]))
print("\n".join(data["project"]["optional-dependencies"]["dev"]))
PY
RUN pip install -r /tmp/reqs.txt

COPY . .
RUN pip install --no-deps -e .

# --- dev --------------------------------------------------------------------
FROM base AS dev
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- production -------------------------------------------------------------
FROM base AS production

# Never run the API as root.
RUN useradd --create-home --uid 10001 sajilo && chown -R sajilo:sajilo /app
USER sajilo

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

# Workers are tuned by the deploy target; 4 is a sane default for a 2-vCPU box.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--no-access-log", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
