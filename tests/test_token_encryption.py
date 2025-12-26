#!/usr/bin/env python3
"""Tests for OAuth token encryption utilities."""

import json
import os
import pytest
from unittest.mock import patch

from app.token_encryption import (
    encrypt_token_data,
    decrypt_token_data,
    is_encrypted_data,
    generate_encryption_key,
    migrate_unencrypted_tokens,
    TokenEncryptionError
)


class TestTokenEncryption:
    """Test token encryption and decryption."""

    @pytest.fixture
    def sample_token_data(self):
        """Sample OAuth token data for testing."""
        return {
            "token": "ya29.sample_access_token",
            "refresh_token": "1//sample_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "sample_client_id",
            "client_secret": "sample_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
            "expiry": "2024-12-25T10:00:00Z"
        }

    @pytest.fixture
    def encryption_key(self):
        """A valid base64-encoded 32-byte encryption key for testing."""
        return "VDzzV7o5mqzowTaPqo/cy6yWmcl1uSXXsmORmsIUoak="  # 32 bytes base64 encoded

    def test_generate_encryption_key(self):
        """Test encryption key generation."""
        key = generate_encryption_key()
        assert isinstance(key, str)
        assert len(key) > 0

        # Decode to verify it's valid base64 for 32 bytes
        import base64
        decoded = base64.b64decode(key)
        assert len(decoded) == 32

    def test_encrypt_decrypt_roundtrip(self, sample_token_data, encryption_key):
        """Test that encrypt/decrypt preserves data."""
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            # Encrypt
            encrypted = encrypt_token_data(sample_token_data)
            assert isinstance(encrypted, str)
            assert len(encrypted) > 0

            # Decrypt
            decrypted = decrypt_token_data(encrypted)
            assert decrypted == sample_token_data

    def test_encrypt_without_key_fails(self, sample_token_data):
        """Test that encryption fails without OAUTH_ENCRYPTION_KEY."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(TokenEncryptionError, match="OAUTH_ENCRYPTION_KEY"):
                encrypt_token_data(sample_token_data)

    def test_decrypt_without_key_fails(self, sample_token_data, encryption_key):
        """Test that decryption fails without OAUTH_ENCRYPTION_KEY."""
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            encrypted = encrypt_token_data(sample_token_data)

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(TokenEncryptionError, match="OAUTH_ENCRYPTION_KEY"):
                decrypt_token_data(encrypted)

    def test_is_encrypted_data(self, sample_token_data, encryption_key):
        """Test detection of encrypted vs unencrypted data."""
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            # Test unencrypted data
            json_str = json.dumps(sample_token_data)
            assert not is_encrypted_data(json_str)

            # Test encrypted data
            encrypted = encrypt_token_data(sample_token_data)
            assert is_encrypted_data(encrypted)

    def test_decrypt_invalid_data_fails(self, encryption_key):
        """Test that decrypting invalid data fails."""
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            with pytest.raises(TokenEncryptionError):
                decrypt_token_data("invalid_encrypted_data")

    def test_decrypt_tampered_data_fails(self, sample_token_data, encryption_key):
        """Test that decrypting tampered data fails."""
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            encrypted = encrypt_token_data(sample_token_data)

            # Tamper with encrypted data
            tampered = encrypted[:-10] + "xxxxxxxxxx"

            with pytest.raises(TokenEncryptionError):
                decrypt_token_data(tampered)

    def test_decrypt_with_wrong_key_fails(self, sample_token_data):
        """Test that decrypting with wrong key fails."""
        key1 = "VDzzV7o5mqzowTaPqo/cy6yWmcl1uSXXsmORmsIUoak="  # 32 bytes base64
        key2 = "UEZZW7o5mqzowTaPqo/cy6yWmcl1uSXXsmORmsIUoak="  # Different 32 bytes base64

        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": key1}):
            encrypted = encrypt_token_data(sample_token_data)

        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": key2}):
            with pytest.raises(TokenEncryptionError, match="corrupted or wrong encryption key"):
                decrypt_token_data(encrypted)

    def test_migrate_unencrypted_tokens(self, sample_token_data, encryption_key, tmp_path):
        """Test migration of unencrypted tokens."""
        token_file = tmp_path / "token.json"

        # Create unencrypted token file
        with open(token_file, 'w') as f:
            json.dump(sample_token_data, f)

        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            # Migrate
            result = migrate_unencrypted_tokens(str(token_file))
            assert result is True

            # Verify file is now encrypted
            with open(token_file, 'r') as f:
                content = f.read()
            assert is_encrypted_data(content)

            # Verify content is correct
            decrypted = decrypt_token_data(content)
            assert decrypted == sample_token_data

    def test_migrate_already_encrypted_tokens(self, sample_token_data, encryption_key, tmp_path):
        """Test migration when tokens are already encrypted."""
        token_file = tmp_path / "token.json"

        # Create encrypted token file
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": encryption_key}):
            encrypted = encrypt_token_data(sample_token_data)
            with open(token_file, 'w') as f:
                f.write(encrypted)

            # Try to migrate again
            result = migrate_unencrypted_tokens(str(token_file))
            assert result is False  # Should not migrate

    def test_migrate_nonexistent_file(self, encryption_key):
        """Test migration of nonexistent file."""
        result = migrate_unencrypted_tokens("/nonexistent/file.json")
        assert result is False

    def test_invalid_encryption_key_format(self):
        """Test handling of invalid encryption key formats."""
        # Invalid base64 (will fail at decode step)
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": "invalid!!!base64!!!"}):
            with pytest.raises(TokenEncryptionError):
                encrypt_token_data({"test": "data"})

        # Wrong length key (valid base64 but wrong size)
        with patch.dict(os.environ, {"OAUTH_ENCRYPTION_KEY": "YWJjZGVm"}):  # 8 bytes instead of 32
            with pytest.raises(TokenEncryptionError, match="32 bytes"):
                encrypt_token_data({"test": "data"})
