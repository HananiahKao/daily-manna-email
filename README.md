Daily Manna Email

- Original link behavior (ezoe selector mode):
  - The email footer includes “原文連結” pointing to the canonical page on ezoe.work.
  - It deep-links to the day section using anchors `#1_6`..`#1_12` mapping 周一..主日.
  - Example: selector `2-1-3` → `https://ezoe.work/books/2/2264-2-1.html#1_8` (周三).
  - If parsing fails, falls back to the non-anchored URL.

Testing
- Force a send for testing: `RUN_FORCE=1 scripts/run_daily_stateful_ezoe.sh`.
- Check logs for: `Original link (anchored): <url>`.

