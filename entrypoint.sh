#!/bin/sh

set -e

DB_URL="${DATABASE_URL:-$DATABASE_BASE_URL}"

if echo "$DB_URL" | grep -q "postgre"; then
    echo "Waiting for PostgreSQL..."
    
    DB_HOST=$(echo "$DB_URL" | sed -e 's/.*@\([^:\/]*\).*/\1/')
    DB_PORT=$(echo "$DB_URL" | sed -e 's/.*:\([0-9]*\)\/.*/\1/')
    DB_PORT="${DB_PORT:-5432}"
    
    while ! nc -z "$DB_HOST" "$DB_PORT"; do
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