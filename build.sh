#!/usr/bin/env bash
# Render build step: install, collect static files, update the database, make sure the owner account exists.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py setup_store
