FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# העתק את requirements לפני התקנת חבילות כדי לנצל cache של Docker
COPY requirements.txt /app/requirements.txt

# התקנת תלויות מערכת נחוצות, עדכון pip והתקנת חבילות (כולל gunicorn)
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --no-cache-dir gunicorn==20.1.0 \
  && python -m pip install --no-cache-dir -r /app/requirements.txt \
  && apt-get remove -y build-essential gcc \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# העתק שאר הקוד
COPY . /app

# אם pip בכל זאת התקין חבילות ל־~/.local, ודא שהבינארים שם זמינים ב‑PATH
ENV PATH
