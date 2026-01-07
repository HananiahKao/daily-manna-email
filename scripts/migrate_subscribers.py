#!/usr/bin/env python3
"""
Migration script to populate subscriber database from environment variables.

Usage:
    python scripts/migrate_subscribers.py [--dry-run] [--source <source>] [--email-list <emails>]

This script migrates subscribers from EMAIL_TO environment variable to the encrypted database.
It supports both ezoe and wix content sources.

Environment variables:
    EMAIL_TO - Comma-separated list of email addresses (legacy)
    EMAIL_ENCRYPTION_KEY - Required for email encryption

Options:
    --dry-run: Show what would be migrated without making changes
    --source: Content source to assign subscribers to (ezoe or wix, default: ezoe)
    --email-list: Override EMAIL_TO with custom comma-separated list
"""

import argparse
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.subscriber_manager import add_subscriber, SubscriberError, DuplicateSubscriberError
from app.email_encryption import generate_email_encryption_key


def parse_email_list(email_string: str) -> list[str]:
    """Parse comma-separated email list, cleaning whitespace."""
    if not email_string or not email_string.strip():
        return []
    return [email.strip() for email in email_string.split(",") if email.strip()]


def migrate_subscribers(email_list: str, content_source: str, dry_run: bool = False) -> tuple[int, int]:
    """
    Migrate subscribers from email list to database.

    Returns:
        Tuple of (migrated_count, error_count)
    """
    emails = parse_email_list(email_list)
    if not emails:
        print("No emails to migrate")
        return 0, 0

    print(f"Migrating {len(emails)} subscribers to content source '{content_source}'")
    if dry_run:
        print("DRY RUN - No changes will be made")

    migrated = 0
    errors = 0

    for email in emails:
        try:
            if dry_run:
                print(f"Would migrate: {email} -> {content_source}")
                migrated += 1
            else:
                add_subscriber(email, content_source)
                print(f"Migrated: {email}")
                migrated += 1
        except DuplicateSubscriberError:
            print(f"Already exists: {email}")
            migrated += 1  # Count as migrated since they already exist
        except SubscriberError as e:
            print(f"Error migrating {email}: {e}")
            errors += 1
        except Exception as e:
            print(f"Unexpected error migrating {email}: {e}")
            errors += 1

    return migrated, errors


def ensure_encryption_key() -> None:
    """Ensure EMAIL_ENCRYPTION_KEY is set, generate if missing."""
    if not os.getenv("EMAIL_ENCRYPTION_KEY"):
        print("EMAIL_ENCRYPTION_KEY not set. Generating a new key...")
        key = generate_email_encryption_key()
        print(f"Generated key: {key}")
        print("Please set EMAIL_ENCRYPTION_KEY environment variable to this value.")
        print("You can also run: export EMAIL_ENCRYPTION_KEY='" + key + "'")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Migrate subscribers from environment variables to database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    parser.add_argument("--source", default="ezoe", choices=["ezoe", "wix"],
                       help="Content source to assign subscribers to (default: ezoe)")
    parser.add_argument("--email-list", help="Override EMAIL_TO with custom comma-separated email list")

    args = parser.parse_args()

    # Ensure encryption key is available
    ensure_encryption_key()

    # Get email list from args or environment
    email_list = args.email_list or os.getenv("EMAIL_TO", "")
    if not email_list:
        print("No email list provided. Set EMAIL_TO environment variable or use --email-list")
        sys.exit(1)

    # Perform migration
    try:
        migrated, errors = migrate_subscribers(email_list, args.source, args.dry_run)

        print(f"\nMigration {'preview' if args.dry_run else 'complete'}!")
        print(f"Subscribers processed: {migrated + errors}")
        print(f"Successfully migrated: {migrated}")
        if errors > 0:
            print(f"Errors: {errors}")

        if args.dry_run:
            print("\nRun without --dry-run to perform the actual migration")

    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
