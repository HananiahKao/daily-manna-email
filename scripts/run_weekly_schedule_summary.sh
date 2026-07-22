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

echo "Preparing upcoming week schedule and emailing summary..."

# Get current timestamp for logging
START_TIME="$(date -Iseconds)"

# Run the ensure-week command and capture output
if "$PYTHON_BIN" schedule_tasks.py ensure-week --email; then
  # Enhanced JSON output for successful weekly summary
  cat <<EOF
{
  "job_type": "weekly_schedule_summary",
  "status": "success",
  "timestamp": "$START_TIME",
  "details": {
    "action": "sent_weekly_summary_email",
    "includes_schedule_preview": true,
    "includes_reply_tokens": true,
    "target_recipients": "admin_summary_to"
  },
  "metadata": {
    "start_time": "$START_TIME",
    "end_time": "$(date -Iseconds)",
    "script_version": "1.0"
  }
}
EOF
else
  # Enhanced error JSON output
  cat <<EOF
{
  "job_type": "weekly_schedule_summary",
  "status": "failed",
  "timestamp": "$START_TIME",
  "error": "weekly_summary_failed",
  "details": {
    "action": "attempted_weekly_summary",
    "exit_code": $?
  },
  "metadata": {
    "start_time": "$START_TIME",
    "end_time": "$(date -Iseconds)",
    "script_version": "1.0"
  }
}
EOF
  exit 1
fi
