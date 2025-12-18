# Stage 1: build
FROM python:3.11-slim AS build
WORKDIR /app
COPY requirements.txt /app/
RUN apt-get update && apt-get install -y build-essential gcc libssl-dev \
 && python -m pip install --upgrade pip setuptools wheel \
 && python -m pip install --prefix=/install -r requirements.txt

# Stage 2: runtime
FROM python:3.11-slim
WORKDIR /app
COPY --from=build /install /usr/local
COPY . /app
ENV PATH="/usr/local/bin:${PATH}"
CMD ["gunicorn","--bind","0.0.0.0:$PORT","bot:app","--workers","2"]
