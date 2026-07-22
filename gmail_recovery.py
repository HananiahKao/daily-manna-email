"""Gmail recovery logic for crash-resilient delivery tracking.

When the system restarts after a crash (e.g., sent to Alice but crashed before
recording), this module queries Gmail's sent folder to backfill missing delivery
records, preventing duplicates on recovery.

Flow:
1. For each recipient without a delivery record for today:
2. Query Gmail: "Do I have a message to this recipient today?"
3. If YES: backfill delivery record (system crashed mid-batch)
4. If NO: send normally (or was already sent, just not recorded)
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

import delivery_tracker
from oauth_utils import get_gmail_service

logger = logging.getLogger(__name__)


def _search_gmail_sent_to_recipient(
    service,
    recipient: str,
    date: dt.date,
    content_source: Optional[str] = None,
) -> Optional[str]:
    """Search Gmail sent folder for message to recipient on given date.

    Args:
        service: Gmail API service object
        recipient: Email address to search for
        date: Date to search (YYYY-MM-DD)
        content_source: Optional content source to verify (e.g., 'stmn1', 'ezoe')

    Returns:
        Gmail message ID if found and content_source matches, None otherwise
    """
    try:
        # Gmail query: search sent folder for emails to this recipient on this date
        # Format: to:recipient after:2026-06-28 before:2026-06-30
        query = (
            f'to:"{recipient}" '
            f'after:{(date - dt.timedelta(days=1)).isoformat()} '
            f'before:{(date + dt.timedelta(days=1)).isoformat()}'
        )

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=10  # Limit to recent messages
        ).execute()

        messages = results.get('messages', [])
        if messages:
            # Verify content source if specified
            if content_source:
                for msg_data in messages:
                    message_id = msg_data.get('id')
                    try:
                        # Fetch message headers to verify content source
                        msg = service.users().messages().get(
                            userId='me',
                            id=message_id,
                            format='metadata',
                            metadataHeaders=['X-Content-Source']
                        ).execute()

                        headers = msg.get('payload', {}).get('headers', [])
                        msg_content_source = next(
                            (h.get('value') for h in headers if h.get('name') == 'X-Content-Source'),
                            None
                        )

                        if msg_content_source == content_source:
                            logger.info(
                                "Found matching message on %s: %s (content_source=%s, crash recovery)",
                                date.isoformat(), message_id, content_source
                            )
                            return message_id
                    except Exception as e:
                        logger.debug("Failed to check message headers: %s", e)
                        continue

                # No matching content source found
                logger.debug(
                    "Found messages for %s on %s but none match content_source=%s",
                    recipient, date.isoformat(), content_source
                )
                return None
            else:
                # No content source specified, return first message (backward compatibility)
                message_id = messages[0].get('id')
                logger.info(
                    "Found existing message on %s: %s (crash recovery)",
                    date.isoformat(), message_id
                )
                return message_id

        return None

    except Exception as e:
        logger.warning(
            "Failed to search Gmail: %s (will attempt normal send)",
            e
        )
        return None


def backfill_missing_deliveries(
    service,
    recipients: list[str],
    date: dt.date,
    path=None,
    content_source: Optional[str] = None,
) -> dict[str, str]:
    """Backfill delivery records by querying Gmail for crashed sends.

    For any recipient without a delivery record, checks if we already sent to them
    by searching Gmail's sent folder. If found, records the message ID.

    Args:
        service: Gmail API service object
        recipients: Full list of recipients
        date: Date to check (typically today)
        path: Optional path override for testing

    Returns:
        Dict of {recipient: message_id} for backfilled records
    """
    backfilled = {}

    # Get currently recorded deliveries
    delivered = delivery_tracker.get_date_deliveries(date, path)
    missing = [r for r in recipients if r not in delivered]

    if not missing:
        logger.debug("No missing recipients to backfill")
        return {}

    logger.info("Backfilling %d missing recipient(s) from Gmail sent folder", len(missing))

    for recipient in missing:
        message_id = _search_gmail_sent_to_recipient(service, recipient, date, content_source)

        if message_id:
            # Backfill the delivery record
            delivery_tracker.record_delivery(recipient, date, message_id, path=path, content_source=content_source)
            backfilled[recipient] = message_id
            logger.info(
                "Backfilled delivery record with message_id=%s (source=%s)",
                message_id, content_source or "unknown"
            )

    if backfilled:
        logger.info(
            "Backfill complete: recovered %d delivery records from Gmail",
            len(backfilled)
        )

    return backfilled


def ensure_no_duplicates_on_startup(
    recipients: list[str],
    date: dt.date,
    content_source: Optional[str] = None,
) -> None:
    """Ensure delivery records are complete before sending.

    Call this before the send loop to backfill any missing records from Gmail.
    Prevents duplicate sends if the system crashed mid-batch.

    Args:
        recipients: Full list of recipients to send to
        date: Date of the send (typically today)
        content_source: Optional content source to verify (e.g., 'stmn1', 'ezoe')
    """
    try:
        service = get_gmail_service()
        backfill_missing_deliveries(service, recipients, date, content_source=content_source)
    except Exception as e:
        logger.error(
            "Failed to backfill delivery records: %s (proceeding with normal send)",
            e
        )
        # Don't fail the send if backfill fails — proceed with normal sending
        # The delivery tracker will still prevent duplicates for already-sent recipients


__all__ = [
    "ensure_no_duplicates_on_startup",
    "backfill_missing_deliveries",
]
