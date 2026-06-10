#!/usr/bin/env bash
# Start the vocab flashcard app with hot reload + phone access.
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi
exec uvicorn app:app --host 0.0.0.0 --port 8000 --reload
