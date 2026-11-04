#!/usr/bin/env bash
# Local equivalent of .github/workflows/ci.yml (backend + frontend gates).
# Usage: bash scripts/ci_local.sh            # same checks as CI jobs
#        bash scripts/ci_local.sh --with-e2e # additionally run smokes (services must be up)
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/.venv/Scripts/python.exe"
  BIN="$ROOT/.venv/Scripts"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
  BIN="$ROOT/.venv/bin"
else
  PY="$(command -v python3 || command -v python)"
  BIN="$(dirname "$(command -v python3 || command -v python)")"
fi
LINT="$BIN/lint-imports"
ALEMBIC="$BIN/alembic"
if [ -x "$BIN/lint-imports.exe" ]; then LINT="$BIN/lint-imports.exe"; fi
if [ -x "$BIN/alembic.exe" ]; then ALEMBIC="$BIN/alembic.exe"; fi

echo "== backend: pytest =="
( cd backend && "$PY" -m pytest -q )

echo "== backend: import-linter =="
( cd backend && "$LINT" )

echo "== backend: alembic fresh-db check =="
(
  cd backend
  rm -f data/ci_local.db
  mkdir -p data
  export UIP_DATABASE_URL="sqlite+aiosqlite:///./data/ci_local.db"
  "$ALEMBIC" upgrade head >/dev/null
  "$ALEMBIC" check
  rm -f data/ci_local.db
)

echo "== frontend: vue-tsc + build =="
( cd frontend && npm run build )

if [ "${1:-}" = "--with-e2e" ]; then
  echo "== e2e: smokes (requires backend :8000 + fixtures :8899) =="
  "$PY" scripts/smoke_m3.py
  "$PY" scripts/smoke_m32.py
  "$PY" scripts/smoke_m34.py
  "$PY" scripts/smoke_m35.py
fi

echo "OK: local CI checks passed"
