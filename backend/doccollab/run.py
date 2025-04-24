#!/usr/bin/env python
"""
Run script for the DocCollab application.
This script starts the Daphne server for WebSocket support.
"""
import os
import sys
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Run the application with Daphne for WebSocket support."""
    print("Starting DocCollab with Daphne for WebSocket support...")
    
    # Set the Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'doccollab.settings')
    
    # Run database migrations
    print("Running database migrations...")
    subprocess.run([sys.executable, "manage.py", "migrate"], check=True)
    
    # Start Daphne server
    print("Starting Daphne server...")
    daphne_cmd = [
        "daphne",
        "-b", "0.0.0.0",  # Bind to all interfaces
        "-p", "8000",     # Port 8000
        "doccollab.asgi:application"
    ]
    
    subprocess.run(daphne_cmd, check=True)

if __name__ == "__main__":
    main()
