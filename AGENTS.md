Agent Guidelines for This Repo

- Read commit rules before committing:
  - File: `/Users/hananiah/Developer/Commit_Message_Rules.md`
  - Always open and follow its format when proposing or making commits.

- Commit etiquette:
  - Ask for approval before committing.
  - Do not push unless explicitly requested.
  - Always stage files explicitly (no blanket `git add -A`). Use `git add <path>` for only the intended files to avoid committing local envs/venv. Prefer `git status` to verify before committing.
  - Always provide the proposed commit message for review before committing.

- Coding style:
  - Keep changes minimal and focused on the task.
  - Prefer plain Python with `requests` and `BeautifulSoup` for scraping.
  - Return rich HTML when requested to support HTML emails.

- Environment:
  - Support configuration via environment variables where applicable.

- VCS hygiene:
  - Do not commit `.venv/`, `.env`, `.sjzl_env`, or other local-only artifacts. If needed, update `.gitignore` first.

## Environment loading

- When running scripts locally (including `scripts/run_daily_stateful_ezoe.sh` and direct Python entrypoints), always source environment variables from `.env` before execution so email sending works during tests.
- The stateful runner already sources `.env` automatically. For direct runs, prefer either exporting vars in the shell or using: `set -a; . ./.env; set +a` prior to invoking Python.
- Required for sending emails: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` (plus optional `SMTP_PORT`, `EMAIL_FROM`, `TLS_MODE`).

---

Notes to future maintainers (lessons learned)

- HTML decoding and mojibake
  - When scraping ezoe.work (and similar sites), always decode response bytes as UTF-8. Browsers render their pages fine because the HTTP response context supplies charset; our local fetch must do the same.
  - ezoe_week_scraper.py now forces UTF-8 for hosts ending with `ezoe.work` and otherwise uses a robust decode flow (requests’ encoding → meta charset sniff → UTF-8 fallback). Keep this logic if you touch fetching.
  - When writing extracted HTML fragments to disk for file:// preview, wrap them in a minimal shell with `<meta charset="utf-8">`. Without this, browsers may guess a wrong encoding for local files even if the bytes are UTF‑8.

- Day section detection on ezoe.work
  - Day headers (周一..主日) are not plain text anchors. They appear under class `cn1` with predictable IDs: `1_6`..`1_12` correspond to 周一..主日.
  - The scraper now prefers these IDs to anchor sections and falls back to normalized text matching (`周三` contained in element text). If site structure changes, revisit `DAY_ID_BY_INDEX` and `_find_day_anchor`.

- Injected labels
  - The `<h3>周X</h3>` heading in outputs is added by our scraper for clarity. It is not in the source HTML.

- Debugging workflow
  - If you see mojibake in the shell, verify via browser using `file://` after ensuring a `<meta charset="utf-8">` is present. If the browser still shows mojibake, the decoding persisted bad codepoints—fix the requests decoding.
  - Use the existing robust decoder in both `sjzl_daily_email.py` and `ezoe_week_scraper.py` to keep behavior consistent.

- Commit etiquette
  - Before proposing commits, read `/Users/hananiah/Developer/Commit_Message_Rules.md` (external to repo). Follow its format and get approval before committing.
