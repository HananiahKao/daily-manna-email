# System Architecture

## Overview

Daily Manna Email automates the delivery of "聖經之旅" lessons by coordinating scraping, scheduling, email delivery, and admin feedback loops. The system is built as a set of small Python modules and shell wrappers that can be run from cron. Configuration is driven by environment variables, and persistent state is stored under `state/`.

## Runtime Context

```text
Cron/Scheduler
  ├─ scripts/run_daily_stateful_ezoe.sh
  │     ├─ schedule_tasks.py next-entry  ↔ state/ezoe_schedule.json
  │     ├─ export EZOE_SELECTOR
  │     ├─ sjzl_daily_email.py (content fetch + email)
  │     └─ schedule_tasks.py mark-sent
  ├─ scripts/run_weekly_schedule_summary.sh
  │     └─ schedule_tasks.py ensure-week --email
  └─ scripts/run_schedule_reply_processor.sh
        └─ scripts/process_schedule_replies.py
               └─ schedule_reply_fetcher.py → schedule_reply_processor.py
```

All entrypoint scripts source `.env` before execution so SMTP/IMAP credentials and overrides are available in child processes.

## Core Modules

### Scheduling & State Management

- `schedule_manager.py` defines `Schedule`/`ScheduleEntry` dataclasses, Taiwan timezone helpers, and JSON persistence around `state/ezoe_schedule.json` (override with `SCHEDULE_FILE`). It can create future entries, roll over previous selectors, and tracks metadata such as notes, overrides, and sent timestamps.
- `schedule_tasks.py` exposes CLI verbs (`next-entry`, `mark-sent`, `ensure-week`, `apply-reply`) that orchestrate the schedule. It calls into `schedule_manager` to ensure the requested date range exists, issues reply tokens via `schedule_reply`, and renders plain-text + HTML summaries. It also reuses `sjzl_daily_email.send_email` to mail weekly admin summaries.

### Content Retrieval & Rendering

- `sjzl_daily_email.py` drives both lesson discovery and message composition.
  - Default mode discovers the latest lesson on `https://four.soqimp.com/books/2264` and sends a simplified plain-text email.
  - When `EZOE_SELECTOR` is set, it delegates to `ezoe_week_scraper.get_day_html` to pull a specific day from ezoe.work, wraps the returned HTML with scoped CSS, and sends a multipart email (plain-text fallback + rich HTML).
  - Shared helpers handle UTF-8 decoding, optional OpenCC conversion, CSS aggregation, and `send_email`, which configures SMTP via `SMTP_*` and `EMAIL_*` variables.
- `ezoe_week_scraper.py` isolates scraping logic for ezoe.work lessons. It enforces UTF-8 decoding, navigates lesson day anchors, wraps the extracted section with an injected `<h3>` label, and provides suggestions (e.g., next selector) when a day is out of range.

### Email Delivery

- `sjzl_daily_email.send_email()` is the single SMTP integration point. It sends multipart/alternative messages using STARTTLS (default) or SSL and is reused by weekly summaries and IMAP confirmation messages.
- `scripts/run_daily_stateful_ezoe.sh` is the cron-friendly wrapper that sources `.env`, queries `schedule_tasks.py next-entry`, exports `EZOE_SELECTOR`, calls `sjzl_daily_email.py`, and finally marks the entry as sent.

### Admin Summary & Feedback Loop

- `schedule_reply.py` issues short-lived reply tokens, embeds them in the weekly summary, and parses admin reply syntax (verbs: `keep`, `skip`, `move`, `selector`, `status`, `note`, `override`). Tokens live in `schedule.meta["reply_tokens"]`.
- `schedule_reply_processor.py` applies parsed instructions onto the in-memory schedule, handling validation and producing per-token outcomes that drive confirmation emails and audit logs.
- `schedule_reply_fetcher.py` connects to IMAP using `IMAP_*` and `ADMIN_*` variables, filters for allowed senders, extracts plain-text bodies, delegates to the processor, persists results to `state/last_reply_results.json`, and optionally sends confirmation emails via `sjzl_daily_email.send_email`.
- `scripts/run_weekly_schedule_summary.sh` ensures the upcoming week exists (rolling forward using `EZOE_VOLUME`/`EZOE_LESSON`/`EZOE_DAY_START` seed env vars when needed), renders HTML + plain summaries, archives the HTML in `state/last_schedule_summary.html`, and emails admins when `ADMIN_SUMMARY_TO` is configured.
- `scripts/process_schedule_replies.py` (invoked by `scripts/run_schedule_reply_processor.sh`) exposes CLI flags for batch size and dry runs when testing IMAP processing.
- `app/main.py` exposes a FastAPI dashboard that reuses the schedule helpers for password-protected edits and acts as the landing page for weekly summary links.

## Data & Persistence

- `state/ezoe_schedule.json` — canonical schedule file with entries sorted by date.
- `state/last_schedule_summary.html` — most recent weekly summary email body.
- `state/last_reply_results.json` — serialized results from the latest IMAP processing run.
- Additional debug artifacts: when `DEBUG_EMAIL` is enabled, raw HTML previews may be written under `state/`.

## Configuration Surface

- **Schedule**: `SCHEDULE_FILE`, `EZOE_SEND_WEEKDAY`, `EZOE_SEND_DATE`, `RUN_FORCE`, `EZOE_VOLUME`, `EZOE_LESSON`, `EZOE_DAY_START`.
- **Content selection**: `EZOE_SELECTOR` (set automatically by the daily runner), `EZOE_BASE`, `SJZL_BASE`, `POLITE_DELAY_MS`.
- **Email delivery**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`, `TLS_MODE`, `CONTENT_LANGUAGE`.
- **Admin summaries**: `ADMIN_SUMMARY_TO`, `ADMIN_SUMMARY_FROM`, `ADMIN_SUMMARY_SUBJECT_PREFIX`.
- **Admin replies/IMAP**: `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_MAILBOX`, `ADMIN_REPLY_FROM`, `ADMIN_REPLY_SUBJECT_KEYWORD`, `ADMIN_REPLY_CONFIRMATION_TO`.

All scripts expect these variables to be present in `.env`; the stateful runner automatically sources the file before invoking Python entrypoints.

## External Integrations

- **HTTP scraping**: `requests` + `BeautifulSoup` fetch lesson content from `four.soqimp.com` and `ezoe.work`.
- **SMTP**: `smtplib` sends multipart emails to subscribers and admin recipients.
- **IMAP**: `imaplib` downloads admin reply emails, using `email` package helpers for MIME parsing.

## Testing & Local Development Notes

- Tests under `tests/` cover schedule management, token issuance, and reply parsing.
- Worktree helper scripts (`scripts/create-worktree.sh`, `scripts/init-worktree.sh`) let multiple contributors operate on separate branches without clobbering `.env` or `.venv/`.
- When running Python modules directly, prefer `set -a; . ./.env; set +a` to export configuration into the shell session.
