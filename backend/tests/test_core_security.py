"""
Tests for app.core.security module.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.security import (
    ALGORITHM,
    create_access_token,
    get_password_hash,
    verify_password,
)


@pytest.fixture(autouse=True)
def use_test_settings(mock_settings):
    """Ensure security module uses test settings."""
    return mock_settings


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_get_password_hash_returns_bcrypt_hash(self):
        hashed = get_password_hash("my_password")
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        hashed = get_password_hash("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = get_password_hash("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_hash_is_different_each_time(self):
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2

    def test_verify_password_special_chars(self):
        for password in ["P@ssw0rd!#$%", "中文密码", "a" * 200]:
            hashed = get_password_hash(password)
            assert verify_password(password, hashed) is True


class TestAccessToken:
    """Tests for JWT access token creation."""

    def test_create_access_token_contains_sub(self, mock_settings):
        token = create_access_token(subject="user123")
        payload = jwt.decode(token, mock_settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "user123"

    def test_create_access_token_default_expiry(self, mock_settings):
        token = create_access_token(subject="user123")
        payload = jwt.decode(token, mock_settings.SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

        now = datetime.now(timezone.utc)
        expected = now + timedelta(minutes=mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        # Allow 2 minute tolerance for test execution time
        assert abs((exp - expected).total_seconds()) < 120

    def test_create_access_token_custom_expiry(self, mock_settings):
        custom_delta = timedelta(minutes=5)
        before = datetime.now(timezone.utc)
        token = create_access_token(subject="user123", expires_delta=custom_delta)
        after = datetime.now(timezone.utc)

        payload = jwt.decode(token, mock_settings.SECRET_KEY, algorithms=[ALGORITHM])
        exp_ts = payload["exp"]

        expected_earliest = int(before.timestamp()) + int(custom_delta.total_seconds())
        expected_latest = int(after.timestamp()) + int(custom_delta.total_seconds()) + 1
        assert expected_earliest <= exp_ts <= expected_latest

    def test_create_access_token_with_string_subject(self, mock_settings):
        token = create_access_token(subject="test_user@example.com")
        payload = jwt.decode(token, mock_settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "test_user@example.com"

    def test_create_access_token_with_int_subject(self, mock_settings):
        token = create_access_token(subject=42)
        payload = jwt.decode(token, mock_settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"
