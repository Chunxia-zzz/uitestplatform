#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python_bin="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  echo "==> 创建虚拟环境 .venv"
  "$python_bin" -m venv .venv
fi

echo "==> 安装后端依赖"
./.venv/bin/python -m pip install --upgrade pip --quiet
./.venv/bin/python -m pip install -r backend/requirements.txt

echo "==> 安装 Playwright Chromium"
./.venv/bin/python -m playwright install chromium

echo "==> 安装前端依赖"
(cd frontend && npm install)

echo
echo "完成。下一步："
echo "  cd backend && ../.venv/bin/python -m app.cli seed-demo"
echo "  ./scripts/dev.sh"
