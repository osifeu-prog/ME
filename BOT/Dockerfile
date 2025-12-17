FROM python:3.11-slim

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy application (diagnostics or bot)
COPY bot.py .

ENV PYTHONUNBUFFERED=1

# default command; Railway will pass $PORT at runtime via Start command
CMD ["uvicorn", "bot:app", "--host", "0.0.0.0", "--port", "8000"]
