# Debug Dockerfile for Railway — prints pip/gunicorn info during build
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && echo "=== INSTALLING gunicorn explicitly ===" \
  && python -m pip install --no-cache-dir gunicorn==20.1.0 || true \
  && echo "=== INSTALLING requirements (prefix=/install) ===" \
  && python -m pip install --prefix=/install --no-cache-dir -r /app/requirements.txt || true \
  && echo "=== PIP LIST ===" \
  && python -m pip list --disable-pip-version-check || true \
  && echo "=== PIP SHOW gunicorn ===" \
  && python -m pip show gunicorn || true \
  && echo "=== which gunicorn ===" \
  && (which gunicorn || echo "gunicorn not in PATH") \
  && echo "=== ls /install/bin ===" \
  && ls -la /install/bin || true \
  && echo "=== ls /usr/local/bin ===" \
  && ls -la /usr/local/bin || true \
  && echo "=== ls /root/.local/bin ===" \
  && ls -la /root/.local/bin || true \
  && apt-get remove -y build-essential gcc \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

COPY . /app

# Ensure common bin locations are in PATH
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"
ENV PORT=8080

# Use shell form so $PORT is expanded at runtime
CMD sh -c "python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30"
