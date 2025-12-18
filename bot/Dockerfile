FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install uvicorn[standard]

COPY . .

CMD uvicorn bot:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers
