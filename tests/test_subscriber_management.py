"""
Tests for subscriber management system.
"""

import os
import pytest
import tempfile
from pathlib import Path

from app.subscriber_manager import (
    add_subscriber, remove_subscriber, get_subscribers,
    get_subscriber_count, SubscriberError, DuplicateSubscriberError
)
from app.email_encryption import generate_email_encryption_key
from app.database import initialize_database


@pytest.fixture(scope="function", autouse=True)
def setup_test_environment():
    """Set up test environment with encryption key and test database."""
    # Generate a test encryption key
    test_key = generate_email_encryption_key()

    # Set environment variables for testing
    os.environ["EMAIL_ENCRYPTION_KEY"] = test_key
    os.environ["DATABASE_MODE"] = "sqlite"

    # Use a temporary database for tests
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db_path = tmp.name

    os.environ["DATABASE_PATH"] = test_db_path

    # Initialize database
    initialize_database()

    yield

    # Cleanup
    try:
        Path(test_db_path).unlink(missing_ok=True)
    except Exception:
        pass


class TestSubscriberManagement:
    """Test subscriber management functions."""

    def test_add_subscriber_valid(self):
        """Test adding a valid subscriber."""
        subscriber = add_subscriber("test@example.com", "ezoe")
        assert subscriber.email_encrypted is not None
        assert subscriber.content_source == "ezoe"
        assert subscriber.active is True

    def test_add_subscriber_duplicate(self):
        """Test adding duplicate subscriber raises error."""
        # Add first time
        add_subscriber("duplicate@example.com", "ezoe")

        # Try to add again - should raise error
        with pytest.raises(DuplicateSubscriberError):
            add_subscriber("duplicate@example.com", "ezoe")

    def test_add_subscriber_invalid_email(self):
        """Test adding subscriber with invalid email."""
        with pytest.raises(SubscriberError):
            add_subscriber("invalid-email", "ezoe")

    def test_add_subscriber_invalid_source(self):
        """Test adding subscriber with invalid content source."""
        with pytest.raises(SubscriberError):
            add_subscriber("test@example.com", "invalid")

    def test_get_subscribers(self):
        """Test getting subscribers for a content source."""
        email = "get-test@example.com"
        add_subscriber(email, "wix")

        subscribers = get_subscribers("wix")
        assert email in subscribers

        # Check other source doesn't have this subscriber
        ezoe_subscribers = get_subscribers("ezoe")
        assert email not in ezoe_subscribers

    def test_remove_subscriber(self):
        """Test removing a subscriber."""
        email = "remove-test@example.com"
        add_subscriber(email, "ezoe")

        # Verify it's there
        subscribers = get_subscribers("ezoe")
        assert email in subscribers

        # Remove it
        result = remove_subscriber(email, "ezoe")
        assert result is True

        # Verify it's gone
        subscribers = get_subscribers("ezoe")
        assert email not in subscribers

    def test_remove_nonexistent_subscriber(self):
        """Test removing a subscriber that doesn't exist."""
        result = remove_subscriber("nonexistent@example.com", "ezoe")
        assert result is False

    def test_get_subscriber_count(self):
        """Test getting subscriber count."""
        # Add some test subscribers with unique emails
        add_subscriber("count1@example.com", "ezoe")
        add_subscriber("count2@example.com", "ezoe")
        add_subscriber("count3@example.com", "wix")

        ezoe_count = get_subscriber_count("ezoe")
        wix_count = get_subscriber_count("wix")
        total_count = get_subscriber_count()

        assert ezoe_count >= 2  # At least the ones we added
        assert wix_count >= 1
        assert total_count >= 3

    def test_email_normalization(self):
        """Test that emails are normalized (lowercased, stripped)."""
        # Add with mixed case and whitespace - use unique email
        email_with_case = "  NORMALIZE@EXAMPLE.COM  "
        add_subscriber(email_with_case, "ezoe")

        # Should be able to retrieve with normalized version
        subscribers = get_subscribers("ezoe")
        assert "normalize@example.com" in subscribers

        # Try to add the normalized version - should detect as duplicate
        with pytest.raises(DuplicateSubscriberError):
            add_subscriber("normalize@example.com", "ezoe")
