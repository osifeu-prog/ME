FROM python:3.11-slim AS build
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --prefix=/install --no-cache-dir -r /app/requirements.txt \
  && rm -rf /var/lib/apt/lists/*

FROM python:3.11-slim
WORKDIR /app
COPY --from=build /install /usr/local
COPY . /app
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"
ENV PORT=8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:${PORT}/health || exit 1
CMD sh -c "python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30"
