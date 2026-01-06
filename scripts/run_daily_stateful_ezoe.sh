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

CONTENT_SOURCE="$(RESULT_JSON="$RESULT_JSON" "$PYTHON_BIN" - <<'PY'
import json, os
print(json.loads(os.environ["RESULT_JSON"]).get("content_source", "ezoe"))
PY
)"

export EZOE_SELECTOR="$SELECTOR"

echo "Sending for $TARGET_DATE ($WEEKDAY_LABEL) selector: $EZOE_SELECTOR from $CONTENT_SOURCE"

if "$PYTHON_BIN" sjzl_daily_email.py; then
  # Enhanced JSON output for web app monitoring
  cat <<EOF
{
  "job_type": "daily_email_send",
  "status": "success",
  "date": "$TARGET_DATE",
  "weekday": "$WEEKDAY_LABEL",
  "selector": "$SELECTOR",
  "content_source": "$CONTENT_SOURCE",
  "timestamp": "$(date -Iseconds)",
  "details": {
    "action": "sent_daily_email",
    "recipient_count": "configured_via_env",
    "content_type": "daily_devotional"
  }
}
EOF
  "$PYTHON_BIN" schedule_tasks.py mark-sent --date "$TARGET_DATE"
else
  # Enhanced error JSON output
  cat <<EOF
{
  "job_type": "daily_email_send",
  "status": "failed",
  "date": "$TARGET_DATE",
  "weekday": "$WEEKDAY_LABEL",
  "selector": "$SELECTOR",
  "content_source": "$CONTENT_SOURCE",
  "timestamp": "$(date -Iseconds)",
  "error": "email_send_failed",
  "details": {
    "exit_code": $?,
    "action": "attempted_send"
  }
}
EOF
  exit 1
fi
