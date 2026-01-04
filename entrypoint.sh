#!/bin/sh
set -e

# تابع برای اجرای مایگریشن
run_migrations() {
  # فقط اگر متغیر RUN_MIGRATIONS مقدارش false نباشد اجرا شود
  if [ "$RUN_MIGRATIONS" != "false" ]; then
      echo "Running migrations..."
      python manage.py migrate --noinput

      echo "Collecting static files..."
      python manage.py collectstatic --noinput
  else
      echo "Skipping migrations (RUN_MIGRATIONS is set to false)"
  fi
}

echo "Waiting for postgres..."
while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.1
done
echo "PostgreSQL started"

run_migrations

exec "$@"