#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
    echo "Virtual environment missing. Run scripts/setup.sh first." >&2
    exit 1
fi

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

PORT="${PORT:-8000}"
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
