#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$ROOT"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

RESULT_JSON="$("$PYTHON_BIN" schedule_tasks.py next-entry)"

if echo "$RESULT_JSON" | grep -q '"skip"'; then
  echo "Already sent or no entry. ($RESULT_JSON)"
  exit 0
fi

SELECTOR="$(RESULT_JSON="$RESULT_JSON" "$PYTHON_BIN" - <<'PY'
import json, os
print(json.loads(os.environ["RESULT_JSON"])["selector"])
PY
)"

TARGET_DATE="$(RESULT_JSON="$RESULT_JSON" "$PYTHON_BIN" - <<'PY'
import json, os
print(json.loads(os.environ["RESULT_JSON"])["date"])
PY
)"

WEEKDAY_LABEL="$(RESULT_JSON="$RESULT_JSON" "$PYTHON_BIN" - <<'PY'
import json, os
print(json.loads(os.environ["RESULT_JSON"]).get("weekday", ""))
PY
)"

export EZOE_SELECTOR="$SELECTOR"

echo "Sending for $TARGET_DATE ($WEEKDAY_LABEL) selector: $EZOE_SELECTOR"

if "$PYTHON_BIN" sjzl_daily_email.py; then
  "$PYTHON_BIN" schedule_tasks.py mark-sent --date "$TARGET_DATE"
else
  exit 1
fi
