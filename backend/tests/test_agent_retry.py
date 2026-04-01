"""
Tests for the retry module (app.services.agent.core.retry).

Covers BackoffStrategy enum, RetryConfig (should_retry / calculate_delay),
retry_with_backoff async function, and RetryResult dataclass.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.core.errors import (
    AgentError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
    ToolResourceError,
    ToolTimeoutError,
)
from app.services.agent.core.retry import (
    BackoffStrategy,
    RetryConfig,
    RetryResult,
    retry_with_backoff,
    retry_with_result,
)


# ============ BackoffStrategy ============


class TestBackoffStrategy:
    """Tests for the BackoffStrategy enum."""

    def test_enum_values(self):
        assert BackoffStrategy.CONSTANT == "constant"
        assert BackoffStrategy.LINEAR == "linear"
        assert BackoffStrategy.EXPONENTIAL == "exponential"

    def test_enum_members_count(self):
        assert len(BackoffStrategy) == 3


# ============ RetryConfig.should_retry ============


class TestRetryConfigShouldRetry:
    """Tests for RetryConfig.should_retry()."""

    def setup_method(self):
        self.config = RetryConfig()

    def test_retry_llm_rate_limit_error(self):
        err = LLMRateLimitError("rate limited")
        assert self.config.should_retry(err) is True

    def test_retry_llm_timeout_error(self):
        err = LLMTimeoutError("timed out")
        assert self.config.should_retry(err) is True

    def test_retry_llm_connection_error(self):
        err = LLMConnectionError("connection failed")
        assert self.config.should_retry(err) is True

    def test_retry_tool_timeout_error(self):
        err = ToolTimeoutError("tool timed out")
        assert self.config.should_retry(err) is True

    def test_retry_tool_resource_error(self):
        err = ToolResourceError("resource unavailable")
        assert self.config.should_retry(err) is True

    def test_retry_builtin_connection_error(self):
        assert self.config.should_retry(ConnectionError("conn")) is True

    def test_retry_builtin_timeout_error(self):
        assert self.config.should_retry(TimeoutError("timeout")) is True

    def test_retry_asyncio_timeout_error(self):
        assert self.config.should_retry(asyncio.TimeoutError()) is True

    def test_retry_recoverable_agent_error(self):
        err = AgentError("temporary", recoverable=True)
        assert self.config.should_retry(err) is True

    def test_no_retry_value_error(self):
        assert self.config.should_retry(ValueError("bad value")) is False

    def test_no_retry_generic_exception(self):
        assert self.config.should_retry(Exception("generic")) is False

    def test_no_retry_non_recoverable_agent_error(self):
        err = AgentError("permanent", recoverable=False)
        assert self.config.should_retry(err) is False


# ============ RetryConfig.calculate_delay ============


class TestRetryConfigCalculateDelay:
    """Tests for RetryConfig.calculate_delay()."""

    def test_constant_strategy(self):
        config = RetryConfig(
            base_delay=2.0,
            backoff_strategy=BackoffStrategy.CONSTANT,
            jitter=False,
        )
        assert config.calculate_delay(0) == 2.0
        assert config.calculate_delay(1) == 2.0
        assert config.calculate_delay(5) == 2.0

    def test_linear_strategy(self):
        config = RetryConfig(
            base_delay=1.0,
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter=False,
        )
        # delay = base_delay * (attempt + 1)
        assert config.calculate_delay(0) == 1.0   # 1.0 * 1
        assert config.calculate_delay(1) == 2.0   # 1.0 * 2
        assert config.calculate_delay(2) == 3.0   # 1.0 * 3

    def test_exponential_strategy(self):
        config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter=False,
        )
        # delay = base_delay * exponential_base^attempt
        assert config.calculate_delay(0) == 1.0   # 1.0 * 2^0
        assert config.calculate_delay(1) == 2.0   # 1.0 * 2^1
        assert config.calculate_delay(2) == 4.0   # 1.0 * 2^2
        assert config.calculate_delay(3) == 8.0   # 1.0 * 2^3

    def test_max_delay_cap(self):
        config = RetryConfig(
            base_delay=10.0,
            exponential_base=10.0,
            max_delay=30.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter=False,
        )
        # attempt 0: 10, attempt 1: 100 capped to 30
        assert config.calculate_delay(0) == 10.0
        assert config.calculate_delay(1) == 30.0
        assert config.calculate_delay(5) == 30.0

    def test_retry_after_from_error(self):
        config = RetryConfig(max_delay=120.0, jitter=False)
        err = LLMRateLimitError("rate limited", retry_after=45)
        delay = config.calculate_delay(0, error=err)
        assert delay == 45.0

    def test_retry_after_capped_by_max_delay(self):
        config = RetryConfig(max_delay=30.0, jitter=False)
        err = LLMRateLimitError("rate limited", retry_after=120)
        delay = config.calculate_delay(0, error=err)
        assert delay == 30.0

    def test_jitter_produces_positive_delay(self):
        config = RetryConfig(
            base_delay=1.0,
            backoff_strategy=BackoffStrategy.CONSTANT,
            jitter=True,
            jitter_factor=0.5,
        )
        for _ in range(20):
            delay = config.calculate_delay(0)
            assert delay >= 0.1  # enforced minimum


# ============ retry_with_backoff ============


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff async function."""

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        func = AsyncMock(return_value="ok")
        result = await retry_with_backoff(func, RetryConfig(max_attempts=3))
        assert result == "ok"
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        config = RetryConfig(max_attempts=3, jitter=False)
        func = AsyncMock(
            side_effect=[
                LLMRateLimitError("limit"),
                LLMRateLimitError("limit"),
                "ok",
            ]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(func, config)
        assert result == "ok"
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_non_retryable_immediately(self):
        config = RetryConfig(max_attempts=3)
        func = AsyncMock(side_effect=ValueError("bad"))
        with pytest.raises(ValueError, match="bad"):
            await retry_with_backoff(func, config)
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausts_max_attempts(self):
        config = RetryConfig(max_attempts=2, jitter=False)
        func = AsyncMock(side_effect=LLMTimeoutError("timeout"))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(LLMTimeoutError, match="timeout"):
                await retry_with_backoff(func, config)
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_on_retry_callback_called(self):
        config = RetryConfig(max_attempts=3, jitter=False)
        callback = AsyncMock()
        func = AsyncMock(
            side_effect=[
                LLMConnectionError("conn"),
                "ok",
            ]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(func, config, on_retry=callback)
        assert result == "ok"
        assert callback.call_count == 1
        # callback receives (attempt_number, error, delay)
        call_args = callback.call_args[0]
        assert call_args[0] == 1  # attempt number (1-based)
        assert isinstance(call_args[1], LLMConnectionError)


# ============ RetryResult ============


class TestRetryResult:
    """Tests for the RetryResult dataclass."""

    @pytest.mark.asyncio
    async def test_successful_result(self):
        func = AsyncMock(return_value=42)
        config = RetryConfig(max_attempts=3)
        result = await retry_with_result(func, config)
        assert result.success is True
        assert result.value == 42
        assert result.attempts == 1
        assert result.error is None

    @pytest.mark.asyncio
    async def test_failed_result_exhausted(self):
        config = RetryConfig(max_attempts=2, jitter=False)
        func = AsyncMock(side_effect=LLMTimeoutError("timeout"))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_result(func, config)
        assert result.success is False
        assert result.value is None
        assert isinstance(result.error, LLMTimeoutError)
        assert result.attempts == 2

    @pytest.mark.asyncio
    async def test_failed_result_non_retryable(self):
        config = RetryConfig(max_attempts=3)
        func = AsyncMock(side_effect=ValueError("nope"))
        result = await retry_with_result(func, config)
        assert result.success is False
        assert isinstance(result.error, ValueError)
        assert result.attempts == 1
