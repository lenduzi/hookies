#!/usr/bin/env bash
# Start both FastAPI backend and Next.js frontend in one terminal.
# Usage: ./dev.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting Hookies dev servers..."
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo ""

# Trap SIGINT so both child processes die on Ctrl-C
trap "kill 0" INT

# FastAPI
"$ROOT/.venv/bin/uvicorn" api.server:app --reload --host 0.0.0.0 --port 8000 &

# Next.js
cd "$ROOT/frontend" && npm run dev -- --port 3000 &

wait
