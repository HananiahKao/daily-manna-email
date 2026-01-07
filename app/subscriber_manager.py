#!/usr/bin/env python3
"""
Subscriber management functions for encrypted email storage.

Provides high-level functions for managing subscribers per content source.
"""

import logging
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import initialize_database
from .email_encryption import decrypt_email, encrypt_email, validate_email_format
from .models import Subscriber, get_db_session
from .token_encryption import TokenEncryptionError

logger = logging.getLogger(__name__)


class SubscriberError(Exception):
    """Base exception for subscriber management errors."""
    pass


class SubscriberNotFoundError(SubscriberError):
    """Raised when a subscriber is not found."""
    pass


class DuplicateSubscriberError(SubscriberError):
    """Raised when trying to add a duplicate subscriber."""
    pass


def _ensure_database_initialized():
    """Ensure database is initialized before operations."""
    try:
        initialize_database()
    except Exception as e:
        raise SubscriberError(f"Failed to initialize database: {e}")


def add_subscriber(email: str, content_source: str) -> Subscriber:
    """
    Add a subscriber to a specific content source.

    Args:
        email: Plain text email address
        content_source: Content source identifier ('ezoe' or 'wix')

    Returns:
        Subscriber object

    Raises:
        SubscriberError: If email format is invalid or database error occurs
        DuplicateSubscriberError: If subscriber already exists for this source
    """
    if not validate_email_format(email):
        raise SubscriberError(f"Invalid email format: {email}")

    if content_source not in ("ezoe", "wix"):
        raise SubscriberError(f"Invalid content source: {content_source}")

    _ensure_database_initialized()

    try:
        encrypted_email = encrypt_email(email)
    except TokenEncryptionError as e:
        raise SubscriberError(f"Failed to encrypt email: {e}")

    with get_db_session() as session:
        try:
            # Check for existing subscriber by decrypting emails
            existing_subscribers = session.query(Subscriber).filter_by(
                content_source=content_source
            ).all()

            normalized_email = email.lower().strip()
            for existing in existing_subscribers:
                try:
                    existing_email = decrypt_email(existing.email_encrypted)
                    if existing_email == normalized_email:
                        if existing.active:
                            raise DuplicateSubscriberError(
                                f"Subscriber {email} already exists for {content_source}"
                            )
                        else:
                            # Reactivate inactive subscriber
                            existing.active = True
                            session.commit()
                            logger.info(f"Reactivated subscriber {email} for {content_source}")
                            return existing
                except TokenEncryptionError:
                    # Skip corrupted entries but continue checking
                    continue

            # Create new subscriber
            subscriber = Subscriber()  # type: ignore
            subscriber.email_encrypted = encrypted_email
            subscriber.content_source = content_source
            subscriber.active = True
            session.add(subscriber)
            session.commit()
            session.refresh(subscriber)

            logger.info(f"Added subscriber {email} for {content_source}")
            return subscriber

        except IntegrityError:
            session.rollback()
            raise DuplicateSubscriberError(
                f"Subscriber {email} already exists for {content_source}"
            )
        except DuplicateSubscriberError:
            # Re-raise duplicate errors without wrapping
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise SubscriberError(f"Failed to add subscriber: {e}")


def remove_subscriber(email: str, content_source: str) -> bool:
    """
    Remove a subscriber from a specific content source (soft delete).

    Args:
        email: Plain text email address
        content_source: Content source identifier

    Returns:
        True if subscriber was found and deactivated

    Raises:
        SubscriberError: If database error occurs
    """
    if content_source not in ("ezoe", "wix"):
        raise SubscriberError(f"Invalid content source: {content_source}")

    _ensure_database_initialized()

    with get_db_session() as session:
        try:
            # Find all active subscribers for this content source
            subscribers = session.query(Subscriber).filter_by(
                content_source=content_source,
                active=True
            ).all()

            # Find the subscriber with matching email (decrypt and compare)
            for subscriber in subscribers:
                try:
                    decrypted_email = decrypt_email(subscriber.email_encrypted)
                    if decrypted_email == email.lower().strip():
                        subscriber.active = False
                        session.commit()
                        logger.info(f"Removed subscriber {email} from {content_source}")
                        return True
                except TokenEncryptionError:
                    # Skip corrupted entries but continue searching
                    continue

            return False

        except Exception as e:
            session.rollback()
            raise SubscriberError(f"Failed to remove subscriber: {e}")


def get_subscribers(content_source: str) -> List[str]:
    """
    Get all active subscribers for a content source.

    Args:
        content_source: Content source identifier

    Returns:
        List of plain text email addresses

    Raises:
        SubscriberError: If database error occurs
    """
    if content_source not in ("ezoe", "wix"):
        raise SubscriberError(f"Invalid content source: {content_source}")

    _ensure_database_initialized()

    with get_db_session() as session:
        try:
            subscribers = session.query(Subscriber).filter_by(
                content_source=content_source,
                active=True
            ).all()

            emails = []
            for subscriber in subscribers:
                try:
                    email = decrypt_email(subscriber.email_encrypted)
                    emails.append(email)
                except TokenEncryptionError as e:
                    logger.error(f"Failed to decrypt email for subscriber {subscriber.id}: {e}")
                    # Skip corrupted emails but continue processing
                    continue

            return emails

        except Exception as e:
            raise SubscriberError(f"Failed to get subscribers: {e}")


def get_subscriber_count(content_source: Optional[str] = None) -> int:
    """
    Get the count of active subscribers.

    Args:
        content_source: Optional content source filter

    Returns:
        Number of active subscribers
    """
    _ensure_database_initialized()

    with get_db_session() as session:
        try:
            query = session.query(Subscriber).filter_by(active=True)
            if content_source:
                query = query.filter_by(content_source=content_source)
            return query.count()
        except Exception as e:
            raise SubscriberError(f"Failed to count subscribers: {e}")


def migrate_from_env(email_list: str, content_source: str) -> int:
    """
    Migrate subscribers from comma-separated environment variable.

    Args:
        email_list: Comma-separated email addresses
        content_source: Content source to assign subscribers to

    Returns:
        Number of subscribers migrated

    Raises:
        SubscriberError: If migration fails
    """
    emails = [email.strip() for email in email_list.split(",") if email.strip()]
    migrated = 0

    for email in emails:
        try:
            add_subscriber(email, content_source)
            migrated += 1
        except DuplicateSubscriberError:
            # Already exists, count as migrated
            migrated += 1
        except SubscriberError as e:
            logger.warning(f"Failed to migrate {email}: {e}")
            # Continue with other emails

    logger.info(f"Migrated {migrated} subscribers to {content_source}")
    return migrated


def list_all_subscribers() -> List[dict]:
    """
    Get all subscribers with their details (for admin purposes).

    Returns:
        List of dicts with subscriber information
    """
    _ensure_database_initialized()

    with get_db_session() as session:
        try:
            subscribers = session.query(Subscriber).order_by(  # type: ignore
                Subscriber.content_source, Subscriber.subscribed_at
            ).all()

            result = []
            for subscriber in subscribers:
                try:
                    email = decrypt_email(subscriber.email_encrypted)
                    result.append({  # type: ignore
                        "id": subscriber.id,
                        "email": email,
                        "content_source": subscriber.content_source,
                        "subscribed_at": subscriber.subscribed_at.isoformat(),
                        "active": subscriber.active,
                    })
                except TokenEncryptionError as e:
                    logger.error(f"Failed to decrypt email for subscriber {subscriber.id}: {e}")
                    continue

            return result

        except Exception as e:
            raise SubscriberError(f"Failed to list subscribers: {e}")
