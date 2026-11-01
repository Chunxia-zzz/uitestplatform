#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

(cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload --port 8000) &
./.venv/bin/python scripts/serve_fixtures.py &
(cd frontend && npm run dev) &

echo "后端 http://127.0.0.1:8000/docs"
echo "前端 http://localhost:5173"
echo "fixture http://127.0.0.1:8899/login.html"
wait
