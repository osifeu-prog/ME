# Dockerfile for Railway — reliable install and runtime
FROM python:3.11-slim

# Basic env
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy requirements early to leverage Docker cache
COPY requirements.txt /app/requirements.txt

# Install system deps, upgrade pip, install gunicorn and requirements
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --no-cache-dir gunicorn==20.1.0 \
  && python -m pip install --no-cache-dir -r /app/requirements.txt \
  && apt-get remove -y build-essential gcc \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . /app

# Ensure user-base bin is in PATH in case pip used user install
ENV PATH="/root/.local/bin:${PATH}"

# Default PORT for local testing; Railway will override with its env
ENV PORT=8080

# Use shell form so $PORT is expanded by sh when Railway runs the container
CMD sh -c "python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30"
