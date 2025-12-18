# Dockerfile - מבוסס על python:3.11-slim
FROM python:3.11-slim

# שיפור: עדכון pip והתקנת build-essential במידת הצורך
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# העתקת קובץ התלויות והתקנה
COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev libssl-dev \
  && python -m pip install --upgrade pip setuptools wheel \
  && pip install --no-cache-dir -r /app/requirements.txt \
  && apt-get remove -y build-essential gcc \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# העתקת שאר הקוד
COPY . /app

# השתמש ב‑PORT שמסופק על ידי Railway
ENV PORT=8080

# הפקודה שתופעל בתוך הקונטיינר; gunicorn צריך להיות מותקן דרך requirements.txt
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "bot:app", "--workers", "2", "--timeout", "30"]
