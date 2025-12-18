# Multi-stage Dockerfile — build dependencies then runtime image
FROM python:3.11-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy only requirements first to leverage cache
COPY requirements.txt /app/requirements.txt

# Install build deps and Python packages into /install
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --prefix=/install --no-cache-dir -r /app/requirements.txt \
  && rm -rf /var/lib/apt/lists/*

# Runtime image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy installed packages from build stage
COPY --from=build /install /usr/local

# Copy application code
COPY . /app

# Ensure common bin locations are in PATH
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"
ENV PORT=8080

# Optional lightweight healthcheck for Docker runtime
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:${PORT}/health || exit 1

# Use shell form so $PORT is expanded by sh at runtime
CMD sh -c "python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30"
