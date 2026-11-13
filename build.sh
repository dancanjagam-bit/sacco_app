#!/usr/bin/env bash
# Railway build script — runs before the app starts

set -e   # exit on any error

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Building React frontend ==="
cd frontend
npm install --legacy-peer-deps
npm run build
cd ..

echo "=== Collecting Django static files ==="
python manage.py collectstatic --noinput

echo "=== Running database migrations ==="
python manage.py migrate --noinput

echo "=== Build complete ==="
