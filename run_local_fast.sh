#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

PY="/opt/homebrew/bin/python3.12"
PORT="${PORT:-8000}"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY not found. Install with: brew install python@3.12"
  exit 1
fi

echo "== Repo: $REPO"
echo "== Python: $("$PY" --version)"

# 1) Create venv only if missing
if [[ ! -d ".venv" ]]; then
  echo "== Creating .venv"
  "$PY" -m venv .venv
fi

source .venv/bin/activate

# 2) Upgrade tooling (fast, safe)
python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install -U pip setuptools wheel >/dev/null

# 3) Install deps only when needed
#    We create a stamp file based on requirements.txt content.
REQ_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
STAMP_FILE=".venv/.requirements_hash"

NEED_INSTALL="true"
if [[ -f "$STAMP_FILE" ]]; then
  OLD_HASH="$(cat "$STAMP_FILE" || true)"
  if [[ "$OLD_HASH" == "$REQ_HASH" ]]; then
    NEED_INSTALL="false"
  fi
fi

if [[ "$NEED_INSTALL" == "true" ]]; then
  echo "== Installing/Updating requirements (requirements.txt changed or first run)"
  pip install -r requirements.txt
  echo "$REQ_HASH" > "$STAMP_FILE"
else
  echo "== Requirements unchanged (skipping pip install)"
fi

# 4) Load env
export APP_ENV="${APP_ENV:-local}"
if [[ -f ".env" ]]; then
  echo "== Loading .env"
  set -a
  source .env
  set +a
else
  echo "== No .env found (APP_ENV=$APP_ENV)."
fi

# 5) Run API (watch ONLY app/)
echo "== Starting API on http://127.0.0.1:$PORT"
exec uvicorn app.main:app --reload --reload-dir app --port "$PORT"
