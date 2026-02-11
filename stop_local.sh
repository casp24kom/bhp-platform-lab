#!/usr/bin/env bash
set -euo pipefail
PORT="${PORT:-8000}"
PID="$(lsof -ti :$PORT || true)"
if [[ -z "${PID}" ]]; then
  echo "Nothing listening on port $PORT"
  exit 0
fi
echo "Killing PID(s) on port $PORT: $PID"
kill -9 $PID || true
