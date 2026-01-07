#!/usr/bin/env python3
"""
Email encryption utilities using AES-256-GCM.

This module provides secure encryption and decryption of email addresses
for subscriber management, using the same encryption scheme as OAuth tokens.
"""

import base64
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .token_encryption import TokenEncryptionError


def _derive_key(master_key: bytes, salt: bytes) -> bytes:
    """Derive a 32-byte encryption key from master key using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(master_key)


def _get_encryption_key() -> bytes:
    """Get the encryption key from environment variable."""
    key_b64 = os.getenv("EMAIL_ENCRYPTION_KEY")
    if not key_b64:
        raise TokenEncryptionError(
            "EMAIL_ENCRYPTION_KEY environment variable is required for email encryption. "
            "Generate a 32-byte key with: python -c \"import secrets; print(secrets.token_bytes(32).hex())\""
        )

    try:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise TokenEncryptionError("EMAIL_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return key
    except Exception as e:
        raise TokenEncryptionError(f"Invalid EMAIL_ENCRYPTION_KEY: {e}")


def encrypt_email(email: str) -> str:
    """
    Encrypt an email address using AES-256-GCM.

    Args:
        email: Plain text email address

    Returns:
        Base64-encoded encrypted data with salt and nonce

    Raises:
        TokenEncryptionError: If encryption fails
    """
    try:
        # Convert email to bytes
        plaintext = email.lower().strip().encode('utf-8')

        # Get encryption key
        key = _get_encryption_key()

        # Generate salt and derive key
        salt = os.urandom(16)
        derived_key = _derive_key(key, salt)

        # Generate nonce
        nonce = os.urandom(12)

        # Encrypt using AES-GCM
        aesgcm = AESGCM(derived_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # Combine salt + nonce + ciphertext and base64 encode
        encrypted_data = salt + nonce + ciphertext
        return base64.b64encode(encrypted_data).decode('utf-8')

    except Exception as e:
        raise TokenEncryptionError(f"Failed to encrypt email: {e}")


def decrypt_email(encrypted_email: str) -> str:
    """
    Decrypt an email address using AES-256-GCM.

    Args:
        encrypted_email: Base64-encoded encrypted data

    Returns:
        Decrypted email address

    Raises:
        TokenEncryptionError: If decryption fails or data is corrupted
    """
    try:
        # Decode base64
        encrypted_data = base64.b64decode(encrypted_email)

        if len(encrypted_data) < 16 + 12:  # salt + nonce minimum
            raise TokenEncryptionError("Encrypted email data too short")

        # Extract components
        salt = encrypted_data[:16]
        nonce = encrypted_data[16:28]
        ciphertext = encrypted_data[28:]

        # Get encryption key and derive
        key = _get_encryption_key()
        derived_key = _derive_key(key, salt)

        # Decrypt using AES-GCM
        aesgcm = AESGCM(derived_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        # Decode to string
        return plaintext.decode('utf-8')

    except InvalidTag:
        raise TokenEncryptionError("Email data appears to be corrupted or wrong encryption key")
    except UnicodeDecodeError:
        raise TokenEncryptionError("Decrypted data is not valid UTF-8")
    except Exception as e:
        raise TokenEncryptionError(f"Failed to decrypt email: {e}")


def is_encrypted_email(data: str) -> bool:
    """
    Check if a string appears to be encrypted email data.

    This is a heuristic check - it tries to decode and check structure.
    """
    try:
        encrypted_data = base64.b64decode(data)
        # Encrypted data should be at least salt(16) + nonce(12) + some ciphertext
        return len(encrypted_data) >= 16 + 12 + 1
    except Exception:
        return False


def generate_email_encryption_key() -> str:
    """
    Generate a new random encryption key and return as base64 string.

    Returns:
        Base64-encoded 32-byte encryption key suitable for EMAIL_ENCRYPTION_KEY
    """
    key = os.urandom(32)
    return base64.b64encode(key).decode('utf-8')


def validate_email_format(email: str) -> bool:
    """
    Basic email format validation.

    Args:
        email: Email address to validate

    Returns:
        True if email format is valid
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))
