#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "[Project] $(pwd)"

# Try existing .venv first
if [ -f ".venv/bin/python" ]; then
  if .venv/bin/python -c "import sys" 2>/dev/null; then
    .venv/bin/python "scripts/start_best.py"
    exit 0
  fi
  echo "[Warning] Existing .venv is invalid; trying system Python."
fi

# Try system python3
if command -v python3 &>/dev/null; then
  python3 "scripts/setup.py" --mirror https://pypi.tuna.tsinghua.edu.cn/simple
  if [ -f ".venv/bin/python" ]; then
    .venv/bin/python "scripts/start_best.py"
    exit 0
  fi
fi

echo "Python 3.10+ is required. Please install it first."
exit 1
