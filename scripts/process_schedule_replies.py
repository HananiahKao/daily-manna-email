#!/usr/bin/env python3
"""CLI to fetch admin reply emails and apply schedule updates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path when executed from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import schedule_reply_fetcher as srf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process admin reply emails via IMAP")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of emails to process")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse without saving or sending emails")
    args = parser.parse_args(argv)

    config = srf.ImapConfig.from_env()
    summary = srf.process_mailbox(config, limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0 if summary.error_count == 0 else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
