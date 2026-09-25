#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Backend
cd "$SCRIPT_DIR/backend"
source venv/Scripts/activate
uvicorn app.main:app --reload &
BACKEND_PID=$!

# Frontend
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT INT TERM

echo ""
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop both"
echo ""

wait
