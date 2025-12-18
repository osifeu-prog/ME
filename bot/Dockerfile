FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt /app/requirements.txt

# התקנה עם פקודות דיבאג כדי לראות היכן הותקנו חבילות ובמיוחד gunicorn
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --no-cache-dir gunicorn==20.1.0 || true \
  && python -m pip install --no-cache-dir -r /app/requirements.txt || true \
  && echo "=== PIP LIST ===" \
  && python -m pip list --disable-pip-version-check \
  && echo "=== PIP SHOW gunicorn ===" \
  && python -m pip show gunicorn || true \
  && echo "=== which gunicorn ===" \
  && (which gunicorn || echo "gunicorn not in PATH") \
  && echo "=== ls /root/.local/bin ===" \
  && ls -la /root/.local/bin || true \
  && echo "=== ls /usr/local/bin ===" \
  && ls -la /usr/local/bin || true \
  && apt-get remove -y build-essential gcc \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

COPY . /app

# אם pip התקין ל־user base, ודא שהנתיב כלול
ENV PATH="/root/.local/bin:${PATH}"
ENV PORT=8080

# Exec form — קל יותר לדיבאג ולניהול תהליכים
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "bot:app", "--workers", "2", "--timeout", "30"]
