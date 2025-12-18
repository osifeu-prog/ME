# Stage 1: build
FROM python:3.11-slim AS build
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --prefix=/install --no-cache-dir -r /app/requirements.txt \
  && rm -rf /var/lib/apt/lists/*

# Stage 2: runtime
FROM python:3.11-slim
WORKDIR /app
COPY --from=build /install /usr/local
COPY . /app
ENV PATH="/usr/local/bin:${PATH}"
ENV PORT=8080
CMD sh -c "python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30"
