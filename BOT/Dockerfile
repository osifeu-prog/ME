# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
ENV FLASK_ENV=production

# לפני הרצת gunicorn, נקבע את ה‑webhook דרך ENTRYPOINT script
# אבל לשמירה על פשטות נשתמש ב‑gunicorn שמריץ את app
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "bot:app", "--workers", "3", "--timeout", "120"]
