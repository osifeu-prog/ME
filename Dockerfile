FROM python:3.11-slim

WORKDIR /app

# system deps (מינימלי)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# העתק קבצים
COPY bot.py .
# אם יש קבצים נוספים: COPY app/ ./app/

ENV PYTHONUNBUFFERED=1

# Start command: uvicorn יקשיב ל-$PORT
CMD ["uvicorn", "bot:app", "--host", "0.0.0.0", "--port", "8000"]
