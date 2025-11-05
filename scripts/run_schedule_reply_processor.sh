#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ROOT/.env"
  set +a
fi

cd "$ROOT"
python3 scripts/process_schedule_replies.py "$@"
