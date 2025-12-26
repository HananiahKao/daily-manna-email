"""
OAuth token encryption utilities using AES-256-GCM.

This module provides secure encryption and decryption of OAuth tokens and credentials
to comply with Google's OAuth 2.0 security requirements.
"""

import base64
import json
import os
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class TokenEncryptionError(Exception):
    """Raised when token encryption/decryption fails."""
    pass


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
    key_b64 = os.getenv("OAUTH_ENCRYPTION_KEY")
    if not key_b64:
        raise TokenEncryptionError(
            "OAUTH_ENCRYPTION_KEY environment variable is required for token encryption. "
            "Generate a 32-byte key with: python -c \"import secrets; print(secrets.token_bytes(32).hex())\""
        )

    try:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise TokenEncryptionError("OAUTH_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return key
    except Exception as e:
        raise TokenEncryptionError(f"Invalid OAUTH_ENCRYPTION_KEY: {e}")


def encrypt_token_data(data: Dict[str, Any]) -> str:
    """
    Encrypt OAuth token data using AES-256-GCM.

    Args:
        data: Dictionary containing OAuth token data

    Returns:
        Base64-encoded encrypted data with salt and nonce

    Raises:
        TokenEncryptionError: If encryption fails
    """
    try:
        # Convert data to JSON bytes
        plaintext = json.dumps(data, separators=(',', ':')).encode('utf-8')

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
        raise TokenEncryptionError(f"Failed to encrypt token data: {e}")


def decrypt_token_data(encrypted_b64: str) -> Dict[str, Any]:
    """
    Decrypt OAuth token data using AES-256-GCM.

    Args:
        encrypted_b64: Base64-encoded encrypted data

    Returns:
        Decrypted token data dictionary

    Raises:
        TokenEncryptionError: If decryption fails or data is corrupted
    """
    try:
        # Decode base64
        encrypted_data = base64.b64decode(encrypted_b64)

        if len(encrypted_data) < 16 + 12:  # salt + nonce minimum
            raise TokenEncryptionError("Encrypted data too short")

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

        # Parse JSON
        return json.loads(plaintext.decode('utf-8'))

    except InvalidTag:
        raise TokenEncryptionError("Token data appears to be corrupted or wrong encryption key")
    except json.JSONDecodeError:
        raise TokenEncryptionError("Decrypted data is not valid JSON")
    except Exception as e:
        raise TokenEncryptionError(f"Failed to decrypt token data: {e}")


def is_encrypted_data(data: str) -> bool:
    """
    Check if a string appears to be encrypted data.

    This is a heuristic check - it tries to decode and check structure.
    """
    try:
        encrypted_data = base64.b64decode(data)
        # Encrypted data should be at least salt(16) + nonce(12) + some ciphertext
        return len(encrypted_data) >= 16 + 12 + 1
    except Exception:
        return False


def generate_encryption_key() -> str:
    """
    Generate a new random encryption key and return as base64 string.

    Returns:
        Base64-encoded 32-byte encryption key suitable for OAUTH_ENCRYPTION_KEY
    """
    key = os.urandom(32)
    return base64.b64encode(key).decode('utf-8')


def migrate_unencrypted_tokens(token_file_path: str) -> bool:
    """
    Migrate unencrypted tokens to encrypted format.

    Args:
        token_file_path: Path to token.json file

    Returns:
        True if migration was performed, False if already encrypted or no file
    """
    if not os.path.exists(token_file_path):
        return False

    try:
        with open(token_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if not content:
            return False

        # Check if already encrypted
        if is_encrypted_data(content):
            return False

        # Try to parse as unencrypted JSON
        data = json.loads(content)

        # Encrypt and save
        encrypted = encrypt_token_data(data)
        with open(token_file_path, 'w', encoding='utf-8') as f:
            f.write(encrypted)

        return True

    except Exception:
        # If anything fails, don't migrate
        return False
