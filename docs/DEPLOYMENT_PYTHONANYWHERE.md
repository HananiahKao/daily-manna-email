# Deploying on PythonAnywhere

These steps assume you have a **paid** PythonAnywhere account (cron multiples, always-on tasks, and unrestricted email access require it).

## 1. Clone the repo & install dependencies

```bash
git clone <repo-url> ~/daily-manna-email
cd ~/daily-manna-email
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy your production `.env` into `~/daily-manna-email/.env`. The helper scripts export everything automatically.

Add the following to `~/.bashrc` (or to the virtualenv’s `postactivate`) so every console/task inherits the timezone and `.env`:

```bash
export TZ="Asia/Taipei"
set -a; source ~/daily-manna-email/.env; set +a
```

## 2. Provision the FastAPI dashboard (ASGI beta)

1. Install the PythonAnywhere CLI inside the virtualenv:
   ```bash
   pip install --upgrade pythonanywhere
   ```
2. Request ASGI access if you don’t already have it (Dashboard → “Send feedback”).
3. Create the ASGI site (replace `YOURNAME`):
   ```bash
   pa website create --domain YOURNAME.pythonanywhere.com \
     --command "/home/YOURNAME/daily-manna-email/.venv/bin/uvicorn \
                --app-dir /home/YOURNAME/daily-manna-email/app \
                --uds ${DOMAIN_SOCKET} main:app"
   ```

Reload with `pa website reload --domain …` whenever you deploy.

Logs live in `/var/log/YOURNAME.pythonanywhere.com.{error,server,access}.log`.

## 3. Scheduled job via the dispatcher

Use the dispatcher wrapper so one cron entry can drive all the automation.

1. Open the **Tasks** tab → “Add a scheduled task”.
2. Command:
   ```
   bash -lc 'cd ~/daily-manna-email && scripts/run_dispatcher.sh'
   ```
3. Schedule it every 10 minutes (or tighter if you prefer). The default dispatcher rules trigger:
   - Daily send at 06:00 Taiwan (`scripts/run_daily_stateful_ezoe.sh`)
   - Weekly summary each Sunday 21:00 Taiwan (`scripts/run_weekly_schedule_summary.sh`)

To customize timings/behaviour, create `state/dispatch_rules.json` with the format documented in `README.md`, then redeploy. For local testing, run `scripts/run_dispatcher.sh --dry-run`.

## 4. Always-on task for Gmail API replies

From the Tasks tab, create an **Always-on task** with the command:

```
bash -lc 'cd ~/daily-manna-email && scripts/run_schedule_reply_processor.sh --limit 10'
```

It will poll Gmail API hourly by default (set `DISPATCH_CONFIG`/`dispatch_rules` if you want to route it through the dispatcher instead). Always-on tasks auto-restart after maintenance and when CPU seconds reset.

## 5. Daily operations

- `~/daily-manna-email/state/` contains the schedule JSON, weekly summaries, reply reports, etc. Back it up periodically.
- Use `tail -f /var/log/alwayson-log-*.log` to watch the always-on processor.
- `scripts/run_dispatcher.sh --show-config` reveals the currently loaded rules; edit `state/dispatch_state.json` only if you need to reset run timestamps.
- To test emails manually:
  ```bash
  cd ~/daily-manna-email
  source .venv/bin/activate
  RUN_FORCE=1 scripts/run_daily_stateful_ezoe.sh
  ```

## 6. Updating code

```
cd ~/daily-manna-email
git pull
source .venv/bin/activate
pip install -r requirements.txt
pa website reload --domain YOURNAME.pythonanywhere.com
```

The dispatcher + always-on tasks automatically pick up new code on the next run because they always `cd` into the repo before executing.
