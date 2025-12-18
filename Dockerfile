# Stage 1: build stage — התקנת תלויות ובניית חבילות
FROM python:3.11-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# העתק קובץ הדרישות בלבד כדי לנצל cache של Docker
COPY requirements.txt /app/requirements.txt

# התקנת כלי בנייה נחוצים, שדרוג pip והתקנת חבילות לתיקיית /install
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --prefix=/install --no-cache-dir -r /app/requirements.txt \
  && rm -rf /var/lib/apt/lists/*

# Stage 2: runtime stage — תמונה נקייה להרצה
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# העתק את החבילות שהותקנו מהשלב הקודם למערכת
COPY --from=build /install /usr/local

# העתק את שאר קבצי האפליקציה
COPY . /app

# ודא ש‑/usr/local/bin ב‑PATH; זה המקום שבו pip עם --prefix מתקין בינארים
ENV PATH="/usr/local/bin:${PATH}"

# ברירת מחדל לפורט לבדיקה מקומית; Railway יספק PORT בזמן ריצה
ENV PORT=8080

# השתמש ב‑sh -c כדי לאפשר הרחבת $PORT בזמן הריצה
CMD sh -c "python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30"
