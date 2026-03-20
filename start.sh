#!/bin/bash
# Start CRM On-Call RAG Assistant (backend + frontend)
# Run from: oncall-rag-assistant/

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== Backend ==="
cd backend
if [ ! -d venv ]; then
  echo "Creating venv..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
echo "Starting backend on http://127.0.0.1:8000 ..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

BACKEND_PID=$!
cd "$ROOT"

echo "=== Frontend ==="
cd frontend
[ ! -d node_modules ] && npm install
echo "Starting frontend on http://127.0.0.1:3000 ..."
npm run dev &

FRONTEND_PID=$!
cd "$ROOT"

echo ""
echo "App is starting. Open: http://localhost:3000"
echo "Backend API: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
