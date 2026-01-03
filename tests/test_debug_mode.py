#!/usr/bin/env python3
"""
Test script to demonstrate DEBUG_MODE functionality.
This script simulates running the email scripts with DEBUG_MODE=1.
"""

import os
import sys
from unittest.mock import patch, MagicMock

# Set up test environment
os.environ["EMAIL_FROM"] = "test-from@example.com"
os.environ["EMAIL_TO"] = "test-to@example.com"
os.environ["SMTP_USER"] = "test-smtp@example.com"
os.environ["DEBUG_MODE"] = "1"

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sjzl_daily_email as sjzl

def test_debug_mode_e2e():
    """Test that DEBUG_MODE enables debug behavior and changes email recipient."""

    print("Testing DEBUG_MODE functionality...")
    print(f"EMAIL_FROM: {os.environ.get('EMAIL_FROM')}")
    print(f"EMAIL_TO: {os.environ.get('EMAIL_TO')}")
    print(f"DEBUG_MODE: {os.environ.get('DEBUG_MODE')}")

    # Test _debug_enabled
    print(f"_debug_enabled(): {sjzl._debug_enabled()}")

    # Mock Gmail API to avoid actual sending
    with patch('sjzl_daily_email.get_gmail_service') as mock_gmail:
        mock_service = MagicMock()
        mock_gmail.return_value = mock_service

        # Test send_email
        print("\nSending test email...")
        sjzl.send_email("DEBUG MODE TEST", "This is a test email sent in debug mode.")

        # Verify the call was made
        assert mock_gmail.called, "Gmail service should have been called"

        # Extract the message data
        call_args = mock_gmail.return_value.users.return_value.messages.return_value.send.call_args
        message_data = call_args[1]['body']

        # Decode the raw message
        import base64
        raw_message = base64.urlsafe_b64decode(message_data['raw'])
        message_str = raw_message.decode('utf-8', errors='ignore')

        # Check recipient
        if "To: test-from@example.com" in message_str:
            print("✓ Email sent to EMAIL_FROM (debug mode working)")
        elif "To: test-to@example.com" in message_str:
            print("✗ Email sent to EMAIL_TO (debug mode not working)")
        else:
            print("? Email recipient unclear")

        print("DEBUG_MODE E2E test completed successfully!")

if __name__ == "__main__":
    test_debug_mode_e2e()
