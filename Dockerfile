# Smart Factory Digital Twin Optimizer — Cloud Run image
# Multi-stage build: slim runtime, non-root user, $PORT-compatible entrypoint.

# ----- build stage -----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY optimizer/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt

# ----- runtime stage -----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    OFACT_MODE=stub \
    OFACT_PROJECT=bicycle_world \
    OFACT_STATE_MODEL_FILE=bicycle_factory.xlsx \
    OFACT_TWIN_DIR=scenarios/current/models/twin \
    PORT=8080

WORKDIR /app

# Non-root user for Cloud Run security guidance
RUN groupadd --system --gid 1000 appuser \
    && useradd --system --uid 1000 --gid appuser --create-home appuser

COPY --from=builder /opt/venv /opt/venv

# Optimizer package + Bicycle World twin (and tutorial as optional fallback)
COPY optimizer/ /app/optimizer/
COPY projects/bicycle_world/scenarios/current/models/twin/bicycle_factory.xlsx \
     /app/projects/bicycle_world/scenarios/current/models/twin/bicycle_factory.xlsx
COPY projects/tutorial/models/twin/mini_model.xlsx \
     /app/projects/tutorial/models/twin/mini_model.xlsx

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# Cloud Run injects PORT; entrypoint always puts /app on sys.path before import
CMD ["python", "-m", "optimizer.api.entrypoint"]
