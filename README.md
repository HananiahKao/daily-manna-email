Daily Manna Email（聖經之旅每日郵件）

Overview
- Fetches the latest “聖經之旅” lesson and emails a readable version daily.
- Supports two sources/modes:
  - SJZL discovery mode: discovers the latest lesson under `https://four.soqimp.com/books/2264` and sends a plain‑text email.
  - Ezoe selector mode: fetches a specific day’s HTML from ezoe.work and sends a rich HTML email with a plain‑text fallback.

Repository Layout
- `sjzl_daily_email.py` — Main scheduler-friendly script that discovers content, extracts text, and sends email via SMTP.
- `ezoe_week_scraper.py` — Helper that scrapes a single lesson day from ezoe.work given a standardized selector like `2-1-3`.
- `.env` — Local environment variables (not committed). Populate with your SMTP and mode config.

Requirements
- Python 3.9+
- Packages: `requests`, `beautifulsoup4`

Install
- Create and activate a virtual environment, then install deps:
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install requests beautifulsoup4`

Configuration
Set the following environment variables (for local dev you can put them in `.env` and export them before running):
- `SMTP_HOST` — SMTP server host, e.g., `smtp.gmail.com`.
- `SMTP_PORT` — SMTP port, e.g., `587` for STARTTLS or `465` for SSL. Default: `587`.
- `SMTP_USER` — SMTP username (often your email address).
- `SMTP_PASSWORD` — SMTP password or app password.
- `EMAIL_FROM` — Optional. Defaults to `SMTP_USER`.
- `EMAIL_TO` — Comma‑separated recipient list.
- `TLS_MODE` — `starttls` (default) or `ssl`.

Content source and mode selection:
- Default SJZL discovery mode (plain text):
  - Uses `SJZL_BASE` (default `https://four.soqimp.com/books/2264`).
  - Discovers the latest lesson by scanning `indexXX.html` and picking the highest numbered lesson.

- Ezoe selector HTML mode (rich HTML):
  - Set `EZOE_SELECTOR` to a standardized selector: `"<volume>-<lesson>-<day>"`.
    - `volume`: integer (e.g., for file `2264-2-1.html`, volume is `2`).
    - `lesson`: integer (1‑based lesson index within the volume, e.g., `1`).
    - `day`: `0..7` where `1..7` map to `周一..主日` and `0` returns the combined lesson content.
  - Optional `EZOE_BASE` (default `https://ezoe.work/books/2`).
  - In this mode, the email is HTML with a minimal plain‑text fallback.

Optional testing helpers:
- `TEST_LESSON_URL` — Override the discovered lesson URL (useful for deterministic tests). When set, the subject shows `測試`.
- `HTTP_RETRIES` — Retries for HTTP fetches. Default: `3`.

Run
- One‑off run (ensure env vars are exported or loaded):
  - `python sjzl_daily_email.py`
  - Exit code `0` on success; non‑zero on error.

Examples
- Plain‑text latest lesson email (default SJZL mode):
  - `export SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... EMAIL_TO=me@example.com`
  - `python sjzl_daily_email.py`

- HTML day email (Ezoe selector mode):
  - `export EZOE_SELECTOR=2-1-3`  # Volume 2, lesson 1, 周三
  - `python sjzl_daily_email.py`

Scheduling
- Use cron, systemd timers, or your CI to run daily. Example crontab (8:00 daily):
  - `0 8 * * * cd /path/to/daily-manna-email && /path/to/.venv/bin/python sjzl_daily_email.py >> daily.log 2>&1`

Security & Etiquette
- Keep credentials in a secure secret store or `.env` not committed to VCS.
- This is for personal, non‑commercial use. Be considerate with request frequency; the script uses simple retries and modest timeouts.

Development Notes
- Network parsing is best‑effort; upstream HTML can change.
- `extract_readable_text` tries to produce concise, readable plain text. If you need more structure, consider customizing the extraction.
- The ezoe day scraper searches for exact day labels (`周一..主日`) and wraps collected content in a simple `<div>` with a header.

Troubleshooting
- Missing env vars: the script exits with an error listing required ones.
- Email fails: verify `SMTP_*`, `TLS_MODE`, and that your provider allows SMTP/app passwords.
- Fetch fails: check connectivity, `SJZL_BASE`/`EZOE_BASE`, and consider increasing `HTTP_RETRIES`.

License
- Personal project; no explicit license provided. Use at your discretion.
