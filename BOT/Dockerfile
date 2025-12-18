FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# פורט פנימי שה‑Gunicorn מאזין אליו
ENV PORT=8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app", "--workers", "3", "--timeout", "120"]
