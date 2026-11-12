# syntax=docker/dockerfile:1
# FulfillOps outbox worker image — multi-stage, non-root.
# Build from the repo root:  docker build -f worker/Dockerfile -t fulfillops-worker .

# ---------- Stage 1: builder ----------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip setuptools \
 && pip install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m pip uninstall -y pip setuptools wheel || true

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# The worker imports the shared SQLAlchemy models from api/models.py.
COPY api/ ./api/
COPY worker/ ./worker/

USER 10001

# No port: the worker only talks to PostgreSQL (it polls outbox_jobs).
# It handles SIGTERM, so "docker stop" / a K8s rolling update stops it cleanly.
CMD ["python", "-m", "worker.worker"]
