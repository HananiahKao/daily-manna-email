#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/hananiah/Developer/daily-manna-email"
VENV_PY="$REPO_DIR/.venv/bin/python"
ENV_FILE="$REPO_DIR/.env"
STATE_FILE_DEFAULT="$REPO_DIR/state/email_progress.json"

cd "$REPO_DIR"

# Load environment
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

# Allow overriding state file via env, else default
STATE_FILE="${STATE_FILE:-$STATE_FILE_DEFAULT}"

# Compute selector from state with inline Python
RESULT_JSON="$($VENV_PY - << 'PY'
import json, os, sys, datetime as dt, pathlib

repo = pathlib.Path(os.getcwd())
state_path = os.environ.get("STATE_FILE", str(repo / "state" / "email_progress.json"))
path = pathlib.Path(state_path)
today = dt.datetime.now().date().isoformat()

# defaults from env
def_env_vol = int(os.environ.get("EZOE_VOLUME", "2"))
def_env_les = int(os.environ.get("EZOE_LESSON", "1"))

state = {"volume": def_env_vol, "lesson": def_env_les, "day": 1, "last_sent_date": ""}
if path.exists():
    try:
        state.update(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        pass

force = os.environ.get("RUN_FORCE", "") not in ("", "0", "false", "False")
if not force and state.get("last_sent_date") == today:
    print(json.dumps({"skip": True, "reason": "already_sent_today", "state_file": state_path}, ensure_ascii=False))
    sys.exit(0)

vol = int(state.get("volume", def_env_vol))
les = int(state.get("lesson", def_env_les))
day = int(state.get("day", 1))

selector = f"{vol}-{les}-{day}"

# advance for next run
day_next = day + 1
les_next, vol_next = les, vol
if day_next > 7:
    day_next = 1
    les_next = les + 1

state_out = {
    "volume": vol_next,
    "lesson": les_next,
    "day": day_next,
    "last_sent_date": today,
    "last_sent_selector": selector,
}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(state_out, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({"selector": selector, "state_file": state_path}, ensure_ascii=False))
PY)"

if echo "$RESULT_JSON" | grep -q '"skip"'; then
  echo "Already sent today; skipping. ($RESULT_JSON)"
  exit 0
fi

SELECTOR="$(echo "$RESULT_JSON" | sed -n 's/.*"selector"[ ]*:[ ]*"\([^"]*\)".*/\1/p')"
export EZOE_SELECTOR="$SELECTOR"

echo "Sending for selector: $EZOE_SELECTOR (state: $(echo "$RESULT_JSON"))"

exec "$VENV_PY" sjzl_daily_email.py

