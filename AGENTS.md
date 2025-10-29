Agent Guidelines for This Repo

- Read commit rules before committing:
  - File: `/Users/hananiah/Developer/Commit_Message_Rules.md`
  - Always open and follow its format when proposing or making commits.

- Commit etiquette:
  - Ask for approval before committing.
  - Do not push unless explicitly requested.
  - Always stage files explicitly (no blanket `git add -A`). Use `git add <path>` for only the intended files to avoid committing local envs/venv. Prefer `git status` to verify before committing.

- Coding style:
  - Keep changes minimal and focused on the task.
  - Prefer plain Python with `requests` and `BeautifulSoup` for scraping.
  - Return rich HTML when requested to support HTML emails.

- Environment:
  - Support configuration via environment variables where applicable.

- VCS hygiene:
  - Do not commit `.venv/`, `.env`, `.sjzl_env`, or other local-only artifacts. If needed, update `.gitignore` first.
