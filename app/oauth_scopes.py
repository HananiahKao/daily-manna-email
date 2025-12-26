"""
OAuth scope utilities for Google Gmail API.

Provides user-friendly descriptions for OAuth scopes according to Google's
official documentation: https://developers.google.com/identity/protocols/oauth2/scopes
"""

# Mapping of Gmail OAuth scopes to user-friendly descriptions
# Based on Google's official OAuth 2.0 scopes documentation
GMAIL_SCOPE_DESCRIPTIONS = {
    # Core Gmail scopes used by this application
    'https://www.googleapis.com/auth/gmail.send': 'Send email on your behalf',
    'https://www.googleapis.com/auth/gmail.readonly': 'View your email messages and settings',

    # Additional Gmail scopes that might be encountered
    'https://www.googleapis.com/auth/gmail.compose': 'Manage drafts and send emails',
    'https://www.googleapis.com/auth/gmail.insert': 'Add emails into your Gmail mailbox',
    'https://www.googleapis.com/auth/gmail.labels': 'See and edit your email labels',
    'https://www.googleapis.com/auth/gmail.metadata': 'View your email message metadata such as labels and headers, but not the email body',
    'https://www.googleapis.com/auth/gmail.modify': 'Read, compose, and send emails from your Gmail account',
    'https://www.googleapis.com/auth/gmail.settings.basic': 'See, edit, create, or change your email settings and filters in Gmail',
    'https://www.googleapis.com/auth/gmail.settings.sharing': 'Manage your sensitive mail settings, including who can manage your mail',

    # Gmail Add-on scopes
    'https://www.googleapis.com/auth/gmail.addons.current.action.compose': 'Manage drafts and send emails when you interact with the add-on',
    'https://www.googleapis.com/auth/gmail.addons.current.message.action': 'View your email messages when you interact with the add-on',
    'https://www.googleapis.com/auth/gmail.addons.current.message.metadata': 'View your email message metadata when the add-on is running',
    'https://www.googleapis.com/auth/gmail.addons.current.message.readonly': 'View your email messages when the add-on is running',

    # Legacy scope
    'https://mail.google.com/': 'Read, compose, send, and permanently delete all your email from Gmail',
}


def get_scope_description(scope: str) -> str:
    """
    Get the user-friendly description for a Gmail OAuth scope.

    Args:
        scope: The technical scope string (e.g., 'https://www.googleapis.com/auth/gmail.send')

    Returns:
        User-friendly description of the scope, or the original scope string if not found
    """
    return GMAIL_SCOPE_DESCRIPTIONS.get(scope, scope)


def get_scopes_descriptions(scopes: list[str]) -> list[str]:
    """
    Get user-friendly descriptions for a list of Gmail OAuth scopes.

    Args:
        scopes: List of technical scope strings

    Returns:
        List of user-friendly descriptions
    """
    return [get_scope_description(scope) for scope in scopes]
