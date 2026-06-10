#!/usr/bin/env bash
# Start the vocab flashcard app with hot reload + phone access.
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi
# Load secrets from .env (gitignored) so the API key never sits in
# shell history. Create it with: echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
# VOCAB_HOST=127.0.0.1 ./run.sh  → localhost only (no LAN/phone access)
exec uvicorn app:app --host "${VOCAB_HOST:-0.0.0.0}" --port 8000 --reload
