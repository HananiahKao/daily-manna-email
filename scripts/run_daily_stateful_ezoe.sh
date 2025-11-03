#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/hananiah/Developer/daily-manna-email"
VENV_PY="$REPO_DIR/.venv/bin/python"
ENV_FILE="$REPO_DIR/.env"
cd "$REPO_DIR"

# Load environment
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

RESULT_JSON="$($VENV_PY schedule_tasks.py next-entry)"

if echo "$RESULT_JSON" | grep -q '"skip"'; then
  echo "Already sent or no entry. ($RESULT_JSON)"
  exit 0
fi

SELECTOR="$($VENV_PY - <<'PY'
import json, sys
data = json.loads(sys.stdin.read())
print(data["selector"])
PY <<<"$RESULT_JSON")"

TARGET_DATE="$($VENV_PY - <<'PY'
import json, sys
data = json.loads(sys.stdin.read())
print(data["date"])
PY <<<"$RESULT_JSON")"

WEEKDAY_LABEL="$($VENV_PY - <<'PY'
import json, sys
data = json.loads(sys.stdin.read())
print(data.get("weekday", ""))
PY <<<"$RESULT_JSON")"

export EZOE_SELECTOR="$SELECTOR"

echo "Sending for $TARGET_DATE ($WEEKDAY_LABEL) selector: $EZOE_SELECTOR"

if "$VENV_PY" sjzl_daily_email.py; then
  "$VENV_PY" schedule_tasks.py mark-sent --date "$TARGET_DATE"
else
  exit 1
fi
