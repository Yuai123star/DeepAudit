"""
Tests for API dependency injection (app.api.deps).

Covers:
- get_current_user: valid token, expired token, invalid token, user not found, inactive user
- get_current_active_superuser: non-superuser rejection
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

from app.api.deps import get_current_user, get_current_active_superuser
from app.core.security import ALGORITHM, create_access_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET_KEY = "test_secret_key_for_testing_1234567890"


def _make_token(subject: str, secret_key: str = SECRET_KEY, expires_delta: timedelta | None = None) -> str:
    """Encode a JWT directly so we control every field."""
    from datetime import datetime, timezone

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {"exp": expire, "sub": subject}
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def _mock_db(user=None):
    """Return an AsyncMock db whose execute() returns the given user (or None)."""
    db = AsyncMock()
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = user
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock
    return db


def _mock_user(
    user_id: str = "user-123",
    is_active: bool = True,
    is_superuser: bool = False,
) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.is_active = is_active
    u.is_superuser = is_superuser
    return u


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


class TestGetCurrentUser:

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        token = _make_token("user-123")
        user = _mock_user(user_id="user-123")
        db = _mock_db(user=user)

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            result = await get_current_user(db=db, token=token)

        assert result is user

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        db = _mock_db()

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=db, token="not-a-real-token")

        assert exc_info.value.status_code == 401
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.asyncio
    async def test_wrong_secret_key_raises_401(self):
        token = _make_token("user-123", secret_key="wrong_secret_key_xxx")
        db = _mock_db()

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=db, token=token)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        token = _make_token("user-123", expires_delta=timedelta(seconds=-1))
        db = _mock_db()

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=db, token=token)

        assert exc_info.value.status_code == 401
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.asyncio
    async def test_user_not_found_raises_404(self):
        token = _make_token("nonexistent-user")
        db = _mock_db(user=None)  # no user in db

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=db, token=token)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_inactive_user_raises_400(self):
        token = _make_token("inactive-user")
        user = _mock_user(user_id="inactive-user", is_active=False)
        db = _mock_db(user=user)

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=db, token=token)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_token_with_nonexistent_sub_raises_404(self):
        """Token decodes fine but the sub field doesn't match any user row."""
        token = _make_token("no-such-id")
        db = _mock_db(user=None)

        with patch("app.api.deps.settings.SECRET_KEY", SECRET_KEY):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=db, token=token)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# get_current_active_superuser
# ---------------------------------------------------------------------------


class TestGetCurrentActiveSuperuser:

    @pytest.mark.asyncio
    async def test_superuser_passes(self):
        user = _mock_user(is_superuser=True)
        result = await get_current_active_superuser(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_non_superuser_raises_400(self):
        user = _mock_user(is_superuser=False)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_superuser(current_user=user)
        assert exc_info.value.status_code == 400
