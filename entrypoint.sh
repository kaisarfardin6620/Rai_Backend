#!/bin/sh

set -e

if echo "$DATABASE_BASE_URL" | grep -q "postgre"; then
    echo "Waiting for PostgreSQL..."
    
    while ! nc -z db 5432; do
      sleep 0.5
    done
    echo "PostgreSQL started"
fi

if echo "$@" | grep -q "gunicorn"; then
    echo "Running initialization tasks for Web Container..."
    
    echo "Applying migrations..."
    python manage.py migrate --noinput

    echo "Collecting static files..."
    python manage.py collectstatic --noinput --clear
fi

exec "$@"