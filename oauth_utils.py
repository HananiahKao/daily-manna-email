import os
import json
import base64
import imaplib
import smtplib
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Define minimal scopes required for the application:
# - gmail.send for sending messages via Gmail API
# - gmail.readonly for reading messages via Gmail API
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]
CLIENT_SECRET_FILE = 'client_secret.json'
TOKEN_FILE = 'token.json'

def get_credentials():
    """
    Handles the OAuth 2.0 flow to get valid credentials.
    It checks for an existing token, refreshes it if expired.
    If no valid token exists, raises an exception instead of prompting for OAuth.
    This function is designed for use in automated scripts that should fail fast
    when OAuth is not configured via the web interface.
    """
    creds = None

    # 1. Load existing token
    if Path(TOKEN_FILE).exists():
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except (ValueError, json.decoder.JSONDecodeError) as e:
            raise RuntimeError(f"Error loading token from {TOKEN_FILE}: {e}. Please re-authorize via the web dashboard.")

    # 2. Refresh token if expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed credentials
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                raise RuntimeError(f"Error refreshing OAuth token: {e}. Please re-authorize via the web dashboard.")
        else:
            # No valid credentials - fail fast instead of prompting
            raise RuntimeError(
                "No valid OAuth credentials found. Please authorize the application via the web dashboard at /oauth/start"
            )

    return creds

def generate_xoauth2_string(email_address, access_token):
    """
    Generates the SASL XOAUTH2 string for IMAP/SMTP login.
    Format: base64("user=" {User} "^Aauth=Bearer " {Access Token} "^A^A")
    where ^A is a Control+A (\x01).
    """
    auth_string = f'user={email_address}\x01auth=Bearer {access_token}\x01\x01'
    return auth_string

def get_xoauth2_string(email_address):
    """
    Main function to get the XOAUTH2 string for a given email address.
    """
    creds = get_credentials()
    if creds:
        return generate_xoauth2_string(email_address, creds.token)
    return None

# The following is a helper function to patch smtplib.SMTP.login for XOAUTH2
# Since smtplib.SMTP.login doesn't directly support XOAUTH2, we use server.auth
# which is available in Python 3.5+. We'll modify the main files directly.

# Helper function for IMAP authentication, as imaplib.IMAP4_SSL.authenticate is used
def imap_xoauth2_authenticate(imap_server, email_address):
    """
    Performs XOAUTH2 authentication for an imaplib.IMAP4_SSL object.
    """
    xoauth2_string = get_xoauth2_string(email_address)
    if xoauth2_string:
        # imaplib.IMAP4_SSL.authenticate expects a callable that returns the
        # base64-encoded string, or the string itself if the mechanism is not
        # interactive (which XOAUTH2 is not, it's an initial client response).
        # However, the standard way is to pass the mechanism and the string.
        # The imaplib.authenticate method is a bit tricky, but passing the
        # mechanism and the base64 string should work for XOAUTH2.
        # The imaplib.authenticate method expects a callable for the response,
        # but for XOAUTH2, the entire payload is sent in the first step.
        # We will use the standard approach of passing the mechanism and a callable
        # that returns the base64 string, which is how the google-api-python-client
        # often suggests it.
        response = imap_server.authenticate('XOAUTH2', lambda x: xoauth2_string)
        if response[0] != 'OK':
            raise imaplib.IMAP4.error(f"IMAP XOAUTH2 authentication failed: {response}")
        return response
    raise ValueError("Could not get XOAUTH2 string for IMAP authentication.")


def get_gmail_service():
    """
    Creates and returns a Gmail API service instance using OAuth credentials.
    """
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Failed to obtain OAuth credentials for Gmail API")
    return build('gmail', 'v1', credentials=creds)
