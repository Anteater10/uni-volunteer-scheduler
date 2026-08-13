# backend/Dockerfile
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# build-essential: tools for building some wheels
# procps: pgrep for the celery_beat container healthcheck
RUN apt-get update && apt-get install -y build-essential procps && rm -rf /var/lib/apt/lists/*

# Install Python deps. BASE-CONFIG-33: requirements.lock.txt is the full
# transitive set captured from a known-good build; requirements.txt pins only the
# packages we chose, so building from it lets ~55 transitives float and two
# builds of the same commit can differ. Prefer the lock, fall back to the loose
# file so this Dockerfile still works if the lock is ever missing.
COPY requirements.txt requirements.lock.txt /app/
RUN if [ -s /app/requirements.lock.txt ]; then \
        echo "installing from requirements.lock.txt (pinned)"; \
        pip install --no-cache-dir -r /app/requirements.lock.txt; \
    else \
        echo "WARNING: no lockfile — installing from requirements.txt (floating)"; \
        pip install --no-cache-dir -r /app/requirements.txt; \
    fi

# BASE-CONFIG-02: bake the local model weights into the image instead of
# downloading ~1.3GB from huggingface.co on the first request of every fresh
# container. World-readable and outside /home so it survives a USER change and
# is shared by the api, worker and beat containers built from this image.
#
# Placed before `COPY . /app` deliberately: this layer is keyed on
# requirements.txt, so editing application code does not re-download the
# weights. Pass --build-arg BAKE_MODEL_WEIGHTS=0 for a fast build that skips
# them — the app still works, it just downloads them at runtime again.
ENV HF_HOME=/opt/hf-cache
ARG BAKE_MODEL_WEIGHTS=1
COPY scripts/prefetch_models.py /app/scripts/prefetch_models.py
COPY app/config.py /app/app/config.py
RUN if [ "$BAKE_MODEL_WEIGHTS" = "1" ]; then \
        DATABASE_URL=postgresql://unused JWT_SECRET=unused \
        python scripts/prefetch_models.py; \
    else \
        echo "skipping model prefetch (BAKE_MODEL_WEIGHTS=$BAKE_MODEL_WEIGHTS)"; \
    fi \
    && chmod -R a+rX /opt/hf-cache 2>/dev/null || true

# Copy backend source
COPY . /app

# Non-root runtime user. uid 1000 matches the typical host uid so the
# bind-mounted test harness keeps working.
RUN useradd --uid 1000 --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Run FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
