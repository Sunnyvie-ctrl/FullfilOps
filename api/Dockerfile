# syntax=docker/dockerfile:1
# FulfillOps API image — multi-stage, non-root.
# Build from the repo root:  docker build -f api/Dockerfile -t fulfillops-api .

# ---------- Stage 1: builder (has pip, installs dependencies) ----------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install everything into an isolated virtualenv we can copy as one folder.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy ONLY requirements first so Docker can cache this layer
# (code changes won't force a full reinstall).
COPY requirements.txt .
RUN pip install --upgrade pip setuptools \
 && pip install -r requirements.txt

# ---------- Stage 2: runtime (what actually ships) ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# 1) Install Debian security updates (e.g. zlib CVE fixes published after the
#    base image was built).
# 2) Remove Python packaging tools the app never uses at runtime, including the
#    spare wheels ensurepip keeps on disk: they are a common source of Trivy findings.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && (python -m pip uninstall -y setuptools wheel pip || true) \
 && rm -rf /usr/local/lib/python3.11/ensurepip/_bundled

# Unprivileged user with a fixed UID (Kubernetes can verify runAsNonRoot).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Dependencies from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Application code. Owned by root = read-only for the app user,
# so an attacker inside the container cannot modify the code.
COPY api/ ./api/
COPY db/ ./db/
COPY scripts/ ./scripts/
COPY alembic.ini ./

USER 10001

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=2)" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
