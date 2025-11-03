#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/hananiah/Developer/daily-manna-email"
VENV_PY="$REPO_DIR/.venv/bin/python"
ENV_FILE="$REPO_DIR/.env"

cd "$REPO_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

echo "Preparing upcoming week schedule and emailing summary..."
"$VENV_PY" schedule_tasks.py ensure-week --email
