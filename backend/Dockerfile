# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Builder: wheels are compiled here so the runtime image never needs a compiler.
# Pinned by tag; swap to a digest (python:3.12-slim@sha256:...) for the bonus.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# requirements before source: this layer is cached across every source change,
# which is the difference between a 4-second rebuild and a 90-second one.
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 civic \
 && useradd --system --uid 10001 --gid civic --no-create-home civic

WORKDIR /srv/app

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY app ./app
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && chown -R civic:civic /srv/app

USER civic
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# exec form: PID 1 is uvicorn itself, so SIGTERM reaches it rather than a shell
# that would swallow it and leave Kubernetes to SIGKILL us 30 seconds later.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "25"]
