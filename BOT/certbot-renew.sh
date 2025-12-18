#!/bin/bash
set -e

DOMAIN="web-production-112f6.up.railway.app"
EMAIL="you@example.com"

# בקשת תעודה ראשונית (הרץ פעם אחת לפני הפעלת ה‑compose במצב מלא)
docker-compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
  -d ${DOMAIN} --email ${EMAIL} --agree-tos --no-eff-email" certbot

# טען מחדש nginx
docker-compose exec nginx nginx -s reload
