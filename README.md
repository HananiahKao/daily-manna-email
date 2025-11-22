Daily Manna Email

- Original link behavior (ezoe selector mode):
  - The email footer includes "原文連結" pointing to the canonical page on ezoe.work.
  - It deep-links to the day section using anchors `#1_6`..`#1_12` mapping 周一..主日.
  - Example: selector `2-1-3` → `https://ezoe.work/books/2/2264-2-1.html#1_8` (周三).
  - If parsing fails, falls back to the non-anchored URL.

### Content Source Switching (OCP-Compliant Architecture)

- Supports multiple content sources while maintaining backward compatibility.
- Set `CONTENT_SOURCE=ezoe` (default) for existing ezoe.work content, or `CONTENT_SOURCE=wix` for Wix site "Morning Revival".
- The system uses an abstraction layer (`content_source.py`) with factory pattern for easy extension to new sources.
- When `CONTENT_SOURCE=wix`, the selector becomes Chinese weekday (e.g., `【週三】`) instead of volume-lesson-day triplet.

## Schedule-driven workflow

- Active schedule is stored at `state/ezoe_schedule.json` (override with `SCHEDULE_FILE`).
- Use `schedule_tasks.py next-entry` to discover which selector should send on a given day.
- Use `schedule_tasks.py mark-sent --date YYYY-MM-DD` after a successful delivery (the daily runner does this automatically).
- Optional overrides: set `EZOE_SEND_WEEKDAY` (e.g. `週三`, `Wed`) or `EZOE_SEND_DATE` (e.g. `2025-05-01`) before running the daily script to pick a different day. Overrides are resolved against Taiwan time and roll forward to the next matching weekday.
- The first seed selector comes from existing schedule entries; otherwise defaults to the env trio `EZOE_VOLUME`, `EZOE_LESSON`, `EZOE_DAY_START` (defaults `2/1/1`).

### Daily send

- Regular job: `scripts/run_daily_stateful_ezoe.sh`
  - Sources `.env`, queries `schedule_tasks.py next-entry`, exports `EZOE_SELECTOR`, runs `sjzl_daily_email.py`, then marks the day as sent.
  - Skip logic: if the day is already marked `sent` and `RUN_FORCE` is empty → job exits early. Set `RUN_FORCE=1` to resend the same selector.

### Weekly summary (cron on Sunday, Taiwan time)

- `scripts/run_weekly_schedule_summary.sh`
  - Ensures the upcoming Monday→Sunday range exists.
  - Renders HTML + plain text summary, saves it to `state/last_schedule_summary.html`.
  - Emails the admin distribution list when `ADMIN_SUMMARY_TO` is configured (comma-separated). Optional helpers: `ADMIN_SUMMARY_FROM`, `ADMIN_SUMMARY_SUBJECT_PREFIX` (default `[DailyManna]`).
  - Summary output now includes per-entry reply tokens to support the beta reply-editing flow.

### Reply editing (beta)

- Each Sunday summary lists a `Token` column alongside selector details plus a reminder of the reply syntax (`[TOKEN] move 2025-06-03`, `note ...`, `skip ...`).
- Pipe the admin's email body into `./schedule_tasks.py apply-reply` (or use `--input path/to/message.txt`) to apply the requested adjustments.
- Supported verbs today: `keep`, `skip`, `move <ISO date>`, `selector <v-l-d>`, `note <text>`, `status <value>`, `override <descriptor>`.
- The workflow is still in flux; expect UX polish and confirmation emails in a later pass.

### Automated reply processing (IMAP)

- Configure IMAP access (typically Gmail): `IMAP_HOST` (default `imap.gmail.com`), `IMAP_PORT` (default `993`), `IMAP_USER`, `IMAP_PASSWORD`, and optional `IMAP_MAILBOX`.
- Allowed admin senders come from `ADMIN_REPLY_FROM` (comma-separated). When unset, `ADMIN_SUMMARY_TO` is used.
- Confirmation emails go to `ADMIN_REPLY_CONFIRMATION_TO` when present, otherwise `ADMIN_SUMMARY_TO`.
- Run `scripts/run_schedule_reply_processor.sh` (cron-friendly) or invoke the Python CLI directly: `scripts/process_schedule_replies.py --limit 5`.
- The processor reads unseen replies, applies commands via `schedule_tasks.py apply-reply`, stores a JSON report at `state/last_reply_results.json`, and emails a confirmation summary (applied vs. rejected commands) back to the admin.

### Dispatcher (single cron entry)

- `python job_dispatcher.py`
  - Evaluates the current Taiwan time and fans out to the daily send, weekly summary, or any custom combo you define.
  - Default rules (when `state/dispatch_rules.json` is absent):
    - `daily-send`: every day at 06:00 Taiwan → `bash scripts/run_daily_stateful_ezoe.sh`
    - `weekly-summary`: Sundays at 21:00 Taiwan → `bash scripts/run_weekly_schedule_summary.sh`
  - The dispatcher persists state in `state/dispatch_state.json` so each rule fires once per window even if the cron job runs every few minutes.
  - Override or extend the behavior by creating `state/dispatch_rules.json` with content like:
    ```json
    [
      {
        "name": "weekday-send",
        "time": "06:00",
        "days": ["mon","tue","wed","thu","fri","sat"],
        "commands": [
          ["bash", "scripts/run_daily_stateful_ezoe.sh"]
        ]
      },
      {
        "name": "sunday-combo",
        "time": "06:00",
        "days": ["sun"],
        "commands": [
          ["bash", "scripts/run_weekly_schedule_summary.sh"],
          ["bash", "scripts/run_daily_stateful_ezoe.sh"]
        ]
      }
    ]
    ```
  - Any command entry can be either an argv array (preferred) or a shell string (it is wrapped with `bash -lc ...` automatically).
  - Cron example (UTC every 10 minutes): `*/10 * * * * cd /app && python job_dispatcher.py`
  - Use `python job_dispatcher.py --dry-run` to verify what would run, or `--show-config` to print the currently active rules.
- Production cron wrappers can call `scripts/run_dispatcher.sh`, which already activates the virtualenv and sources `.env`.
- A more advanced sample config lives at `docs/dispatch_rules.example.json`.

### Admin CLI quick reference

```
# Inspect next selector (honours overrides/EZOE_SEND_WEEKDAY)
./schedule_tasks.py next-entry

# Mark a given day as sent manually
./schedule_tasks.py mark-sent --date 2025-05-01

# Ensure the next weekly window without emailing
./schedule_tasks.py ensure-week

# Ensure the week starting from a specific Monday and email summary
./schedule_tasks.py ensure-week --start 2025-05-12 --email

# Apply admin reply commands (reads from stdin)
./schedule_tasks.py apply-reply < admin_reply.txt

# Process admin reply emails via IMAP (reads credentials from env)
scripts/run_schedule_reply_processor.sh --limit 5
```

### Admin dashboard (FastAPI)

- Set `ADMIN_DASHBOARD_PASSWORD` (required) and optionally `ADMIN_DASHBOARD_USER` (default `admin`).
- Launch locally with `uvicorn app.main:app --host 0.0.0.0 --port 8000` after exporting `.env`.
- Authenticate via HTTP Basic using the configured credentials; the dashboard renders the current week, offers inline actions (mark sent, skip, move, update selector/status/notes/override), and displays flash messages for feedback.
- The application reuses `schedule_manager` state, so edits made through the UI are immediately reflected in the JSON schedule and weekly summaries.

### Deploying on PythonAnywhere

See `docs/DEPLOYMENT_PYTHONANYWHERE.md` for a full walkthrough (virtualenv, ASGI CLI, dispatcher cron, and always-on IMAP processing).

### Migrating from `state/email_progress.json`

If the legacy state file exists, seed the new schedule as follows:

1. Read the current pointer: `cat state/email_progress.json` (values correspond to the next selector the old script would use).
2. Export matching env vars, e.g.:
   ```
   export EZOE_VOLUME=3
   export EZOE_LESSON=13
   export EZOE_DAY_START=3
   ```
3. Ensure the upcoming week: `./schedule_tasks.py ensure-week`
4. Verify the next send: `./schedule_tasks.py next-entry`

Once the schedule file exists, the legacy `state/email_progress.json` can be ignored.

## Testing

- Force a send for testing: `RUN_FORCE=1 scripts/run_daily_stateful_ezoe.sh`.
- Check logs for: `Original link (anchored): <url>`.
