# backend/Dockerfile
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# build-essential: tools for building some wheels
# procps: pgrep for the celery_beat container healthcheck
RUN apt-get update && apt-get install -y build-essential procps && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source
COPY . /app

# Non-root runtime user. uid 1000 matches the typical host uid so the
# bind-mounted test harness keeps working. The home dir holds the HF model
# cache that sentence-transformers downloads at runtime.
RUN useradd --uid 1000 --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Run FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
