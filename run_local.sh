#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

PY="/opt/homebrew/bin/python3.12"
PORT="${PORT:-8000}"

echo "== Repo: $REPO"

# 0) Ensure correct python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY not found."
  echo "Install it with: brew install python@3.12"
  exit 1
fi
echo "== Python: $("$PY" --version)"

# 1) Recreate venv (clean + repeatable)
echo "== Recreating .venv"
rm -rf .venv
"$PY" -m venv .venv
source .venv/bin/activate

# 2) Upgrade tooling + install deps
python -m ensurepip --upgrade
python -m pip install -U pip setuptools wheel
pip install -r requirements.txt

# 3) Load env (prefer .env if present)
export APP_ENV="${APP_ENV:-local}"
if [[ -f ".env" ]]; then
  echo "== Loading .env"
  set -a
  source .env
  set +a
else
  echo "== No .env found (APP_ENV=$APP_ENV)."
fi

# 4) Run API (watch ONLY app/ to avoid .venv reload loops)
echo "== Starting API on http://127.0.0.1:$PORT"
exec uvicorn app.main:app --reload --reload-dir app --port "$PORT"

