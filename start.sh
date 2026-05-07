#!/usr/bin/env bash
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Starting Bulk Content Generator on http://localhost:8000"
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
