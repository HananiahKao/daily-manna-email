Daily Manna Email

- Original link behavior (ezoe selector mode):
  - The email footer includes “原文連結” pointing to the canonical page on ezoe.work.
  - It deep-links to the day section using anchors `#1_6`..`#1_12` mapping 周一..主日.
  - Example: selector `2-1-3` → `https://ezoe.work/books/2/2264-2-1.html#1_8` (周三).
  - If parsing fails, falls back to the non-anchored URL.

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
```

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
