# Stage 1: build
FROM python:3.11-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc libffi-dev libssl-dev ca-certificates \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install --prefix=/install --no-cache-dir -r /app/requirements.txt \
  && rm -rf /var/lib/apt/lists/*

# Stage 2: runtime
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# העתק חבילות מהשלב הקודם
COPY --from=build /install /usr/local

# העתק קוד
COPY . /app

# PATH לוודא שהבינארים נגישים
ENV PATH="/usr/local/bin:/root/.local/bin:${PATH}"
ENV PORT=8080

# סקריפט start: מדפיס מידע דיבאג ואז מריץ gunicorn
RUN printf '#!/bin/sh\n' > /app/start.sh \
  && printf 'echo \"=== DEBUG: which python ===\"; which python || true\n' >> /app/start.sh \
  && printf 'echo \"=== DEBUG: python -m pip show flask ===\"; python -m pip show flask || true\n' >> /app/start.sh \
  && printf 'echo \"=== DEBUG: python -m pip list | grep -E \\\"Flask|gunicorn\\\" ===\"; python -m pip list --disable-pip-version-check | grep -E \"Flask|gunicorn\" || true\n' >> /app/start.sh \
  && printf 'echo \"=== DEBUG: ls /usr/local/lib/python3.11/site-packages | head -n 50 ===\"; ls -la /usr/local/lib/python3.11/site-packages | head -n 50 || true\n' >> /app/start.sh \
  && printf 'echo \"=== STARTING gunicorn ===\"\n' >> /app/start.sh \
  && printf 'exec python -m gunicorn --bind 0.0.0.0:${PORT} bot:app --workers 2 --timeout 30\n' >> /app/start.sh \
  && chmod +x /app/start.sh

# הפעלת הסקריפט (שידפיס ל־Deploy Logs ואז יריץ את השרת)
CMD ["/app/start.sh"]
