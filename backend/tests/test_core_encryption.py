"""
Tests for app.core.encryption module.
"""

import pytest

from app.core.encryption import (
    EncryptionService,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
)


@pytest.fixture(autouse=True)
def reset_encryption_singleton():
    """Reset EncryptionService singleton between tests."""
    EncryptionService._instance = None
    EncryptionService._fernet = None
    yield
    EncryptionService._instance = None
    EncryptionService._fernet = None


class TestEncryptionBasic:
    """Tests for basic encrypt/decrypt operations."""

    def test_encrypt_returns_non_empty_string(self):
        svc = EncryptionService()
        result = svc.encrypt("hello world")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != "hello world"

    def test_encrypt_decrypt_roundtrip(self):
        svc = EncryptionService()
        plaintext = "sensitive_api_key_12345"
        encrypted = svc.encrypt(plaintext)
        decrypted = svc.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_empty_string(self):
        svc = EncryptionService()
        result = svc.encrypt("")
        assert result == ""

    def test_decrypt_empty_string(self):
        svc = EncryptionService()
        result = svc.decrypt("")
        assert result == ""

    def test_decrypt_non_encrypted_returns_original(self):
        svc = EncryptionService()
        plain = "this_is_not_encrypted"
        result = svc.decrypt(plain)
        assert result == plain

    def test_encrypt_decrypt_unicode(self):
        svc = EncryptionService()
        plaintext = "\u4e2d\u6587\u6d4b\u8bd5\u5bc6\u7801"
        encrypted = svc.encrypt(plaintext)
        decrypted = svc.decrypt(encrypted)
        assert decrypted == plaintext


class TestIsEncrypted:
    """Tests for the is_encrypted check."""

    def test_is_encrypted_true_for_encrypted_value(self):
        svc = EncryptionService()
        encrypted = svc.encrypt("some_value")
        assert svc.is_encrypted(encrypted) is True

    def test_is_encrypted_false_for_plain_text(self):
        svc = EncryptionService()
        assert svc.is_encrypted("plain_text_value") is False

    def test_is_encrypted_false_for_empty_string(self):
        svc = EncryptionService()
        assert svc.is_encrypted("") is False


class TestSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        instance1 = EncryptionService()
        instance2 = EncryptionService()
        assert instance1 is instance2


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_encrypt_sensitive_data_convenience_function(self):
        encrypted = encrypt_sensitive_data("my_secret")
        assert isinstance(encrypted, str)
        assert encrypted != "my_secret"

    def test_decrypt_sensitive_data_convenience_function(self):
        encrypted = encrypt_sensitive_data("my_secret")
        decrypted = decrypt_sensitive_data(encrypted)
        assert decrypted == "my_secret"
