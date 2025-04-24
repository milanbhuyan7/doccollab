#!/bin/bash

# Start script for the DocCollab application
# This script starts the Daphne server for WebSocket support

# Set environment variables
export DJANGO_SETTINGS_MODULE=doccollab.settings

# Install dependencies if needed
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start Daphne server
echo "Starting Daphne server for WebSocket support..."
daphne -b 0.0.0.0 -p 8000 doccollab.asgi:application
